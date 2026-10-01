import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')

import pytest
import config
from sensors import Encoders

# R5 low, owner decision 2026-10-01: WARN AND NAME THE CAUSE, never a new stop. R5 is the 3.3V
# rail that powers the six Hall encoders and nothing else. On 2026-08-25 it sagged and looked
# exactly like six dead channels; today that would surface as a "wheel stall" emergency stop
# blaming the wheels. The existing stall and health checks still stop motion if the encoders
# actually drop out -- this only makes the status and the stop reason point at the rail.
# Nobody has measured the voltage these encoders stop working at, so there is deliberately no
# threshold here that stops the rover.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Link:
    def __init__(self,fields): self.f=fields
    def fresh(self,kind,max_age_s): return self.f


@pytest.fixture
def enc():
    e=Encoders.__new__(Encoders)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config,'SIMULATE_HARDWARE',False)
        yield e


def _frame(mv,flags):
    return ['E','1','0','0','0','0','0','0','0',str(mv),str(flags)]


def test_r5_low_reads_pico_a_flag(enc):
    enc._link=_Link(_frame(2900,0x02)); assert enc.r5_low is True
    enc._link=_Link(_frame(3390,0x00)); assert enc.r5_low is False
    enc._link=_Link(_frame(2900,0x03)); assert enc.r5_low is True    # alongside Phase-B bit
    enc._link=_Link(_frame(3390,0x01)); assert enc.r5_low is False   # Phase-B bit is not R5


def test_a_stale_link_is_not_r5_low(enc):
    """No frame means nothing is known about R5. The link's own health check owns that."""
    enc._link=_Link(None); assert enc.r5_low is False


_SCRIPT='''
import time,types,config
from brain import RoverBrain

class FakeEnc:
    def __init__(self): self.r5_low=False; self.r5_millivolts=3390

def fb():
    ns=types.SimpleNamespace(_r5_low_since=None,_r5_low=False,encoders=FakeEnc())
    ns._check_r5=types.MethodType(RoverBrain._check_r5,ns)
    ns._stall_reason=types.MethodType(RoverBrain._stall_reason,ns)
    return ns

f=fb()
assert f._check_r5()=="" and f._r5_low is False

# A single low frame is not a warning -- grace first, same shape as the motor-rail check.
f.encoders.r5_low=True; f.encoders.r5_millivolts=2900
assert f._check_r5()=="" and f._r5_low is False
f._r5_low_since=time.time()-config.ENCODER_R5_GRACE_S-0.01
msg=f._check_r5()
assert f._r5_low is True and "2900" in msg, msg

# The stall stop now names the rail, not the wheels.
r=f._stall_reason(["lf","rf"])
assert "R5" in r and "2900" in r, r

# Recovers.
f.encoders.r5_low=False; f.encoders.r5_millivolts=3380
assert f._check_r5()=="" and f._r5_low is False and f._r5_low_since is None
assert f._stall_reason(["lf"])=="wheel stall: ['lf']"
print("R5_OK")
'''

def test_brain_warns_on_r5_low_and_names_it_in_the_stall_reason():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=60)
    assert 'R5_OK' in result.stdout, (
        f'--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}')
