import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

import voice
from voice import VoicePipeline

# P0, 2026-09-14 review. "For Willy, 'whoa whoa please stop right now' should never depend on an
# LLM correctly interpreting intent."
#
# THE MEASURED FAILURE. In the 96-call classification run that utterance was classified by the
# Hailo model as `where_are_you` at self-reported confidence 0.8, in 2 of 3 repeats
# (experiments/results/2026-09-14-failure-classification.md). It reached the model at all only
# because _fast_path() matches with fullmatch and the sentence form did not fit the pattern's
# prefix/trailer vocabulary. A safety-critical command was therefore one model misfire away from
# being understood as a question about which room the rover is in.
#
# THE APPROACH, and why it is not simply a broader matcher. The review was explicit: do not solve
# this by widening the stop matcher, because the negation protection must survive. It is also not
# solved by switching fullmatch to search -- tests/test_voice_fast_path.py requires
# "we should stop soon" NOT to fire, and a keyword search would break that. Discussing stopping
# is not commanding it.
#
# So the structure stays fullmatch, and what widens is the VOCABULARY of politeness/interjection
# prefixes and intensifier trailers around a narrow imperative core. That is fail-closed by
# construction: an unanticipated phrasing falls through to the LLM exactly as before, and no
# negation can be admitted because "don't" is not a prefix the matcher accepts. An explicit
# negation guard sits in front of it as well, as defence in depth for whoever widens the prefix
# list next.
#
# FAIL-SAFE DIRECTION. A false positive stops a rover nobody asked to stop: annoying, harmless.
# A false negative fails to stop a moving rover when a person asked it to. These are not
# symmetric, and where a judgement call exists this errs toward stopping.


@pytest.fixture
def fp():
    """_fast_path is pure -- it reads its argument and module-level patterns, never self -- so it
    is called unbound with None for self, matching tests/test_voice_fast_path.py. Constructing a
    real VoicePipeline would load Whisper and the wake model, which this has no need for."""
    return lambda text: (VoicePipeline._fast_path(None, text) or {}).get('intent')


# --- must stop: the review's own examples, plus the measured failure -------------------

MUST_STOP = [
    'stop',
    'please stop',
    'stop right now',
    'whoa stop',
    'whoa whoa please stop right now',          # the measured Hailo failure
    'I need you to stop moving immediately',    # also failed the batch
    'stop moving',
    'stop now',
    'halt',
    'freeze',
    'whoa',
    'hey stop',
    'willie stop',
    'willie, stop',
    'can you stop',
    'stop please',
    'just stop',
    'stop immediately',
    'stop right there',
    'hold it',
    'stand still',
    'emergency stop',
    'stop!',
    'whoa, stop!',
]


@pytest.mark.parametrize('utterance', MUST_STOP)
def test_natural_stop_language_hits_the_deterministic_path(fp, utterance):
    """None of these may depend on a model. Each must resolve to the stop intent in _fast_path,
    which voice.py dispatches straight to stop_requested without queueing."""
    assert fp(utterance) == 'stop', f'{utterance!r} did not reach the deterministic stop path'


# --- must NOT stop: negation, and discussion of stopping -------------------------------

MUST_NOT_STOP = [
    "don't stop",
    'do not stop',
    'dont stop',
    'never stop',
    "please don't stop",
    "don't stop following me",
    'do not stop moving',
    "I don't want you to stop",
    'we should stop soon',            # pinned by tests/test_voice_fast_path.py; discussion
    'you never stop talking',
    'what does a stop sign mean',
    'stop mapping',                   # a different intent entirely -- must not be hijacked
]


@pytest.mark.parametrize('utterance', MUST_NOT_STOP)
def test_negated_and_conversational_stop_language_does_not_fire(fp, utterance):
    """The protection the review asked to preserve. A false stop is harmless; a stop fired by the
    word "don't" would make the rover unusable and would teach the household to distrust it."""
    assert fp(utterance) != 'stop', f'{utterance!r} wrongly fired the stop path'


def test_stop_mapping_still_reaches_the_mapping_intent(fp):
    """Guards the specific hijack risk: 'stop' as a verb with a task object is not an emergency
    stop, and the widened matcher must not swallow it."""
    assert fp('stop mapping') == 'stop_map'


# --- the architectural property -------------------------------------------------------

def test_the_stop_path_does_not_consult_any_model(fp):
    """_fast_path runs before _interpret_local, so a stop never reaches the LLM. Asserted by
    construction: _fast_path takes no provider argument and Voice._fast_path is a pure function of
    its text."""
    import inspect
    sig = inspect.signature(VoicePipeline._fast_path)
    assert list(sig.parameters) == ['self', 'text'], (
        'the fast path gained a dependency; a stop must not be able to require a model')


def test_stop_is_dispatched_immediately_rather_than_queued():
    """voice.py sends stop straight to stop_requested instead of pending_commands. Queued
    commands wait for brain.py's tick and its IDLE gating; a stop cannot."""
    import inspect
    src = inspect.getsource(VoicePipeline)
    i = src.index("if name=='stop'")
    window = src[i:i + 600]   # wide enough to clear the branch comment; 300 cut mid-token
    assert 'stop_requested.set()' in window
    assert 'pending_commands.put' not in window


def test_every_review_example_is_covered_by_one_of_the_two_lists():
    """The review named specific phrases on both sides. If one is ever dropped from the lists
    above, this fails rather than silently reducing coverage."""
    required_stop = {'stop', 'please stop', 'stop right now', 'whoa stop',
                     'whoa whoa please stop right now'}
    required_not = {"don't stop", 'do not stop', 'never stop'}
    assert required_stop <= set(MUST_STOP)
    assert required_not <= set(MUST_NOT_STOP)
