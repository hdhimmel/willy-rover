import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

# WHY THIS EXISTS. The Hailo model is Qwen2, ChatML-trained -- it ships a chat template
# (llm.prompt_template) and its stop tokens are ['<|im_end|>', '<|endoftext|>']. generate_all()
# does NOT apply that template; it takes one raw string and continues it.
#
# Until 2026-09-14 hailo_llm.py handed it a bare instruction string. A chat model given a raw
# template with no role framing does what a completion model does -- it CONTINUES the text. The
# observed output was the prompt's own JSON skeleton echoed back five and a half times:
#
#   {"intent":"<short action name>","args":{},"reply":"<what to say back, <200 chars>", ...
#
# repeated until the token budget ran out, 820 characters of it. That is also the explanation for
# the "Expecting value: line 1 column 97 (char 96)" that appeared in 20 of 32 batch failures and
# was misread as truncation for weeks: char 96 is exactly where `"confidence":<0.0-1.0` starts,
# and `<` is the first thing json.loads cannot accept. The offset was identical every time
# because the echoed skeleton is a fixed string. Raising max_generated_tokens did nothing,
# because nothing was ever being truncated.
#
# Measured on three utterances, same model, same sampling: raw framing parsed 1 of 3 with 820-1039
# character completions; ChatML framing parsed 3 of 3 with ~110 character ones.
#
# These tests pin the FRAMING only. Whether the model then picks the right intent is a separate
# question with a separate measurement (experiments/llm_reliability_batch.py, FRD G-6) -- and the
# answer to it is still poor. Do not read a passing file here as "the Hailo path works".

pytest.importorskip('picamera2', reason='hailo_llm needs picamera2; rover-only test')
pytest.importorskip('hailo_platform', reason='hailo_llm needs hailo_platform; rover-only test')


class _RecordingLLM:
    def __init__(self):
        self.prompt = None

    def generate_all(self, prompt, **kw):
        self.prompt = prompt
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


def _ask(m, prompt='bring me my slippers', system=None):
    return m._call(prompt, system=system, schema={'intent': str, 'args': dict, 'reply': str})


def test_the_prompt_is_wrapped_in_chatml_role_markers(model):
    """The defect in one assertion: a bare instruction string reaches the model unframed."""
    _ask(model)
    sent = model._llm.prompt
    assert '<|im_start|>user' in sent, 'prompt was sent without ChatML role framing'
    assert '<|im_end|>' in sent


def test_it_ends_with_the_assistant_generation_prompt(model):
    """add_generation_prompt in the model's own template. Without the trailing
    '<|im_start|>assistant\n' the model has not been handed the turn, and continuing the user
    message is a perfectly reasonable thing for it to do next -- which is the echo bug."""
    assert _ask(model) is not None
    assert model._llm.prompt.endswith('<|im_start|>assistant\n')


def test_the_system_message_goes_in_the_system_turn(model):
    """Previously system was concatenated onto the user text with a blank line. The template has
    a system role; instructions carry more weight there, and merging them into the user turn is
    what made the whole thing look like one block of text to continue."""
    _ask(model, system='You are Willie.')
    sent = model._llm.prompt
    assert '<|im_start|>system\nYou are Willie.<|im_end|>' in sent


def test_a_system_turn_is_emitted_even_when_the_caller_gives_none(model):
    """The template emits Qwen's stock system message when the messages list has no system role.
    Matching that keeps the framing identical whether or not a caller passes one, rather than
    producing two different prompt shapes that would have to be debugged separately."""
    _ask(model, system=None)
    assert model._llm.prompt.startswith('<|im_start|>system\n')


def test_the_user_text_survives_intact(model):
    """Framing must not mangle the payload."""
    _ask(model, prompt='bring me my slippers')
    assert 'bring me my slippers' in model._llm.prompt


def test_the_prompt_is_not_double_wrapped(model):
    """Guard against a caller that already framed its text, and against this being applied twice
    if the wrapping ever moves. Exactly one assistant handoff, or the model sees a conversation
    that did not happen."""
    _ask(model)
    assert model._llm.prompt.count('<|im_start|>assistant') == 1
