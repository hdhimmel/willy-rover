import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# G-1 arm side, 2026-10-15. SW-A cuts the 6V arm converter's input and INA260 0x44 sits on that
# rail, so the cut is visible -- but nothing read it: a switched-off arm took every command and
# did nothing, with no reason given. brain._check_arm_rail() now sees it, stops any arm work and
# releases the PWM (so the arm cannot jump back to a held pose when power returns), and
# _arm_power_refused() turns arm requests away with a spoken reason.

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_arm_power_cut_is_seen_and_refused():
    script = '''
import types
from brain import RoverBrain
import config

class FakeCurrent:
    def __init__(self, v): self.v=v; self.asked=[]
    def rail(self, name):
        self.asked.append(name)
        return {'voltage_v': self.v[name], 'current_a': 0.0, 'power_w': 0.0}

class FakeArm:
    def __init__(self): self.releases=0
    def release(self): self.releases+=1

def brain_with(v, state='IDLE'):
    said=[]; went=[]; stops=[]
    ns = types.SimpleNamespace(_arm_rail_low_since=None, _arm_rail_lost=False, _state=state,
        current=FakeCurrent(v), arm=FakeArm(), _say=said.append, _go=went.append,
        retrieval=types.SimpleNamespace(active=False, abort=lambda why: None),
        safety=types.SimpleNamespace(emergency_stop=stops.append),
        _wave_seq=[('elbow',1500,0.2)], _wave_step=0, _wave_deadline=None,
        _release_after_seq=True, _pick=object(), _pick_after_stow=None)
    for n in ('_check_arm_rail','_arm_power_refused','_start_arm_sequence'):
        setattr(ns, n, types.MethodType(getattr(RoverBrain, n), ns))
    return ns, said, went, stops

on  = {'steering_5v': 4.99, 'arm_6v': 6.04, 'bus_12v': 11.2}
off = {'steering_5v': 4.99, 'arm_6v': 0.05, 'bus_12v': 11.2}

# healthy: nothing happens, and it reads the ARM rail
b,said,went,_ = brain_with(on)
b._check_arm_rail()
assert b.current.asked == ['arm_6v'] and not b._arm_rail_lost and not b._arm_power_refused()

# a cut mid-wave: grace first, then stop the sequence, go idle, release the PWM
b,said,went,stops = brain_with(off, state='WAVE')
b._check_arm_rail(); assert not b._arm_rail_lost
b._arm_rail_low_since -= config.ARM_RAIL_GRACE_S + 0.5
b._check_arm_rail()
assert b._arm_rail_lost and b.arm.releases == 1 and went == ['IDLE'] and b._wave_seq == []
assert b._pick is None and b._release_after_seq is False and stops
b._check_arm_rail(); assert b.arm.releases == 1          # once, not every tick

# arm requests are refused, with a reason
b._start_arm_sequence([('elbow', 1600, 0.2)])
assert went == ['IDLE'] and b._wave_seq == [] and any('arm power' in s for s in said)

# servo droop is not a cut
b,said,went,_ = brain_with({'steering_5v': 4.99, 'arm_6v': 5.4, 'bus_12v': 11.2})
for _ in range(3): b._check_arm_rail()
assert not b._arm_rail_lost

# power back: requests are accepted again
b,said,went,_ = brain_with(off)
b._arm_rail_lost = True; b.current.v = on
b._check_arm_rail()
assert not b._arm_rail_lost and not b._arm_power_refused()
print("OK")
'''
    env = dict(os.environ, WILLY_SIMULATE="1")
    r = subprocess.run([sys.executable, "-c", script], cwd=_REPO_ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_arm_rail_threshold_sits_between_a_cut_and_a_stall():
    assert 1.0 < config.ARM_RAIL_MIN_V < 5.0       # cut ~0 V; idle 6.04 V, stall droop ~5.5 V


def test_startup_check_names_switched_off_arm_power(monkeypatch):
    import types, startup_check
    b = types.SimpleNamespace(current=types.SimpleNamespace(
        is_healthy=True, rail=lambda n: {'voltage_v': 0.1, 'current_a': 0.0}))
    names = [n for n, _ in startup_check.failures(b)]
    assert 'arm power' in names
