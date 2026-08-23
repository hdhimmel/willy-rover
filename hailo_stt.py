# Hailo-10H NPU-backed speech-to-text, gated behind config.ENABLE_HAILO_STT. Scaffolding only --
# see docs/superpowers/plans/2026-08-23-hailo-voice-offload.md Task 5. Blocked on compiling a
# Whisper HEF via Hailo's Dataflow Compiler on a separate x86 Ubuntu machine (ARM/this rover
# cannot run the compiler); no such machine is available yet, so real loading/inference is not
# implemented here -- do not guess the HailoRT call shape without a real HEF to test against, the
# same lesson Task 4's generate_all() investigation already demonstrated live on this codebase.
import os
import config

class HailoWhisper:
    """Drop-in replacement for faster_whisper in voice.py::_process_utterance() once a real HEF
    exists -- transcribe(pcm) matches that call's existing shape (spec section 4). Always raises
    on construction today, which voice.py's fail-safe wiring (see _load_models()) catches and
    falls back to the CPU faster_whisper path, same pattern as ENABLE_HAILO_VISION/ENABLE_HAILO_LLM."""
    def __init__(self):
        model_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.HAILO_STT_MODEL_PATH)
        if not os.path.exists(model_path):
            raise RuntimeError(
                f'Hailo STT HEF not found at {model_path} -- this needs a Whisper model '
                f'compiled on a separate x86 Ubuntu machine via the Hailo Dataflow Compiler; '
                f'ARM cannot run the compiler. See docs/superpowers/plans/2026-08-23-hailo-'
                f'voice-offload-design.md Task 5/spec section 10.4.')
        # Real loading/inference implementation blocked until that HEF exists -- do not guess
        # the HailoRT call shape here without hardware to confirm it against, same reasoning
        # Task 4 followed for the LLM's generate_all() investigation.

    def transcribe(self,pcm):
        raise NotImplementedError('HailoWhisper is scaffolding only -- see class docstring.')
