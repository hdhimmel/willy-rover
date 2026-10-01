import os,sys,subprocess

# FRD gap audit, 2026-10-01 (FR-300-004, controller failure). DriveBase._ramp_loop wrote throttles
# with no try/except: one I2C OSError ended the thread, after which every ramped stop() did
# nothing and nothing noticed. Now a failed write is recorded, the other wheels are still
# written, the thread survives, and is_healthy goes false so brain.py's _check_health()
# escalates to SENSOR_FAULT. Subprocess for the same reason as test_motor_sign.py.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import time,motors

class Flaky:
    def __init__(self): self.fail=True; self._t=None
    @property
    def throttle(self): return self._t
    @throttle.setter
    def throttle(self,v):
        if self.fail: raise OSError(121,'Remote I/O error')
        self._t=v

d=motors.DriveBase()
assert d.is_healthy
bad=Flaky(); d._motors["lf"]=bad
d.forward(0.6); time.sleep(0.3)
assert d._thread.is_alive(), "one failed write killed the ramp thread"
assert not d.is_healthy, "a failing driver must report unhealthy"
assert d._motors["lm"].throttle>0, "the other wheels must still be driven"

d.brake()                                   # must not raise, must still brake the rest
assert d._motors["rf"].throttle==0.0

bad.fail=False; d.stop(); time.sleep(1.3)
assert d.is_healthy, "health returns once writes succeed again"
d.cleanup()
print("DRIVE_FAULT_OK")
'''

def test_a_failed_motor_write_is_survived_and_reported():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                     capture_output=True,text=True,timeout=30)
    assert 'DRIVE_FAULT_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}'
