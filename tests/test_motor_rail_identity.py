import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Found live 2026-09-15. brain.py::_check_motor_rail() is the only software observability there
# is for a motor-power cut (G-1: the E-stop has no sense line). It read the CurrentMonitor rail
# named 'motor' -- and that name pointed at INA260 0x44, which the owner confirmed is the 6V ARM
# servo rail, not the +12V motor bus.
#
# That broke the feature in BOTH directions at once, which is why it deserves its own file:
#
#   * A real cut was UNDETECTABLE. Killing motor power collapses the +12V bus while the 6V arm
#     rail carries on at ~6.04V -- comfortably above MOTOR_RAIL_MIN_V -- so the check returned
#     "fine" precisely when it was supposed to fire. A protective mechanism inert while
#     appearing configured: the same shape as the Type=simple watchdog and the __MEASURE__
#     placeholders.
#   * FALSE positives were 43mV away. The arm rail idles at 6.043V against a 6.0V threshold, so
#     ordinary arm-servo droop would log "MOTOR POWER LOST" with the motor bus perfectly healthy.
#
# The root cause was a NAME that encoded a consumer ("motor") rather than a property of the wire.
# When the INA260s were physically relocated (see config.py's 2026-09-15 note), the name silently
# stopped describing the hardware and nothing failed loudly. These tests pin the identity itself,
# not just the behaviour, so a future relocation has to come past them.

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_rail_keys_name_voltages_not_consumers():
    """The keys must state the rail's voltage. 'motor'/'pi'/'servo' are exactly the names that
    went stale when the wire moved; a voltage cannot drift away from the hardware that way."""
    from sensors import CurrentMonitor
    assert set(CurrentMonitor._RAILS) == {'steering_5v', 'arm_6v', 'bus_12v'}
    for stale in ('motor', 'pi', 'servo'):
        assert stale not in CurrentMonitor._RAILS, (
            "%r is back. That name is what let _check_motor_rail() watch the arm supply for "
            "three weeks -- see config.py's INA260 identity note." % stale)


def test_rail_keys_map_to_the_addresses_the_owner_confirmed():
    """0x40 = R2 5V, 0x44 = R3 6V arm, 0x45 = +12V bus. Owner-stated 2026-09-15; measured
    4.986V / 6.043V / 11.174V against a metered pack of 11.36V."""
    from sensors import CurrentMonitor
    assert CurrentMonitor._RAILS['steering_5v'] == 0x40
    assert CurrentMonitor._RAILS['arm_6v'] == 0x44
    assert CurrentMonitor._RAILS['bus_12v'] == 0x45
    assert config.INA260_5V_ADDR == 0x40
    assert config.INA260_ARM_6V_ADDR == 0x44
    assert config.INA260_BUS_12V_ADDR == 0x45


def test_motor_rail_check_reads_the_12v_bus_and_not_the_arm_rail():
    """The behavioural half: _check_motor_rail() must ask for 'bus_12v'.

    Asserting on the requested key rather than on the return value is deliberate -- a version
    reading 'arm_6v' would still return '' here and look perfectly healthy, which is the entire
    bug. The fake records what was asked for, and fails loudly on anything else."""
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
    ns = types.SimpleNamespace(_motor_rail_low_since=None, _motor_rail_lost=False)
    ns.current = FakeCurrent(volts)
    ns._check_motor_rail = types.MethodType(RoverBrain._check_motor_rail, ns)
    return ns

# The exact live situation on 2026-09-15: motor bus healthy, arm rail sitting at 6.043V.
healthy = {'steering_5v': 4.986, 'arm_6v': 6.043, 'bus_12v': 11.174}
b = brain_with(healthy)
b._check_motor_rail()
assert b.current.asked == ['bus_12v'], b.current.asked
assert b._motor_rail_lost is False

# A REAL motor-power cut: +12V collapses, the arm rail is untouched. The old code read the arm
# rail, saw 6.043V > 6.0V, and reported nothing. This must now detect it.
cut = {'steering_5v': 4.986, 'arm_6v': 6.043, 'bus_12v': 0.0}
b2 = brain_with(cut)
b2._check_motor_rail()                      # first call only starts the grace timer
assert b2._motor_rail_low_since is not None
b2._motor_rail_low_since -= (config.MOTOR_RAIL_GRACE_S + 1.0)
msg = b2._check_motor_rail()
assert b2._motor_rail_lost is True, "a collapsed +12V bus must be detected"
assert msg, "a detected cut must return a status string"

# Arm-servo droop below 6.0V must NOT be mistaken for a motor cut, because the arm rail is not
# the motor rail. Under the old wiring of this check, this was a guaranteed false positive.
droop = {'steering_5v': 4.986, 'arm_6v': 5.4, 'bus_12v': 11.174}
b3 = brain_with(droop)
for _ in range(3):
    b3._check_motor_rail()
assert b3._motor_rail_lost is False, "arm droop is not a motor-power cut"

print("OK")
'''
    env = dict(os.environ, WILLY_SIMULATE="1")
    r = subprocess.run([sys.executable, "-c", script], cwd=_REPO_ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_threshold_still_suits_a_12v_bus():
    """MOTOR_RAIL_MIN_V was written for the +12V bus ('well below any real operating voltage
    (the bus measured 11.3-11.4V) but above the ~0V a genuine cut produces') and is correct as
    it stands. It is only the rail selection that was wrong -- so if someone 'fixes' this by
    moving the threshold instead, that is the wrong repair and this catches it."""
    assert config.MOTOR_RAIL_MIN_V == 6.0
    assert config.MOTOR_RAIL_MIN_V < 11.174      # clears the measured idle bus voltage
    assert config.MOTOR_RAIL_MIN_V > 1.0         # still well above the ~0V of a real cut
