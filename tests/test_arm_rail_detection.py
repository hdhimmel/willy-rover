import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Software Design S-1: a SW-A cut collapses the 6V arm rail and was readable on INA260 0x44
# (rail key 'arm_6v') but nothing read it for that purpose. _check_arm_rail() closes the gap,
# same shape as the existing _check_motor_rail() (see test_motor_rail_identity.py) --
# detection only, never a stop, fault, or state change.

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_arm_rail_check_reads_the_arm_rail_and_detects_a_cut():
    script = '''
import types
from brain import RoverBrain
import config

class FakeCurrent:
    def __init__(self, volts): self.asked=[]; self._v=volts
    def rail(self, name):
        self.asked.append(name)
        if name not in ('steering_5v','arm_6v','bus_12v'):
            raise KeyError("unknown rail %r -- stale name?" % name)
        return {'voltage_v': self._v[name], 'current_a': 0.0, 'power_w': 0.0}

def brain_with(volts):
    ns = types.SimpleNamespace(_arm_rail_low_since=None, _arm_rail_lost=False)
    ns.current = FakeCurrent(volts)
    ns._check_arm_rail = types.MethodType(RoverBrain._check_arm_rail, ns)
    return ns

# Arm rail healthy at its measured idle voltage, motor bus also healthy.
healthy = {'steering_5v': 4.986, 'arm_6v': 6.043, 'bus_12v': 11.174}
b = brain_with(healthy)
b._check_arm_rail()
assert b.current.asked == ['arm_6v'], b.current.asked
assert b._arm_rail_lost is False

# A SW-A cut: the arm rail collapses while the motor bus is untouched.
cut = {'steering_5v': 4.986, 'arm_6v': 0.0, 'bus_12v': 11.174}
b2 = brain_with(cut)
b2._check_arm_rail()                      # first call only starts the grace timer
assert b2._arm_rail_low_since is not None
b2._arm_rail_low_since -= (config.ARM_RAIL_GRACE_S + 1.0)
msg = b2._check_arm_rail()
assert b2._arm_rail_lost is True, "a collapsed arm rail must be detected"
assert msg, "a detected cut must return a status string"

# Ordinary arm-servo droop must not be mistaken for a cut -- the margin is the whole point
# of ARM_RAIL_MIN_V being well below the idling ~6.043V.
droop = {'steering_5v': 4.986, 'arm_6v': 5.4, 'bus_12v': 11.174}
b3 = brain_with(droop)
for _ in range(3):
    b3._check_arm_rail()
assert b3._arm_rail_lost is False, "ordinary arm-servo droop is not an arm-power cut"

# Restoring power must clear the flag and log a restoration.
b2._check_arm_rail.__self__.current = FakeCurrent({'steering_5v': 4.986, 'arm_6v': 6.043, 'bus_12v': 11.174})
b2._check_arm_rail()
assert b2._arm_rail_lost is False, "restored power must clear the flag"

print("OK")
'''
    env = dict(os.environ, WILLY_SIMULATE="1")
    r = subprocess.run([sys.executable, "-c", script], cwd=_REPO_ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_arm_rail_threshold_clears_droop_but_not_idle():
    """ARM_RAIL_MIN_V must sit strictly between a real cut (~0V) and the idling rail (6.043V),
    with enough margin above 0 to not be mistaken for a healthy near-zero reading."""
    assert 1.0 < config.ARM_RAIL_MIN_V < 6.043
    assert config.ARM_RAIL_GRACE_S > 0


def test_arm_rail_prefix_shows_on_the_face():
    """_upd() must surface a lost arm rail the same way it surfaces a lost motor rail --
    information prepended to the status string, never its own FSM state."""
    import inspect, brain
    src = inspect.getsource(brain.RoverBrain._upd)
    assert '_arm_rail_lost' in src
    assert 'ARM POWER LOST' in src
