import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

# P0 regression cover for the 2026-08-23 Hailo degradation.
#
# THE BUG THIS EXISTS TO CATCH: generate_all() is stateful. It accumulates conversation context
# across calls, so the FIRST intent classification on a fresh model worked and later ones
# progressively degraded -- ending in "[HailoRT] [warning] Conversation context is full" and
# every subsequent call failing to parse.
#
# That failure mode is invisible to a single-call test, which is exactly why it survived to be
# found live. So these assert on REPEATED calls against ONE long-lived instance, which is how
# the rover actually uses it: brain.py constructs the provider once at startup and keeps it for
# the life of the process.
#
# Intent classification is single-turn BY CONTRACT -- the same contract LocalAIProvider has,
# where `history` is accepted and unused. Any conversational state surviving between two
# independent classifications is a defect, not a feature, because utterance N-1 must not be able
# to change how utterance N is understood.
#
# These tests deliberately do NOT need a Hailo. They drive HailoIntentModel's own call path with
# a stub LLM, so they run in CI, on the laptop, and on a rover with the NPU busy. Accuracy is a
# separate question, measured by experiments/llm_reliability_batch.py against the real device.


class _StubLLM:
    """Stands in for hailo_platform.genai.LLM, and records the ordering that matters."""

    def __init__(self, replies=None, raise_on=()):
        self.replies = replies or []
        self.raise_on = set(raise_on)
        self.calls = 0
        self.clears = 0
        self.events = []            # ordered trace of 'generate'/'clear'
        self.context = []           # what a STATEFUL implementation would accumulate

    def generate_all(self, prompt):
        self.events.append('generate')
        self.context.append(prompt)
        i = self.calls
        self.calls += 1
        if i in self.raise_on:
            raise RuntimeError('simulated HailoRT failure')
        if i < len(self.replies):
            return self.replies[i]
        return '{"intent":"status","args":{},"reply":"ok","confidence":0.9}'

    def clear_context(self):
        self.events.append('clear')
        self.clears += 1
        self.context.clear()


# hailo_llm imports picamera2.devices and hailo_platform.genai at module scope, so this file
# runs on the rover and skips elsewhere. Guarding those imports would mean restructuring the
# Hailo.TARGET sharing logic, which is load-bearing (a second VDevice collides with vision's --
# HAILO_OUT_OF_PHYSICAL_DEVICES(74), found live 2026-08-23), and is not worth disturbing for
# test convenience. Nothing below needs an actual NPU: the stub replaces the LLM, so these pass
# even with the device busy serving vision.
pytest.importorskip('picamera2', reason='hailo_llm needs picamera2; rover-only test')
pytest.importorskip('hailo_platform', reason='hailo_llm needs hailo_platform; rover-only test')


@pytest.fixture
def model():
    from hailo_llm import HailoIntentModel
    m = HailoIntentModel.__new__(HailoIntentModel)      # no device, no 1.7GB HEF
    import threading
    m._enabled = True
    m._llm = _StubLLM()
    m._lock = getattr(m, '_lock', threading.Lock())
    return m


def _ask(m, text='how are you doing'):
    return m._call(text, schema={'intent': str, 'args': dict, 'reply': str})


# --- the actual regression ------------------------------------------------------------

def test_twenty_consecutive_calls_all_parse(model):
    """The original symptom: call 1 fine, later calls garbled. A single-call test cannot see it."""
    for i in range(20):
        r = _ask(model, f'utterance number {i}')
        assert r.parse_success, f'call {i + 1} of 20 failed to parse: {r.reason}'


def test_context_never_accumulates_across_calls(model):
    """The mechanism, asserted directly rather than via its symptom. If context survives a call,
    utterance N-1 can change how utterance N is understood -- and the failure appears gradually,
    which is the hardest kind to attribute."""
    for i in range(20):
        _ask(model, f'utterance number {i}')
        assert len(model._llm.context) == 0, f'context survived call {i + 1}'


def test_every_generate_is_followed_by_a_clear(model):
    """Ordering, not just counts: clear-before-generate would leave the last call's context
    live for the whole gap, and the totals alone would look identical."""
    for i in range(10):
        _ask(model, f'utterance {i}')
    assert model._llm.events == ['generate', 'clear'] * 10


def test_clear_count_matches_call_count(model):
    for i in range(15):
        _ask(model, f'utterance {i}')
    assert model._llm.clears == model._llm.calls == 15


# --- failure paths, which is where cleanup usually gets skipped ------------------------

def test_context_is_cleared_when_generation_raises(model):
    """The `finally:` in ask_sync exists for this. A raising call that skipped cleanup would
    poison every later classification -- and an exception is exactly when a caller-side cleanup
    would have been missed."""
    model._llm = _StubLLM(raise_on={0, 1, 2})
    for i in range(3):
        r = _ask(model, f'failing {i}')
        assert r.parse_success is False
    assert model._llm.clears == 3
    assert len(model._llm.context) == 0


def test_context_is_cleared_when_output_is_garbled(model):
    """Unparseable output is a normal outcome, not an error path -- the model returns a string
    and it simply is not JSON. Cleanup must happen regardless."""
    model._llm = _StubLLM(replies=['not json at all', '<|endoftext|>', ''])
    for i in range(3):
        _ask(model, f'garbled {i}')
    assert model._llm.clears == 3
    assert len(model._llm.context) == 0


def test_recovery_after_failures(model):
    """A burst of failures must not leave the provider permanently degraded -- if it did, one
    bad utterance would cost every later one."""
    model._llm = _StubLLM(replies=['garbage', 'garbage'], raise_on={2})
    for i in range(3):
        _ask(model, f'bad {i}')
    r = _ask(model, 'now a good one')
    assert r.parse_success is True


# --- malformed output must not become an action ----------------------------------------

def test_garbled_output_is_rejected_not_returned_as_an_intent(model):
    """P1: never let malformed model output reach anything that moves. Rejection has to be a
    parse_success of False, because brain.py gates on that -- returning a half-parsed payload
    would put the decision in the caller's hands."""
    model._llm = _StubLLM(replies=['{"intent": "retrieve"'])    # truncated JSON
    r = _ask(model)
    assert r.parse_success is False
    assert r.payload is None or 'intent' not in (r.payload or {})


def test_output_missing_required_schema_keys_is_rejected(model):
    model._llm = _StubLLM(replies=['{"reply":"sure thing"}'])   # no intent, no args
    r = _ask(model)
    assert r.parse_success is False


def test_junk_around_valid_json_is_still_accepted(model):
    """Confirmed live: real output carries leading junk and a trailing <|endoftext|>. Rejecting
    that would throw away good classifications, so the slicing in _parse_response is load-bearing
    and this pins it."""
    model._llm = _StubLLM(replies=[
        '.\n\n{"intent":"battery","args":{},"reply":"plenty","confidence":0.8}\n<|endoftext|>'])
    r = _ask(model)
    assert r.parse_success is True
    assert r.payload['intent'] == 'battery'


def test_an_unavailable_model_reports_rather_than_raises(model):
    """brain.py falls through to the cloud provider on this. A raise would take the tick with it."""
    model._enabled = False
    r = _ask(model)
    assert r.parse_success is False
    assert r.payload is None
