# Hailo-10H NPU-backed speech-to-text, gated behind config.ENABLE_HAILO_STT. Scaffolding only --
# see docs/superpowers/plans/2026-08-23-hailo-voice-offload.md Task 5. Blocked on compiling a
# Whisper HEF via Hailo's Dataflow Compiler on a separate x86 Ubuntu machine (ARM/this rover
# cannot run the compiler); no such machine is available yet, so real loading/inference is not
# implemented here -- do not guess the HailoRT call shape without a real HEF to test against, the
# same lesson Task 4's generate_all() investigation already demonstrated live on this codebase.
import os
import config

class HailoWhisper:
    """Scaffold for a future faster_whisper replacement in voice.py::_process_utterance().

    NOT usable yet, and deliberately impossible to half-enable: __init__ raises unconditionally,
    so voice.py's fail-safe wiring in _load_models() always catches it and falls back to the CPU
    faster_whisper path (same pattern as ENABLE_HAILO_VISION/ENABLE_HAILO_LLM).

    The unconditional raise is the point. Gating only on os.path.exists() would mean that the
    moment any file appears at HAILO_STT_MODEL_PATH with ENABLE_HAILO_STT=True, construction
    succeeds and the *first utterance* raises NotImplementedError instead -- which propagates out
    of _process_utterance -> _handle_wake -> _loop's outer except, setting self._running=False and
    permanently killing the entire voice pipeline, including voice "stop". Failing at construction
    keeps that failure inside the fallback path where it belongs.

    transcribe()'s signature mirrors the real call site (voice.py::_process_utterance):
        segments,_=self._whisper.transcribe(pcm,language='en',beam_size=1,vad_filter=True)
    so a future implementation is a genuine drop-in: it must accept those kwargs and return a
    (segments, info) tuple whose segments each carry a .text attribute.
    """
    def __init__(self):
        model_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.HAILO_STT_MODEL_PATH)
        raise RuntimeError(
            f'HailoWhisper is scaffolding only -- no working Hailo STT implementation exists. '
            f'It needs a Whisper model compiled on a separate x86 Ubuntu machine via the Hailo '
            f'Dataflow Compiler (ARM cannot run the compiler), landing at {model_path}, AND the '
            f'real HailoRT inference call written against that HEF. See docs/superpowers/plans/'
            f'2026-08-23-hailo-voice-offload.md Task 5 / spec section 10.4.')

    def transcribe(self,pcm,language=None,beam_size=None,vad_filter=None,**kwargs):
        # Signature matches voice.py::_process_utterance()'s real call so this is a true drop-in
        # once implemented. Unreachable today -- __init__ always raises.
        raise NotImplementedError('HailoWhisper is scaffolding only -- see class docstring.')
