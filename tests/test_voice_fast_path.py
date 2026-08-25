import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import voice

# The fast path is the difference between an ~8.7s answer and a ~30s one: a miss falls through
# to the local LLM. That makes an unmatched phrasing look like a broken rover rather than a slow
# one, and it is why this file exists -- the same bug shape has now landed three times:
#   2026-08-21  a clipped first word turned "what time is it" into "time is it" -> 84.9s
#   2026-08-23  "what's today's day" missed: no alternative put "today's" before "day"
#   2026-08-25  "What is the current time?" missed: `(?:the )?current time` is a bare
#               alternative, so nothing allows "what is" in front of it. Live log 08:19:15,
#               30s in the LLM, immediately after "What is today's date?" answered in 8.7s.
# Each was fixed by appending one more surface form. None was covered by a test. This file
# covers the behaviour instead: a phrasing a person would actually use must resolve to its
# intent, whichever alternative happens to carry it.
#
# _fast_path() is pure -- it reads its argument and module-level patterns, never self -- so it is
# called unbound with None for self. Constructing a real VoicePipeline would load Whisper and the
# wake model, which this has no need for.
_fast=lambda text: voice.VoicePipeline._fast_path(None,text)

def _intent(text):
    r=_fast(text)
    return None if r is None else r['intent']

# Phrasings that regressed live. Each is a real utterance, not a hypothetical.
@pytest.mark.parametrize('utterance',[
    'What is the current time?',   # 2026-08-25, the one that started this
    "What's the current time?",
    'Willie, what is the current time?',
    'what is the current time',
    'tell me the current time',
])
def test_current_time_phrasings_reach_the_time_intent(utterance):
    assert _intent(utterance)=='time'

@pytest.mark.parametrize('utterance',[
    'What is the current date?',
    "What's the current date?",
    "What's the current day?",
    'tell me the current date',
])
def test_current_date_phrasings_reach_the_date_intent(utterance):
    assert _intent(utterance)=='date'

# Already-working phrasings, pinned so a rewrite of the patterns cannot quietly drop them.
@pytest.mark.parametrize('utterance,intent',[
    ('what time is it','time'),
    ('What is the time?','time'),
    ("what's the time",'time'),
    ('current time','time'),
    ('time is it','time'),               # 2026-08-21 clipped-first-word case
    ("What is today's date?",'date'),
    ("what's today's day",'date'),       # 2026-08-23 case
    ("today's date",'date'),
    ('what day is it today','date'),
])
def test_previously_working_phrasings_still_match(utterance,intent):
    assert _intent(utterance)==intent

# fullmatch is load-bearing: a command embedded in a longer sentence must fall through to the LLM
# rather than fire on a fragment. Motion intents are the ones where a false positive actually
# moves the rover, so they are pinned hardest.
@pytest.mark.parametrize('utterance',[
    "don't stop",
    'we should stop soon',
    'do not turn left',
    'what is the current temperature',   # 'current' alone must not imply time or date
    'what is the weather',
])
def test_non_commands_fall_through_rather_than_matching(utterance):
    assert _intent(utterance) not in ('stop','turn_left','time','date')


# Arm presets, added 2026-08-25 after Jules pointed out that "center arm" fell through to the
# ~30s LLM. Composed as verb x subject rather than enumerated, for the same reason the time and
# date patterns were: listing surface forms is what let this class of gap recur three times.
# Note brain.py currently aliases BOTH arm_home and arm_stow to arm.center_all(), since no
# calibrated stow pose exists yet (section 20.6) -- the intents are distinct, the behaviour is
# not yet.
@pytest.mark.parametrize('utterance',[
    'center arm',
    'arm center',
    'center the arm',
    'centre your arm',        # the rover's owner writes British English in the docs
    'arm home',               # already worked; pinned so the rewrite cannot drop it
    'reset your arm',
    'home the arm',
])
def test_arm_home_phrasings_reach_the_arm_home_intent(utterance):
    assert _intent(utterance)=='arm_home'

@pytest.mark.parametrize('utterance',[
    'stow the arm',           # already worked; pinned
    'put your arm away',
    'arm away',
    'stow arm',
    'park the arm',
])
def test_arm_stow_phrasings_reach_the_arm_stow_intent(utterance):
    assert _intent(utterance)=='arm_stow'

@pytest.mark.parametrize('utterance',[
    "don't stow the arm",
    'do not center the arm',
])
def test_negated_arm_commands_fall_through(utterance):
    assert _intent(utterance) not in ('arm_home','arm_stow')
