# Hailo-10H NPU-backed intent-parsing LLM, gated behind config.ENABLE_HAILO_LLM. Drop-in
# alternative to ai_provider.py::LocalAIProvider -- subclasses the same AIProvider base class
# so voice.py::_interpret_local() (which calls self._local_ai.ask_sync(...)) doesn't need to
# know which backend it's talking to. See docs/superpowers/plans/2026-08-23-hailo-voice-offload.md
# Task 4 for the full investigation trail behind this file's choices.
import os
import config
import logsetup
from ai_provider import AIProvider, AIResult, _parse_response
from logsetup import log_event
from picamera2.devices import Hailo
from hailo_platform.genai import LLM

log=logsetup.setup('hailo_llm')

class HailoIntentModel(AIProvider):
    # Shares vision's device via the class-level Hailo.TARGET singleton (picamera2.devices.Hailo)
    # rather than constructing a separate hailo_platform.genai.VDevice() -- confirmed live on the
    # rover 2026-08-23 that a second, independently-constructed VDevice collides with vision's
    # existing one (HAILO_OUT_OF_PHYSICAL_DEVICES(74)), while reusing Hailo.TARGET directly works.
    # If ENABLE_HAILO_VISION is False (or this loads before vision does), Hailo.TARGET is still
    # None here -- construct it ourselves using the exact same VDevice params Hailo.__init__ uses
    # internally, so a later vision Hailo(...) call correctly reuses this one instead of colliding
    # with it.
    def __init__(self):
        super().__init__()
        self._enabled=False; self._llm=None
        model_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.HAILO_LLM_MODEL_PATH)
        if not os.path.exists(model_path):
            log.warning(f'Hailo LLM HEF missing at {model_path} -- staying disabled.')
            return
        try:
            if Hailo.TARGET is None:
                from hailo_platform import VDevice, HailoSchedulingAlgorithm
                params=VDevice.create_params()
                params.scheduling_algorithm=HailoSchedulingAlgorithm.ROUND_ROBIN
                Hailo.TARGET=VDevice(params)
            # Increment only AFTER LLM() succeeds. Incrementing first leaks the refcount on a
            # load failure -- nothing owns it, so picamera2's vision close() can never drive the
            # count to 0 and release the shared VDevice.
            self._llm=LLM(Hailo.TARGET,model_path)
            Hailo.TARGET_REF_COUNT+=1
            self._enabled=True
        except Exception as e:
            log.error(f'Hailo LLM load failed, staying disabled: {e}')
            self._enabled=False

    @property
    def available(self): return self._enabled

    def _call(self,prompt,system=None,schema=None,history=None):
        # history unused -- local interpretation is single-turn, same as LocalAIProvider._call().
        if not self.available:
            log_event(log,'AI_UNAVAILABLE',severity='info',subsystem='ai_provider',provider='hailo')
            return AIResult(False,0.0,None,False,None,'Hailo LLM not loaded')
        log_event(log,'AI_REQUEST',severity='info',subsystem='ai_provider',provider='hailo')
        # generate_all() is synchronous, returns str directly -- confirmed live on the rover
        # 2026-08-23 (docs/superpowers/plans/2026-08-23-hailo-voice-offload.md Task 4 Step 0).
        # No chat-template plumbing needed the way LocalAIProvider's create_chat_completion
        # requires -- system is folded into the same prompt string since generate_all() takes
        # one string, not a messages list; voice.py never actually passes a separate `system`
        # for local interpretation today (_interpret_local() builds one combined prompt), so
        # this is not a behavior change, just documented here since the shape differs from
        # LocalAIProvider's messages-list call.
        full_prompt=f'{system}\n\n{prompt}' if system else prompt
        try:
            txt=self._llm.generate_all(full_prompt)
        except Exception as e:
            log.info(f'Hailo LLM call failed: {type(e).__name__}: {e}')
            return AIResult(False,0.0,None,False,None,f'{type(e).__name__}: {e}')
        finally:
            # Confirmed live 2026-08-23: generate_all() is stateful -- it keeps accumulating
            # conversation context across calls (real symptom hit during testing: "[HailoRT]
            # [warning] Conversation context is full", followed by every subsequent call failing
            # to parse). Each call here is meant to be single-turn, same as LocalAIProvider's
            # history-unused contract, so clear context after every call regardless of outcome --
            # in `finally` so a failed/exception call doesn't leave stale context for the next one.
            try: self._llm.clear_context()
            except Exception as e: log.warning(f'Hailo LLM clear_context failed: {e}')
        # Confirmed live: real output can carry leading junk before the JSON and a trailing
        # <|endoftext|> token after it (e.g. ".\n\n{...}\n<|endoftext|>"). _parse_response()'s
        # existing txt[txt.index('{'):txt.rindex('}')+1] slicing already handles both --
        # verified against a real captured completion, no change needed there.
        result=_parse_response(txt,schema)
        if not result.parse_success:
            log_event(log,'AI_REJECTED',severity='warning',subsystem='ai_provider',
                      provider='hailo',reason=result.reason)
        else:
            log_event(log,'AI_RESULT',severity='info',subsystem='ai_provider',provider='hailo',
                      intent_confidence=result.intent_confidence,action_confidence=result.action_confidence)
        return result
