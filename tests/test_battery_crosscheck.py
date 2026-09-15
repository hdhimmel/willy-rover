import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# brain.py::_check_battery_crosscheck(), added 2026-09-15 after the ADS1115 divider went open and
# read 0.09V while the +12V bus INA260 read 10.97V -- simultaneously, for hours, with nothing in
# the system comparing them. That was noticed because a human read a diagnostics run.
#
# THE CASE THIS ACTUALLY DEFENDS IS NOT THAT ONE. A 0.09V reading is already rejected:
# accept_battery_raw() refuses anything under BAT_IMPLAUSIBLE_V=5.0 and brain.py escalates the
# resulting staleness through SENSOR_FAULT. The fault that gets through is the one that CLEARS
# that floor -- a divider drifting or partially failing so it reports 7.5V from an 11.2V pack.
# That is plausible, so it is adopted, and it walks the tier ladder to rth, then safe, then
# shutdown. Willie goes home or powers off for no reason and the log blames the battery. The
# test named ...plausible_but_wrong... below is the one that matters.
#
# Detection only, deliberately: it logs and shows on the face and never touches the tier. Adding
# an automatic halt path driven by battery sensing, while battery sensing is the thing under
# suspicion, is how you get a rover that refuses to move for reasons nobody understands.

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT = '''
import types, time
from brain import RoverBrain
import config

class FakeADC:
    def __init__(self, volts, healthy=True):
        self.battery_volts = volts; self.is_healthy = healthy

class FakeCurrent:
    def __init__(self, bus_v, raises=False): self._v = bus_v; self._raises = raises; self.asked = []
    def rail(self, name):
        self.asked.append(name)
        if self._raises: raise OSError("monitor unreadable")
        if name not in ("steering_5v", "arm_6v", "bus_12v"):
            raise KeyError("unknown rail %r" % name)
        return {"voltage_v": self._v, "current_a": 0.0, "power_w": 0.0}

def mk(adc_v, bus_v, adc_healthy=True, raises=False):
    ns = types.SimpleNamespace(_bat_xcheck_since=None, _bat_xcheck_flagged=False)
    ns.adc = FakeADC(adc_v, adc_healthy)
    ns.current = FakeCurrent(bus_v, raises)
    ns._check_battery_crosscheck = types.MethodType(RoverBrain._check_battery_crosscheck, ns)
    return ns

def age(ns):
    """Push the pending timer past the grace period."""
    ns._bat_xcheck_since -= (config.BAT_CROSSCHECK_GRACE_S + 1.0)

# 1. AGREEMENT. The real 2026-09-15 numbers once the divider is repaired: pack 11.36V read by the
#    divider, bus 11.17V downstream of the fuse and switch. A 0.19V delta is the drop, not a fault.
b = mk(11.36, 11.17)
assert b._check_battery_crosscheck() == ""
assert b._bat_xcheck_flagged is False
assert b.current.asked == ["bus_12v"], b.current.asked

# 2. THE CASE THAT MATTERS: plausible but wrong. 7.5V clears BAT_IMPLAUSIBLE_V so nothing else in
#    the system objects -- but the pack is really 11.2V and the tier ladder is being walked toward
#    shutdown on a lie.
b = mk(7.5, 11.0)
assert b._check_battery_crosscheck() == ""        # first call only starts the grace timer
assert b._bat_xcheck_since is not None
assert b._bat_xcheck_flagged is False
age(b)
msg = b._check_battery_crosscheck()
assert b._bat_xcheck_flagged is True, "a 3.5V disagreement must be reported"
assert msg and "7.50" in msg and "11.00" in msg, msg
assert 7.5 > config.BAT_IMPLAUSIBLE_V, "the whole point is that this value passes the floor"

# 3. GRACE PERIOD. A single tick of disagreement is not a report -- motor inrush sags the bus.
b = mk(7.5, 11.0)
for _ in range(4):
    assert b._check_battery_crosscheck() == ""
assert b._bat_xcheck_flagged is False

# 4. BUS DOWN -> SKIP, NOT REPORT. The bus monitor sits downstream of SW-M, so throwing the motor
#    cut collapses it. Comparing then would turn every E-stop into "your battery sensor is lying".
#    This is also what makes the check correct regardless of which side of SW-M it is really on.
b = mk(11.3, 0.0)
assert b._check_battery_crosscheck() == ""
assert b._bat_xcheck_flagged is False
assert b._bat_xcheck_since is None, "a dead bus must CLEAR the pending timer, not accumulate it"

#    And it must not latch a flag mid-way through a cut: pending, then the cut lands.
b = mk(7.5, 11.0)
b._check_battery_crosscheck()
assert b._bat_xcheck_since is not None
b.current._v = 0.0
b._check_battery_crosscheck()
assert b._bat_xcheck_since is None

# 5. STALE ADC -> SKIP. accept_battery_raw()/_check_health() own that path; comparing a held-over
#    value against a live one manufactures a disagreement that is not real.
b = mk(0.09, 11.0, adc_healthy=False)
assert b._check_battery_crosscheck() == ""
assert b._bat_xcheck_flagged is False
assert b.current.asked == [], "must not even read the rail when the ADC is already stale"

# 6. UNREADABLE MONITOR -> SKIP rather than raise into the 20Hz tick loop.
b = mk(11.3, 11.1, raises=True)
assert b._check_battery_crosscheck() == ""
assert b._bat_xcheck_flagged is False

# 7. RECOVERY clears the flag, so a repaired divider stops shouting without a restart.
b = mk(7.5, 11.0)
b._check_battery_crosscheck(); age(b); b._check_battery_crosscheck()
assert b._bat_xcheck_flagged is True
b.adc.battery_volts = 11.2
assert b._check_battery_crosscheck() == ""
assert b._bat_xcheck_flagged is False
assert b._bat_xcheck_since is None

print("OK")
'''


def test_crosscheck_behaviour():
    env = dict(os.environ, WILLY_SIMULATE="1")
    r = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=_REPO_ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_tolerance_clears_the_real_measured_drop_but_not_a_real_fault():
    """The threshold has to sit above the legitimate pack-vs-bus delta and below a fault.

    Measured 2026-09-15: pack 11.36V (meter) against bus 11.174V = 0.19V at 16mA idle. Under
    motor load that drop grows and nobody has measured it yet -- M-1/E-1 will, and this value
    should be tightened then. These bounds are what stops it being tightened into false alarms
    or loosened into uselessness."""
    assert config.BAT_CROSSCHECK_MAX_DIFF_V > 0.19, "must clear the measured idle drop"
    assert config.BAT_CROSSCHECK_MAX_DIFF_V < 3.0, (
        "a divider reading 7.5V from an 11.2V pack is 3.7V out and is the case this exists for; "
        "a tolerance at or above 3.0V starts letting that class through")
    assert config.BAT_CROSSCHECK_GRACE_S >= 1.0, "must ride out motor inrush"


def test_it_is_detection_only():
    """No branch of this may stop, fault, or move the battery tier. _check_motor_rail() set the
    precedent and the reasoning is the same: do not add an automatic halt path driven by the
    sensor that is currently under suspicion."""
    import inspect, brain
    src = inspect.getsource(brain.RoverBrain._check_battery_crosscheck)
    for forbidden in ("emergency_stop", "_go(", "_bat_tier", "_update_bat_tier", "abort("):
        assert forbidden not in src, (
            "_check_battery_crosscheck() must stay detection-only; found %r" % forbidden)
