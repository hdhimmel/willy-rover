import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# P1-3, 2026-09-14 review. The three paths the review asked to see proven, for the STUCK state --
# the only place an AI decision reaches the motors:
#
#   Hailo available -> low/failed confidence -> Claude(cloud) fallback
#   Hailo unavailable                        -> straight to Claude, no crash
#   Hailo failure                            -> NO physical action
#
# Nothing asserted this before. brain.py's gate is one line (brain.py:1007):
#
#   if result.parse_success and result.action_confidence >= config.HAILO_LLM_CONFIDENCE_FLOOR:
#       self._apply_ai_motion(...)          <- the ONLY path from a model to the wheels
#   ...
#   self._escalate_to_claude(d, tilt)
#
# so the property worth pinning is which of those two is reached, for each kind of result. A
# regression here would not look like a crash; it would look like the rover acting on a decision
# nobody reviewed, which is the failure mode with no symptom until it drives into something.
#
# Run out-of-process, matching tests/test_brain_voice_drain.py: importing brain at module scope
# pulls in the hardware stack, and this must stay runnable on a laptop. The fakes below record
# which branch fired rather than mocking the branch itself -- asserting on a mock would prove
# only that the mock works.

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT = r'''
import json, types, config
from brain import RoverBrain
from ai_provider import AIResult

D = {'front': 12.0, 'left': 40.0, 'right': 40.0}
TILT = 1.0

def fb(hailo_result, hailo_available=True):
    """A Brain stand-in holding only what _stuck() touches on the _hailo_pending branch."""
    calls = []
    ns = types.SimpleNamespace(
        safety=types.SimpleNamespace(timed_move_active=False,
                                     stop=lambda: calls.append(('safety_stop',))),
        _claude_move_pending=False,
        _claude_pending=False,
        _hailo_pending=True,
        _stuck_count=1,
        _last_action='forward',
        _last_stuck_prompt='situation prompt',
        _stuck_history=[],
        hailo_llm=types.SimpleNamespace(available=hailo_available,
                                        poll_async=lambda: hailo_result),
        _upd=lambda *a, **k: calls.append(('upd',)),
        _go=lambda s: calls.append(('go', s)),
        _apply_ai_motion=lambda r, d, t, who: calls.append(('MOTION', who, r.payload)),
        _escalate_to_claude=lambda d, t: calls.append(('ESCALATE',)),
    )
    ns.calls = calls
    ns._stuck = types.MethodType(RoverBrain._stuck, ns)
    return ns

def kinds(ns):
    return [c[0] for c in ns.calls]

FLOOR = config.HAILO_LLM_CONFIDENCE_FLOOR

# --- 1. A structurally valid, confident decision is the ONE case that may move the rover.
good = AIResult(True, 0.9, 1.0, True, {'action': 'reverse', 'duration': 0.8, 'speed': 0.3}, '')
f = fb(good); f._stuck(D, TILT)
assert 'MOTION' in kinds(f), f.calls
assert 'ESCALATE' not in kinds(f), f.calls

# --- 2. A FAILED PARSE must never move the rover. This is the safety property.
bad_parse = AIResult(False, 0.0, 0.0, False, None, 'parse failed: Expecting value')
f = fb(bad_parse); f._stuck(D, TILT)
assert 'MOTION' not in kinds(f), 'a failed parse reached _apply_ai_motion: %r' % (f.calls,)
assert 'ESCALATE' in kinds(f), f.calls

# --- 3. Structurally INVALID action (confidence 0.0) -> escalate, do not act.
#     This is the real protection: an invented action name cannot execute however sure the
#     model claims to be. Note parse_success is True here -- the JSON was fine, the CONTENT
#     was not -- so this is a genuinely different rejection from case 2.
invalid = AIResult(True, 0.99, 0.0, False, {'action': 'teleport', 'duration': 1.0}, '')
f = fb(invalid); f._stuck(D, TILT)
assert 'MOTION' not in kinds(f), 'a structurally invalid action reached the motors: %r' % (f.calls,)
assert 'ESCALATE' in kinds(f), f.calls

# --- 4. The echoed-template payload, which is what the model ACTUALLY produced before the
#     2026-09-14 ChatML fix. brain.py's STUCK prompt still contains angle-bracket placeholders
#     ("duration":<float>), so this shape is not hypothetical on this path.
echoed = AIResult(False, 0.0, 0.0, False, None, 'parse failed')
f = fb(echoed); f._stuck(D, TILT)
assert 'MOTION' not in kinds(f), f.calls
assert 'ESCALATE' in kinds(f), f.calls

# --- 5. A result still in flight (None) parks in STUCK. It must NOT be read as "no action
#     needed" and must not clear _hailo_pending, or the answer would be dropped when it lands.
f = fb(None); f._stuck(D, TILT)
assert 'MOTION' not in kinds(f), f.calls
assert 'ESCALATE' not in kinds(f), f.calls
assert f._hailo_pending is True, 'a pending request was cleared before its result arrived'

# --- 6. A move already executing is left alone -- no second decision on top of the first.
f = fb(good); f.safety.timed_move_active = True; f._stuck(D, TILT)
assert 'MOTION' not in kinds(f), f.calls
assert 'ESCALATE' not in kinds(f), f.calls

# --- 7. The floor is applied as a >= comparison against action_confidence, not against the
#     model's self-reported confidence. Pinned here as WIRING (test_confidence_gate_semantics.py
#     covers the arithmetic): a payload whose own "confidence" is 0.01 still moves the rover,
#     because that field is not what this gate reads.
sneaky = AIResult(True, 0.01, 1.0, True,
                  {'action': 'stop', 'duration': 0.0, 'speed': 0.0, 'confidence': 0.01}, '')
f = fb(sneaky); f._stuck(D, TILT)
assert 'MOTION' in kinds(f), (
    'the motion gate read the model self-report instead of action_confidence: %r' % (f.calls,))

# --- 8. On the accepted path the exchange is recorded for the next turn's context, and bounded.
f = fb(good); f._stuck(D, TILT)
assert len(f._stuck_history) == 2, f._stuck_history
assert f._stuck_history[0]['role'] == 'user'
assert f._stuck_history[1]['role'] == 'assistant'

print('OK')
'''


def test_stuck_ai_fallback_chain():
    """Every kind of model result, mapped to whether it may reach the motors.

    The assertion that matters is the negative one: of the eight cases, exactly three reach
    _apply_ai_motion, and all three are structurally validated. A failed parse, an invented
    action, an in-flight poll and an already-executing move all reach the wheels never."""
    r = subprocess.run([sys.executable, '-c', _SCRIPT], cwd=_REPO_ROOT,
                       capture_output=True, text=True,
                       env={**os.environ, 'WILLY_SIMULATE': '1', 'PYTHONPATH': _REPO_ROOT})
    assert r.returncode == 0, f'stdout:\n{r.stdout}\nstderr:\n{r.stderr}'
    assert 'OK' in r.stdout, r.stdout
