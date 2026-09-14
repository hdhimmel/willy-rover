import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config

# WHY THIS EXISTS. hailo_llm.py called generate_all(full_prompt) with no generation parameters
# at all, so temperature, top_p, top_k and max_generated_tokens were every one of them None --
# whatever the runtime defaults happen to be. For a model whose entire job is emitting one small
# JSON object, that is the wrong end of the sampling range: default sampling optimises for varied
# prose, and varied prose is precisely what breaks a strict parser.
#
# Observed live 2026-09-14, same prompt, same model, back to back:
#   defaults                  -> {"intent":"status", ...}   valid JSON, WRONG intent
#   temperature=0.1, top_p=0.9 -> {"intent":"battery", ...}  valid JSON, CORRECT intent
#
# That is a single sample and proves nothing on its own -- the 32-case batch is what decides it.
# What these tests pin is narrower and worth pinning regardless of how the batch scores: that the
# parameters are actually PASSED. A knob in config.py that never reaches generate_all() is worse
# than no knob, because the batch result then gets attributed to a setting that was never in
# effect, and the next person tunes a number that does nothing.

pytest.importorskip('picamera2', reason='hailo_llm needs picamera2; rover-only test')
pytest.importorskip('hailo_platform', reason='hailo_llm needs hailo_platform; rover-only test')


class _RecordingLLM:
    """Records the kwargs generate_all() is called with. Deliberately strict: it accepts **kw
    rather than named parameters, so a passed-but-misspelled parameter shows up as itself
    instead of raising a TypeError that could be mistaken for an API mismatch."""

    def __init__(self):
        self.kwargs = None
        self.prompt = None

    def generate_all(self, prompt, **kw):
        self.prompt = prompt
        self.kwargs = kw
        return '{"intent":"status","args":{},"reply":"ok","confidence":0.9}'

    def clear_context(self):
        pass


@pytest.fixture
def model():
    from hailo_llm import HailoIntentModel
    import threading
    m = HailoIntentModel.__new__(HailoIntentModel)
    m._enabled = True
    m._llm = _RecordingLLM()
    m._lock = getattr(m, '_lock', threading.Lock())
    return m


def _ask(m):
    return m._call('how much battery do you have left',
                   schema={'intent': str, 'args': dict, 'reply': str})


def test_generation_parameters_reach_the_model(model):
    """The whole point. Without this, config knobs are decorative."""
    _ask(model)
    kw = model._llm.kwargs
    assert kw, 'generate_all() was called with no generation parameters at all'
    assert kw.get('temperature') == config.HAILO_LLM_TEMPERATURE
    assert kw.get('top_p') == config.HAILO_LLM_TOP_P
    assert kw.get('max_generated_tokens') == config.HAILO_LLM_MAX_TOKENS


def test_temperature_is_low_enough_for_structured_output(model):
    """A guard on the VALUE, not just the plumbing. This model emits JSON that a strict parser
    consumes; there is no upside to creative sampling and a documented downside. If someone
    raises this to chat-like values, the batch score this was tuned against no longer applies."""
    assert 0.0 <= config.HAILO_LLM_TEMPERATURE <= 0.3, (
        f'temperature {config.HAILO_LLM_TEMPERATURE} is too high for JSON-only output; '
        f're-run experiments/llm_reliability_batch.py before changing this')


def test_max_tokens_leaves_room_for_a_complete_object(model):
    """20 of 32 batch failures on 2026-09-14 broke at exactly character 96, which is what
    truncation looks like. A budget too small to close the JSON object reproduces that
    regardless of how good the model is."""
    assert config.HAILO_LLM_MAX_TOKENS >= 128


def test_the_prompt_is_still_passed_positionally(model):
    """Guards against a refactor that moves the prompt into kwargs; generate_all's first
    positional parameter is the prompt and the API is not ours to change."""
    _ask(model)
    assert 'battery' in model._llm.prompt
