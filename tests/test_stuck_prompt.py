import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

from ai_provider import build_stuck_prompt

# The STUCK motion prompt, pinned. Two separate problems are being prevented here.
#
# PROBLEM 1 -- ANGLE-BRACKET PLACEHOLDERS. The 2026-09-14 investigation established that this
# model copies "<the object>"-style placeholders into its output verbatim instead of substituting
# real values. That was the entire cause of the intent path's 0%. The fix was applied to the
# intent prompt and NOT swept into this one, which still carried "duration":<float>,
# "speed":<0.0-1.0>, "reason":"<60 chars>" and "confidence":<0.0-1.0>.
#
# Measured before the fix (experiments/results/2026-09-14-*-motion-baseline.json):
#   hailo  30 calls: 53% parsed, and of those EVERY SINGLE ONE answered "forward" -- including
#          fully blocked, boxed in on three sides, and 25 degrees of tilt. 33% of all calls were
#          both unsafe AND structurally valid, meaning they pass brain.py:1007 and drive the
#          rover with no cloud review.
#   cpu    10 calls: 10% parsed, 90% escalated.
#
# PROBLEM 2 -- TWO COPIES. The prompt existed as a literal inside brain.py and again inside the
# measurement harness. That is the same divergence trap that made the intent prompt untrustworthy
# (voice.py and llm_reliability_batch.py had to be manually kept character-identical, and a batch
# measured against a prompt the rover does not send is worthless). One builder now, imported by
# both, so they CANNOT drift.

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SITUATION = {'robot': {'room': None, 'pose': {'x': 1.0, 'y': 2.0, 'heading': 0.5}, 'battery': 78},
             'goal': 'find a clear path to continue roaming',
             'front_cm': 8.0, 'left_cm': 60.0, 'right_cm': 60.0, 'tilt_deg': 1.0,
             'stuck_count': 1, 'last_action': 'forward'}

ACTIONS = ('forward', 'reverse', 'turn_left', 'turn_right', 'stop', 'wait')

# "<float>", "<0.0-1.0>", "<60 chars>" -- a bracketed run with no whitespace-only content.
PLACEHOLDER = re.compile(r'<[^<>\s][^<>]{0,40}>')


def test_the_prompt_contains_no_angle_bracket_placeholders():
    """The regression that matters. This model copies placeholders instead of filling them in."""
    p = build_stuck_prompt(SITUATION)
    found = PLACEHOLDER.findall(p)
    assert not found, f'placeholder syntax still present: {found}'


def test_every_legal_action_is_named():
    """_apply_ai_motion executes exactly these six; anything else falls through to a stop. The
    model cannot pick a name it was never shown."""
    p = build_stuck_prompt(SITUATION)
    for a in ACTIONS:
        assert a in p, f'{a} missing from the prompt'


def test_the_safety_rules_appear_with_their_numbers():
    """_MOTION_SYSTEM states them, but the baseline showed the model driving forward into a
    blocked front anyway. Restating them in the user turn, next to the actual measured distance,
    is the cheap half of the fix."""
    p = build_stuck_prompt(SITUATION)
    assert '15' in p and '22' in p


def test_the_situation_is_embedded_as_json():
    p = build_stuck_prompt(SITUATION)
    assert 'front_cm' in p and '8.0' in p


def test_the_examples_show_more_than_one_action():
    """Anti-leakage. On the intent path the model copied the single worked example's object name
    ("newspaper") into unrelated answers. One example here would teach a constant -- and given the
    baseline answered "forward" to everything, a single forward example would be actively
    dangerous. At least two distinct actions must be demonstrated."""
    p = build_stuck_prompt(SITUATION)
    shown = {a for a in ACTIONS if f'"action":"{a}"' in p.replace(' ', '')}
    assert len(shown) >= 2, f'examples demonstrate only {shown}'


def test_the_examples_are_parseable_json_matching_the_schema():
    """An example that would itself fail _MOTION_SCHEMA teaches the wrong shape."""
    p = build_stuck_prompt(SITUATION)
    examples = re.findall(r'\{"action".*?\}', p.replace(' ', ''))
    assert examples, 'no worked example found'
    for e in examples:
        d = json.loads(e)
        assert d['action'] in ACTIONS
        assert isinstance(d['duration'], (int, float))
        assert isinstance(d['speed'], (int, float))
        assert 0.0 <= d['speed'] <= 1.0


def test_no_example_drives_forward_into_a_blocked_front():
    """The specific failure being corrected. A worked example showing 'forward' would reinforce
    exactly the behaviour that produced a 33% unsafe rate."""
    p = build_stuck_prompt(SITUATION)
    for e in re.findall(r'\{"action".*?\}', p.replace(' ', '')):
        d = json.loads(e)
        if d['action'] == 'forward':
            assert 'blocked' not in d.get('reason', '').lower()


def test_it_is_deterministic():
    """Same situation, same prompt. A prompt that varied per call would make every measurement
    in experiments/results/ unreproducible."""
    assert build_stuck_prompt(SITUATION) == build_stuck_prompt(SITUATION)


# --- the anti-divergence property -------------------------------------------------------

def _src(rel):
    with open(os.path.join(_REPO, rel), encoding='utf-8') as f:
        return f.read()


def test_brain_uses_the_shared_builder_rather_than_its_own_literal():
    """brain.py must not carry a second copy. This is the structural fix for a defect that has
    now recurred twice in this repo."""
    s = _src('brain.py')
    assert 'build_stuck_prompt' in s, 'brain.py no longer uses the shared prompt builder'
    assert '"reason":"<60 chars>"' not in s, 'the old placeholder literal is back in brain.py'


def test_the_measurement_harness_uses_the_same_builder():
    """A batch measured against a prompt the rover does not send is worthless -- the exact trap
    the intent batch had to be kept out of by hand."""
    s = _src('experiments/motion_reliability_batch.py')
    assert 'build_stuck_prompt' in s


def _docstring_node_ids(tree):
    """Ids of the string constants that are docstrings, so prose may quote the old prompt while
    live code may not. Several docstrings deliberately quote it to explain what was measured and
    why it changed -- deleting that history to satisfy a grep would be the wrong trade."""
    ids = set()
    import ast
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def test_no_live_code_still_builds_the_old_placeholder_prompt():
    """Repo-wide sweep, per CLAUDE.md's rule that a correction is not done until every copy of the
    old value is found. Deliberately AST-based rather than a text grep: the placeholder must be
    gone from executable string literals, while remaining quotable in docstrings that explain the
    2026-09-14 measurement. A plain grep cannot tell those apart, and the first version of this
    test could not either -- it flagged two docstrings that exist precisely to record the fix."""
    import ast
    offenders = []
    for root, _, files in os.walk(_REPO):
        # tests/ is excluded on purpose: test_malformed_model_output.py holds the echoed
        # template as FIXTURE DATA, to assert it is rejected. The rule being enforced is that no
        # code which BUILDS a prompt still contains the placeholder -- production and experiments.
        if any(skip in root for skip in ('.git', '__pycache__', 'venv', 'archive', 'results',
                                         os.sep + 'tests')):
            continue
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(root, name)
            if os.path.basename(path) == os.path.basename(__file__):
                continue
            src = open(path, encoding='utf-8', errors='ignore').read()
            if '0.0-1.0>' not in src:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            skip = _docstring_node_ids(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and id(node) not in skip and '0.0-1.0>' in node.value:
                    offenders.append(f'{os.path.relpath(path, _REPO)}:{node.lineno}')
    assert not offenders, f'old placeholder prompt still live in: {offenders}'
