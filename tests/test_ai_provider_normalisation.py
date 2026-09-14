import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

from ai_provider import _parse_response

# WHY THIS EXISTS. Two small models, measured on the same 32-case batch 2026-09-14, fail in
# opposite directions on the SAME prompt:
#
#   Hailo (Qwen2 1.5B) pads args with the prompt's own placeholder syntax on intents that take
#   no object: {"intent":"shutdown","args":{"object":"<the object>"},...}
#   CPU (LocalAIProvider) omits args entirely: {"intent":"shutdown","reply":"...","confidence":0.9}
#
# In BOTH cases the intent is correct and the classification is usable. In both cases it was
# thrown away -- the first because the batch scores bool(args), the second because
# _validate_schema requires an args key and a missing one is a hard reject.
#
# Three rounds of prompt rewording were spent trying to satisfy both models at once, and each
# rewording fixed one model by breaking the other (Hailo 0% -> 53% -> 25%; CPU 69% -> 34%).
# That is the signature of a problem in the wrong layer. The prompt cannot be the place this is
# enforced, because the prompt is one string shared by two models with different habits.
#
# So normalise here instead, where it applies to every provider equally. Both rules below are
# defensible WITHOUT reference to any benchmark, which is the test of whether this is engineering
# or metric-gaming:
#
#   1. A value of the form "<...>" is placeholder text the model copied out of its instructions.
#      It is never a real object name. Letting it through is worse than dropping it -- it is a
#      string that would reach object-retrieval and be searched for.
#   2. args is a CONTAINER with a well-defined empty value. A missing one carries no less
#      information than an empty one. This does not invent intent or reply, which are content.


def _r(payload_json):
    return _parse_response(payload_json, {'intent': str, 'args': dict, 'reply': str})


# --- rule 1: placeholder values ---------------------------------------------------------

def test_placeholder_args_value_is_dropped():
    r = _r('{"intent":"shutdown","args":{"object":"<the object>"},"reply":"Night.","confidence":0.9}')
    assert r.parse_success
    assert r.payload['args'] == {}, 'placeholder text must not survive as an object name'


def test_a_real_object_name_is_kept():
    """The rule must not eat legitimate args -- retrieve is the intent that actually needs them."""
    r = _r('{"intent":"retrieve","args":{"object":"blue cup"},"reply":"On it.","confidence":0.9}')
    assert r.parse_success
    assert r.payload['args'] == {'object': 'blue cup'}


def test_only_the_placeholder_key_is_dropped_not_the_whole_args():
    r = _r('{"intent":"retrieve","args":{"object":"slippers","room":"<the room>"},'
           '"reply":"Going.","confidence":0.9}')
    assert r.parse_success
    assert r.payload['args'] == {'object': 'slippers'}


def test_angle_brackets_inside_a_longer_string_are_not_treated_as_placeholders():
    """Only a value that is ENTIRELY a placeholder counts. Substring matching would corrupt
    real text that happens to contain a bracket."""
    r = _r('{"intent":"retrieve","args":{"object":"the <b> sign"},"reply":"ok","confidence":0.9}')
    assert r.parse_success
    assert r.payload['args'] == {'object': 'the <b> sign'}


def test_non_string_args_values_are_untouched():
    r = _r('{"intent":"move","args":{"distance":5},"reply":"ok","confidence":0.9}')
    assert r.parse_success
    assert r.payload['args'] == {'distance': 5}


# --- rule 2: missing args container -----------------------------------------------------

def test_missing_args_defaults_to_empty_and_the_result_is_accepted():
    """The CPU failure mode. Intent correct, reply present, rejected over an absent container."""
    r = _r('{"intent":"shutdown","reply":"Shutting down.","confidence":0.9}')
    assert r.parse_success, f'rejected a complete classification: {r.reason}'
    assert r.payload['args'] == {}


def test_a_missing_reply_is_still_rejected():
    """reply is CONTENT, not a container -- it is what he says out loud. Defaulting it would
    invent speech. Only args gets this treatment."""
    r = _r('{"intent":"arm_stow","args":{}}')
    assert r.parse_success is False


def test_a_missing_intent_is_still_rejected():
    r = _r('{"args":{},"reply":"ok","confidence":0.9}')
    assert r.parse_success is False


def test_args_of_the_wrong_type_is_still_rejected():
    """Defaulting a MISSING key is not licence to coerce a wrong one -- a string args means the
    model misunderstood the shape, and that is worth failing on."""
    r = _r('{"intent":"shutdown","args":"none","reply":"Night.","confidence":0.9}')
    assert r.parse_success is False


# --- the two rules together, which is how they actually arrive -------------------------

def test_placeholder_only_args_becomes_empty_and_passes():
    """The exact Hailo payload observed on 2026-09-14, end to end."""
    r = _r('{"intent":"arm_stow","args":{"object":"<the arm>"},'
           '"reply":"I will put the arm away.","confidence":0.8}')
    assert r.parse_success
    assert r.payload['intent'] == 'arm_stow'
    assert r.payload['args'] == {}


def test_normalisation_does_not_disturb_a_clean_payload():
    r = _r('{"intent":"battery","args":{},"reply":"80 percent.","confidence":0.9}')
    assert r.parse_success
    assert r.payload == {'intent': 'battery', 'args': {}, 'reply': '80 percent.',
                         'confidence': 0.9}
