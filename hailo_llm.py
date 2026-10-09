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
import hailo_server
from picamera2.devices import Hailo
from hailo_platform.genai import LLM

log=logsetup.setup('hailo_llm')

# Qwen2 is ChatML-trained: llm.prompt_template is a ChatML Jinja template and its stop tokens
# are ['<|im_end|>', '<|endoftext|>']. generate_all() does NOT apply that template -- it takes
# one raw string and continues it. Handing it a bare instruction therefore invited exactly what a
# completion model should do with a template: continue it. Live output was the prompt's own JSON
# skeleton echoed back five and a half times, 820 characters of it, with no answer anywhere.
#
# This renders the template's non-tools branch by hand for a [system, user] messages list with
# add_generation_prompt=True. Doing it by hand rather than through Jinja keeps the dependency
# surface where it is; the branch reproduced is small and fixed, and tests/test_hailo_chatml.py
# pins its exact shape.
_QWEN_DEFAULT_SYSTEM='You are Qwen, created by Alibaba Cloud. You are a helpful assistant.'

# 2026-10-08: with ENABLE_HAILO_SERVER the model runs in hailo_server.py's child process and
# none of what follows applies -- no freeze here, no brake. It stays for the in-process fallback.
# ⚠ generate_all() FREEZES THE WHOLE PROCESS while it runs (2026-10-07, live). "Explore." went to
# the model, which took 5.4 s; at the instant it returned, the IMU, encoders, current monitors,
# battery ADC and sonars ALL faulted and ALL recovered within 0.1 s. They live on two UARTs and an
# I2C bus and share nothing but this process: the call holds Python's GIL, so no other thread --
# tick loop, sensor readers, the motor ramp thread -- runs until it returns. A rover driving when
# it starts keeps its last motor duty, unwatched, for the whole call.
# Interim (brake first): every call runs the hook below first; brain.py installs one that brakes
# the drive SYNCHRONOUSLY if anything is commanded, so the wheels are stopped before the freeze.
# Real fix still open: the model in its own process (shares the Hailo VDevice with vision -- the
# reason hailo-ollama was rejected, design doc 2026-08-21 -- so it needs design).
_before_generate=None

def set_before_generate(fn):
    """Install a callable run just before every in-process generation (brain.py's brake)."""
    global _before_generate
    _before_generate=fn

def _chatml(prompt,system=None):
    sys_msg=system if system else _QWEN_DEFAULT_SYSTEM
    return (f'<|im_start|>system\n{sys_msg}<|im_end|>\n'
            f'<|im_start|>user\n{prompt}<|im_end|>\n'
            f'<|im_start|>assistant\n')


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
        self._enabled=False; self._llm=None; self._remote=None
        # FR-1400-006 real fix: the model runs in the Hailo server process when it is up.
        client=hailo_server.get_client()
        if client is None and config.ENABLE_HAILO_SERVER and hailo_server.server_failed():
            # 2026-10-09: no in-process fallback for the MODEL. It is the 2.2 s whole-process
            # freeze the server exists to remove; vision still falls back (it never froze).
            log.warning('Hailo server did not start: on-board model OFF this run (no in-process fallback).')
            return
        if client is not None:
            if client.info.get('llm'):
                self._remote=client; self._enabled=True
            else:
                log.warning('Hailo server is up without the LLM -- staying disabled.')
            return
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
        full_prompt=_chatml(prompt,system)
        if getattr(self,'_remote',None) is not None:
            # Out of process: this thread waits on a pipe, the GIL is free, nothing freezes, so
            # no brake. A dead or hung server raises ServerDown -> a failed result, as below.
            try:
                txt=self._remote.generate(full_prompt,config.HAILO_LLM_TEMPERATURE,
                                          config.HAILO_LLM_TOP_P,config.HAILO_LLM_MAX_TOKENS)
            except Exception as e:
                log.info(f'Hailo server call failed: {type(e).__name__}: {e}')
                return AIResult(False,0.0,None,False,None,f'{type(e).__name__}: {e}')
            return self._finish(txt,schema)
        try:
            # Generation parameters are passed explicitly -- see config.py. Leaving them unset
            # means None for all four, which is the runtime's prose-oriented default sampling and
            # is measurably worse at producing parseable, correct JSON (2026-09-14).
            if _before_generate is not None:
                try: _before_generate()
                except Exception: log.warning('before-generate hook failed',exc_info=True)
            # STREAMING, not generate_all() (FR-1400-006, measured on willie 2026-10-08 with a
            # 20 ms heartbeat thread): generate_all() holds the GIL for the whole call -- every
            # other thread froze for 7.7 s on a realistic 2,900-char prompt. generate() releases
            # it between tokens: same total time, longest freeze 2.2 s (reading the prompt, one
            # uninterruptible step) and ~0.12 s per token after that. The remaining prompt-read
            # freeze needs the model out of this process; until then the brake hook above stays.
            # (save_context/load_context of a pre-read prompt prefix was also measured and
            # rejected: restoring the 44 MB context costs ~1 s and the call was no faster.)
            toks=[]
            with self._llm.generate(full_prompt,
                                    temperature=config.HAILO_LLM_TEMPERATURE,
                                    top_p=config.HAILO_LLM_TOP_P,
                                    max_generated_tokens=config.HAILO_LLM_MAX_TOKENS) as gen:
                for tok in gen: toks.append(tok)
            txt=''.join(toks)
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
        return self._finish(txt,schema)

    def _finish(self,txt,schema):
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
