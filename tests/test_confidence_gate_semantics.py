import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

import config
from ai_provider import _parse_response, _action_confidence

# P0-3, 2026-09-14 review. The review asked: "when Hailo reports >= 0.7 confidence, how often is
# it actually right?" -- on the assumption that HAILO_LLM_CONFIDENCE_FLOOR reads the model's
# self-reported confidence. IT DOES NOT, and the difference matters enough to pin here.
#
# There are TWO gates in this codebase and they are easy to confuse:
#
#   voice intent path   voice.py:467   LOCAL_LLM_CONFIDENCE_FLOOR = 0.55
#                                      compared against AIResult.intent_confidence, which IS the
#                                      model's own self-reported "confidence" field, clamped.
#
#   STUCK motion path   brain.py:1007  HAILO_LLM_CONFIDENCE_FLOOR = 0.7
#                                      compared against AIResult.action_confidence, which is
#                                      _action_confidence(payload) -- a STRUCTURAL check that
#                                      returns 1.0 or 0.0 and nothing in between.
#
# So on the motion path the floor is a BOOLEAN dressed as a threshold. 0.7, 0.5 and 0.95 all
# behave identically; only 0.0 (accept structurally invalid actions) and >1.0 (reject everything)
# differ. "Tune the 0.7 floor against real output" -- which FRD G-6, config.py and this
# assistant's own review notes all recommended at various points -- is not a meaningful action.
# The model's self-reported confidence never reaches this decision at all.
#
# This is not necessarily a defect. A structural gate is arguably the more honest instrument,
# since a 1.5B model's self-rated confidence is unvalidated and it rates its wrong answers 0.8-1.0
# anyway. But it must be UNDERSTOOD, because the residual risk it leaves is specific and is NOT
# the one the docs described: a structurally perfect, semantically terrible action -- "forward,
# 2 seconds" straight into the obstacle that caused the STUCK -- scores exactly 1.0 and proceeds
# without cloud review. No confidence number anywhere would catch that. safety.py's clamps and
# the reflex layer are what stand between it and the wheels.


MOTION_SCHEMA = {'action': str, 'duration': (int, float), 'speed': (int, float)}


def _res(txt):
    return _parse_response(txt, MOTION_SCHEMA)


# --- what action_confidence actually is --------------------------------------------------

def test_action_confidence_is_binary():
    """The claim the rest of this file rests on. If someone makes _action_confidence return a
    graded score, the floor becomes a real threshold and every comment above needs rewriting --
    this test failing is the signal to do that."""
    seen = set()
    for payload in (
        {'action': 'forward', 'duration': 1.0, 'speed': 0.4},
        {'action': 'reverse', 'duration': 0.5, 'speed': 0.2},
        {'action': 'stop'},
        {'action': 'wait'},
        {'action': 'teleport', 'duration': 1.0, 'speed': 0.4},
        {'action': 'forward', 'duration': -1, 'speed': 0.4},
        {'action': 'forward', 'duration': 1.0, 'speed': 99},
        {'action': 'forward', 'duration': 10 ** 6, 'speed': 0.4},
    ):
        seen.add(_action_confidence(payload))
    assert seen <= {0.0, 1.0}, f'expected a binary signal, got {sorted(seen)}'
    assert seen == {0.0, 1.0}, 'the sample should exercise both outcomes'


def test_a_recognised_action_with_sane_bounds_scores_exactly_one():
    assert _action_confidence({'action': 'forward', 'duration': 1.0, 'speed': 0.4}) == 1.0


def test_an_unrecognised_action_scores_zero():
    """The real protection on this path: an invented action name cannot execute, whatever the
    model claims about its own certainty."""
    assert _action_confidence({'action': 'launch', 'duration': 1.0, 'speed': 0.4}) == 0.0


def test_out_of_range_duration_or_speed_scores_zero():
    assert _action_confidence({'action': 'forward', 'duration': -1, 'speed': 0.4}) == 0.0
    assert _action_confidence({'action': 'forward', 'duration': 1.0, 'speed': 2.0}) == 0.0


# --- the consequence: the floor is not a tuning knob -------------------------------------

@pytest.mark.parametrize('floor', [0.05, 0.3, 0.5, 0.7, 0.9, 1.0])
def test_every_floor_in_the_open_interval_behaves_identically(floor):
    """The point of this file. A structurally valid action passes every one of these floors; an
    invalid one fails every one. Changing the number changes nothing, so a doc that says 'tune
    this against the batch' is promising something that cannot happen."""
    good = _res('{"action":"forward","duration":1.0,"speed":0.4}')
    bad = _res('{"action":"teleport","duration":1.0,"speed":0.4}')
    assert good.action_confidence >= floor
    assert not (bad.action_confidence >= floor)


def test_the_configured_floor_sits_in_that_interval():
    """Guards the one way this could actually break: a floor of 0.0 would admit structurally
    invalid actions, and anything above 1.0 would reject every on-device decision and silently
    make the rover fully cloud-dependent for STUCK recovery."""
    assert 0.0 < config.HAILO_LLM_CONFIDENCE_FLOOR <= 1.0


def test_the_models_self_reported_confidence_does_not_affect_the_motion_gate():
    """Stated directly, because this is the specific misunderstanding being corrected. Two
    payloads identical but for the model's own confidence field produce the same gate result."""
    sure = _res('{"action":"forward","duration":1.0,"speed":0.4,"confidence":1.0}')
    unsure = _res('{"action":"forward","duration":1.0,"speed":0.4,"confidence":0.01}')
    assert sure.action_confidence == unsure.action_confidence == 1.0
    floor = config.HAILO_LLM_CONFIDENCE_FLOOR
    assert (sure.action_confidence >= floor) == (unsure.action_confidence >= floor) is True


def test_a_confidently_wrong_but_structurally_valid_action_still_passes_the_gate():
    """The residual risk, made explicit rather than left as prose in a gap register. Driving
    forward is exactly the wrong response to being stuck against an obstacle in front, and this
    payload sails through the confidence gate. What stops it is safety.py and the reflex layer --
    NOT this floor. Anyone tempted to rely on the floor for semantic correctness should read
    this test first."""
    r = _res('{"action":"forward","duration":2.0,"speed":0.9,"confidence":0.99}')
    assert r.parse_success is True
    assert r.action_confidence >= config.HAILO_LLM_CONFIDENCE_FLOOR


# --- the voice path, where confidence IS the model's own ---------------------------------

def test_the_voice_path_gate_does_read_the_models_confidence():
    """Contrast, so the two are not conflated again. The intent schema has no 'action' key, so
    action_confidence is None there and intent_confidence -- the model's own number -- is what
    voice.py:467 compares against LOCAL_LLM_CONFIDENCE_FLOOR."""
    intent_schema = {'intent': str, 'args': dict, 'reply': str}
    high = _parse_response('{"intent":"stop","args":{},"reply":"ok","confidence":0.95}',
                           intent_schema)
    low = _parse_response('{"intent":"stop","args":{},"reply":"ok","confidence":0.10}',
                          intent_schema)
    assert high.action_confidence is None and low.action_confidence is None
    assert high.intent_confidence == pytest.approx(0.95)
    assert low.intent_confidence == pytest.approx(0.10)
    assert high.intent_confidence >= config.LOCAL_LLM_CONFIDENCE_FLOOR
    assert low.intent_confidence < config.LOCAL_LLM_CONFIDENCE_FLOOR
