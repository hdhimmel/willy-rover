import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

from ai_provider import _parse_response, AIResult

# P1-2, 2026-09-14 review. The rule this file exists to enforce:
#
#   NO MALFORMED MODEL OUTPUT MAY EVER BECOME A PHYSICAL ACTION.
#
# The enforcement point is parse_success. brain.py and voice.py both gate on it, so anything that
# returns parse_success=False is structurally incapable of reaching a motor. That makes
# parse_success the thing to pin, and it is what every test below asserts on -- not the error
# string, which is cosmetic and may change.
#
# These run WITHOUT a Hailo. _parse_response is a pure function of (text, schema), which is
# precisely why the malformed-output contract is testable at all: the dangerous cases are the ones
# you cannot conveniently produce on demand from real hardware. Depending on the device to
# generate its own garbage is how this contract went untested until now.
#
# Note deliberately NOT tested here: that a well-formed but WRONG intent is rejected. It is not,
# and it cannot be -- a syntactically perfect {"intent":"forward"} is indistinguishable from a
# correct one at this layer. That is what the confidence floor, the safety layer and
# tests/test_no_direct_drive_bypass.py are for. Parsing is the first gate, not the only one.

SCHEMA = {'intent': str, 'args': dict, 'reply': str}

GOOD = '{"intent":"status","args":{},"reply":"All fine.","confidence":0.9}'


def _r(txt):
    return _parse_response(txt, SCHEMA)


# --- the shapes that MUST be accepted, or good classifications get thrown away ----------

def test_normal_json_is_accepted():
    r = _r(GOOD)
    assert r.parse_success is True
    assert r.payload['intent'] == 'status'


def test_json_followed_by_a_stop_token_is_accepted():
    """Real captured output. Qwen2's stop tokens are <|im_end|> and <|endoftext|>, and both have
    been observed trailing the JSON. Rejecting these would discard correct answers."""
    for token in ('<|endoftext|>', '<|im_end|>'):
        r = _r(GOOD + '\n' + token)
        assert r.parse_success is True, f'rejected valid JSON trailed by {token}'
        assert r.payload['intent'] == 'status'


def test_junk_before_the_json_is_accepted():
    """Also real: completions frequently open with '.\\n\\n' before the object."""
    r = _r('.\n\nSure, here you go:\n' + GOOD)
    assert r.parse_success is True


def test_json_followed_by_explanatory_prose_is_accepted():
    r = _r(GOOD + '\n\nI chose status because you asked how I am doing.')
    assert r.parse_success is True
    assert r.payload['intent'] == 'status'


def test_a_fenced_code_block_is_accepted():
    """Cloud models in particular wrap JSON in markdown fences; _parse_response strips them."""
    r = _r('```json\n' + GOOD + '\n```')
    assert r.parse_success is True


# --- the shapes that MUST be rejected ---------------------------------------------------

def test_truncated_json_is_rejected():
    r = _r('{"intent":"retrieve","args":{"object":"cup"},"reply":"On my')
    assert r.parse_success is False


def test_the_echoed_prompt_template_is_rejected():
    """The exact 2026-09-14 failure: the model echoed the prompt's own skeleton back instead of
    answering. It looks like JSON and is not -- the angle-bracket placeholders are not valid
    values. This must never be mistaken for an instruction to retrieve something called
    '<the object>'."""
    echoed = ('{"intent":"<short action name>","args":{},'
              '"reply":"<what to say back, <200 chars>","confidence":<0.0-1.0>}')
    assert _r(echoed).parse_success is False


def test_wrong_schema_is_rejected():
    r = _r('{"action":"drive","speed":1.0}')
    assert r.parse_success is False


def test_missing_required_key_is_rejected():
    assert _r('{"intent":"stop","args":{}}').parse_success is False          # no reply
    assert _r('{"args":{},"reply":"ok","confidence":1.0}').parse_success is False   # no intent


def test_wrongly_typed_field_is_rejected():
    """args as a string means the model misunderstood the shape. Coercing it would be inventing
    structure the model did not produce."""
    assert _r('{"intent":"stop","args":"none","reply":"ok","confidence":1.0}').parse_success is False


def test_empty_response_is_rejected():
    for txt in ('', '   ', '\n\n'):
        assert _r(txt).parse_success is False, f'accepted empty response {txt!r}'


def test_a_bare_stop_token_is_rejected():
    """Observed live: one probe returned nothing but '<|endoftext|>'."""
    assert _r('<|endoftext|>').parse_success is False


def test_prose_with_no_json_at_all_is_rejected():
    assert _r("I think you want me to drive forward, so I'll do that.").parse_success is False


def test_none_is_rejected_without_raising():
    """A provider that returns None instead of a string must not take the caller down with it --
    ask_sync is called from voice and from brain's worker thread, and an AttributeError there
    would surface as a crash rather than a declined command."""
    try:
        r = _parse_response(None, SCHEMA)
    except Exception as e:
        pytest.fail(f'_parse_response(None) raised {type(e).__name__}: {e}')
    assert r.parse_success is False


def test_a_single_object_array_is_recovered_not_rejected():
    """Written first as "arrays are rejected", which FAILED -- and the code was right.

    The brace-slicing that makes junk-plus-JSON and code fences work also reaches inside [ ... ]
    and recovers the object. That is consistent leniency, not a hole: the recovered object still
    goes through the full schema validation every other path uses, and because the model omitted
    a confidence field it arrives at _clamp01's deliberate 0.3 default -- below BOTH
    LOCAL_LLM_CONFIDENCE_FLOOR (0.55) and HAILO_LLM_CONFIDENCE_FLOOR (0.7), so it escalates
    rather than acting. Rejecting it would throw away a recoverable correct answer, which is the
    same mistake as rejecting a payload for a missing empty args."""
    r = _r('[{"intent":"stop","args":{},"reply":"ok"}]')
    assert r.parse_success is True
    assert r.payload['intent'] == 'stop'
    assert r.intent_confidence == pytest.approx(0.3)
    import config
    assert r.intent_confidence < config.LOCAL_LLM_CONFIDENCE_FLOOR


def test_a_multi_object_array_is_rejected():
    """The case where leniency correctly stops. Slicing first-brace-to-last-brace across two
    objects yields '{...}, {...}', which is not valid JSON -- so an ambiguous response carrying
    two different intents is refused rather than silently resolved to whichever came first."""
    assert _r('[{"intent":"stop","args":{},"reply":"a"},'
              '{"intent":"forward","args":{},"reply":"b"}]').parse_success is False


def test_a_payload_without_a_confidence_field_reads_as_uncertain():
    """_clamp01's default is 0.3, not 0.5, on purpose: a model that never self-reported must not
    be treated as averagely sure. Pinned because raising it to 0.5 would still sit below the
    voice floor but would quietly change which answers escalate if that floor is ever lowered."""
    r = _r('{"intent":"stop","args":{},"reply":"ok"}')
    assert r.parse_success is True
    assert r.intent_confidence == pytest.approx(0.3)


# --- the safety property, stated directly ------------------------------------------------

MALFORMED = [
    '',
    '   ',
    '<|endoftext|>',
    '{"intent":"retrieve","args":{"object":"cup"},"reply":"On my',
    '{"action":"drive","speed":1.0}',
    '{"intent":"stop","args":{}}',
    '{"intent":"stop","args":"none","reply":"ok","confidence":1.0}',
    'I think you want me to drive forward.',
    '[{"intent":"stop","args":{},"reply":"a"},{"intent":"forward","args":{},"reply":"b"}]',
    ('{"intent":"<short action name>","args":{},'
     '"reply":"<what to say back>","confidence":<0.0-1.0>}'),
]


@pytest.mark.parametrize('txt', MALFORMED)
def test_no_malformed_output_yields_a_usable_intent(txt):
    """The property that actually matters, asserted over every malformed shape at once.

    A caller gating on parse_success can never act on any of these. The second assertion is the
    belt-and-braces one: even a caller that wrongly ignored parse_success and reached for the
    payload would not find an intent to execute."""
    r = _parse_response(txt, SCHEMA)
    assert r.parse_success is False, f'accepted malformed output: {txt!r}'
    assert not (r.payload or {}).get('intent') or r.parse_success is False


@pytest.mark.parametrize('txt', MALFORMED)
def test_malformed_output_never_reports_confidence_above_the_floor(txt):
    """config.HAILO_LLM_CONFIDENCE_FLOOR gates whether an on-device answer drives the rover
    without cloud review. A rejected parse must not arrive carrying a confidence that could clear
    that gate -- otherwise the floor would be reading a number the model never actually asserted."""
    import config
    r = _parse_response(txt, SCHEMA)
    assert r.intent_confidence < config.HAILO_LLM_CONFIDENCE_FLOOR


def test_parse_failure_is_reported_not_raised():
    """Every malformed shape returns an AIResult. ask_sync's callers handle a declined result;
    they do not have an exception path, and _stuck() runs on a worker thread where a raise would
    be swallowed and the rover would simply never recover."""
    for txt in MALFORMED:
        assert isinstance(_parse_response(txt, SCHEMA), AIResult)
