import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-300-003, applied to all faults not just a future E-stop (owner decision 2026-08-18): once
# a fault condition clears, brain.py no longer auto-resumes to IDLE -- it keeps braking and waits
# for an explicit operator action. RoverBrain._await_reset_or_resume() is the shared gate, used
# by SENSOR_FAULT/TILT_FAULT/STALL_FAULT recovery and -- since 2026-09-17 -- battery SAFE_MODE.
# That action is a screen tap (display.py's reset button) or the 'reset' voice intent (owner
# decision 2026-09-17); the voice half has its own coverage in tests/test_voice_reset.py. Same
# subprocess-under-WILLY_SIMULATE=1 approach as tests/test_brain_battery.py, for the same reason
# (importing brain.py in-process needs the full display/voice/vision stack this suite
# deliberately avoids depending on).

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types
from brain import RoverBrain

class FakeDisplay:
    def __init__(self,tapped=False): self._tapped=tapped; self.updates=[]
    def reset_tapped(self):
        v=self._tapped; self._tapped=False; return v
    def update_state(self,**kw): self.updates.append(kw)

class FakeSafety:
    def __init__(self): self.calls=[]
    def emergency_stop(self,reason): self.calls.append(reason)

def fb(tapped):
    # _motor_rail_lost and _bat_xcheck_flagged are read by _upd() (the motor-rail and
    # battery-sense banners, both added after this test was written). Unrelated to the reset
    # gate, but the fake has to carry them or _upd() raises.
    ns=types.SimpleNamespace(_state="SENSOR_FAULT",_motor_rail_lost=False,_bat_xcheck_flagged=False)
    ns.display=FakeDisplay(tapped); ns.safety=FakeSafety()
    ns._go=lambda s: setattr(ns,"_state",s)
    ns._upd=types.MethodType(RoverBrain._upd,ns)
    # Bound 2026-09-17: the gate now accepts a voice reset as well as a screen tap, so
    # _await_reset_or_resume() calls this. This namespace has no .voice at all, which is
    # deliberate -- it proves the screen-tap path still works with no voice subsystem present.
    ns._voice_reset_requested=types.MethodType(RoverBrain._voice_reset_requested,ns)
    ns._await_reset_or_resume=types.MethodType(RoverBrain._await_reset_or_resume,ns)
    return ns

# 1. Condition cleared but not tapped yet -> stays in the fault state, keeps braking (does not
#    silently resume just because the underlying sensor/tilt/stall reading recovered).
f=fb(tapped=False)
result=f._await_reset_or_resume("sensor fault",{"front":999},0.0,"CLEARED")
assert result is False
assert f._state=="SENSOR_FAULT"
assert f.safety.calls==["sensor fault cleared, awaiting operator reset"]
assert f.display.updates[-1]["awaiting_reset"] is True

# 2. Screen tapped -> resumes to IDLE and does not re-brake on the same call.
f2=fb(tapped=True)
result=f2._await_reset_or_resume("sensor fault",{"front":999},0.0,"CLEARED")
assert result is True
assert f2._state=="IDLE"
assert f2.safety.calls==[]

print("RESET_GATE_OK")
'''

def test_fault_recovery_waits_for_screen_tap():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'RESET_GATE_OK' in result.stdout, (
        f'reset-gate test failed\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}')
