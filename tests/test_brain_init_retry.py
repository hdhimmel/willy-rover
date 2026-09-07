import os,sys,subprocess

sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# brain.py::_init_device exists to survive a transient at process startup: constructing many I2C
# devices back-to-back can sag the bus enough that a device's own construction fails even though
# the bus is healthy moments later (found 2026-08-21). It retried on OSError only.
#
# That misses the case that actually crash-looped the service on 2026-09-07. Adafruit's
# I2CDevice.__probe_for_device() raises **ValueError**, not OSError, when nothing ACKs at an
# address -- so "the isolated rail has not come up yet" propagated on the first attempt with zero
# retries, while the guard that was supposed to cover exactly that scenario never engaged.
#
# Same subprocess-under-WILLY_SIMULATE=1 approach as tests/test_brain_stall.py, for the same
# reason: importing brain.py in-process needs the full hardware/display stack.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import time
from brain import _init_device

# 1. ValueError -- the "device not on the bus (yet)" case. This is what Adafruit raises when an
#    address does not ACK, and it is the one that took the service down on 2026-09-07.
calls={"n":0}
def flaky_valueerror():
    calls["n"]+=1
    if calls["n"]<3: raise ValueError("No I2C device at address: 0x60")
    return "device"
assert _init_device(flaky_valueerror,"motors",attempts=4,delay_s=0.01)=="device"
assert calls["n"]==3, f"expected 3 attempts, got {calls['n']}"

# 2. OSError -- the original transient case must keep working.
calls2={"n":0}
def flaky_oserror():
    calls2["n"]+=1
    if calls2["n"]<2: raise OSError(121,"Remote I/O error")
    return "device"
assert _init_device(flaky_oserror,"imu",attempts=4,delay_s=0.01)=="device"
assert calls2["n"]==2

# 3. A genuinely absent device still fails rather than hanging or returning None -- retrying
#    forever would hide real hardware faults behind a silent startup stall.
calls3={"n":0}
def always_missing():
    calls3["n"]+=1
    raise ValueError("No I2C device at address: 0x60")
try:
    _init_device(always_missing,"motors",attempts=3,delay_s=0.01)
except ValueError:
    pass
else:
    raise AssertionError("a permanently absent device must still raise")
assert calls3["n"]==3, f"expected exhausting 3 attempts, got {calls3['n']}"

# 4. Unrelated exception types are NOT swallowed -- a bug in a constructor must surface
#    immediately, not be retried four times and then re-raised.
calls4={"n":0}
def broken():
    calls4["n"]+=1
    raise KeyError("bug in ctor")
try:
    _init_device(broken,"display",attempts=4,delay_s=0.01)
except KeyError:
    pass
else:
    raise AssertionError("unexpected exception types must propagate")
assert calls4["n"]==1, f"must not retry unrelated errors, got {calls4['n']} attempts"

print("INIT_RETRY_OK")
'''


def test_init_device_retries_missing_device_not_just_io_errors():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                          capture_output=True,text=True,timeout=30)
    assert 'INIT_RETRY_OK' in result.stdout, (
        f'_init_device retry test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
