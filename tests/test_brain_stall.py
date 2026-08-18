import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-500-003 / Directive 5 (found 2026-08-18, via FRD v3.1's own gap audit): sensors.py's
# Encoders.stalled() existed since the baseline pass but had no caller anywhere in the codebase --
# Directive 5 was documented but never actually enforced. RoverBrain._check_stall() closes that.
# Same subprocess-under-WILLY_SIMULATE=1 approach as tests/test_brain_battery.py, for the same
# reason: importing brain.py in-process only works with the full hardware/display stack installed
# (pygame etc.), which this suite deliberately doesn't depend on. _check_stall() only reads
# self.motors.commanded / self.encoders.stalled() / self._stall_since, so a lightweight
# types.SimpleNamespace stand-in is used instead of a full RoverBrain.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import time,types,config
from brain import RoverBrain

class FakeMotors:
    def __init__(self,commanded): self._commanded=commanded
    @property
    def commanded(self): return dict(self._commanded)

class FakeEncoders:
    def __init__(self,stalled_wheels): self._stalled=set(stalled_wheels)
    def stalled(self,wheel,commanded): return commanded and wheel in self._stalled

def fb(commanded,stalled_wheels):
    ns=types.SimpleNamespace(_stall_since={})
    ns.motors=FakeMotors(commanded); ns.encoders=FakeEncoders(stalled_wheels)
    ns._check_stall=types.MethodType(RoverBrain._check_stall,ns)
    return ns

# 1. Not commanded -> never flagged even if the encoder reads near-zero (nothing driving it).
f=fb({"lf":False},stalled_wheels=["lf"])
assert f._check_stall()==[]

# 2. Commanded + stalled, but within the grace period -> not yet sustained (a wheel that just
#    started ramping up legitimately reads near-zero for a moment; that is not a stall).
f=fb({"lf":True,"rf":True},stalled_wheels=["lf"])
assert f._check_stall()==[]
assert "lf" in f._stall_since

# 3. Grace period elapsed -> now correctly reported.
f._stall_since["lf"]=time.time()-config.STALL_GRACE_S-0.01
assert f._check_stall()==["lf"]

# 4. Wheel recovers (encoder shows movement again) -> stall timer clears, no longer flagged.
f2=fb({"lf":True},stalled_wheels=[])
f2._stall_since["lf"]=time.time()-5.0
assert f2._check_stall()==[]
assert "lf" not in f2._stall_since

# 5. Independence -- only the actually-stalled wheel is reported, not its whole side.
f3=fb({"lf":True,"lm":True,"lr":True},stalled_wheels=["lm"])
f3._stall_since["lm"]=time.time()-config.STALL_GRACE_S-0.01
assert f3._check_stall()==["lm"]

print("STALL_CHECK_OK")
'''

def test_stall_detection_under_simulation():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'STALL_CHECK_OK' in result.stdout, (
        f'stall detection test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
