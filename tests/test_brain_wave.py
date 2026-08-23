import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Found 2026-08-18 alongside the FRD v3.1 doc adoption: brain.py's wave-hello gesture used to run
# through blocking time.sleep() calls (~1.5s total) inside a single tick(). That was accepted at
# the time on the reasoning "no systemd watchdog is actually configured, so nothing enforces a
# deadline on tick duration" -- but willy-rover.service does set WatchdogSec=500ms (confirmed the
# same day), so a single 1.5s tick gets the whole service killed and restarted by systemd
# mid-wave. Converted _wave_hello() into a non-blocking, tick-serviced step machine (_start_wave/
# _wave + a 'WAVE' FSM state), same pattern as retrieval_task.py's _grasp() fix earlier this
# session. Same subprocess-under-WILLY_SIMULATE=1 approach as tests/test_brain_battery.py, for
# the same reason (importing brain.py in-process needs the full display/voice/vision stack this
# suite deliberately avoids depending on).

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import time,types,config
from brain import RoverBrain

class FakeArm:
    def __init__(self): self.pulses=[]
    def set_pulse(self,joint,us): self.pulses.append((joint,us))

def fb():
    ns=types.SimpleNamespace(_wave_step=0,_wave_deadline=None,_state="WAVE",
                             _WAVE_OFFSETS_US=RoverBrain._WAVE_OFFSETS_US,
                             _WAVE_DELAY_S=RoverBrain._WAVE_DELAY_S)
    ns.arm=FakeArm()
    ns._go=lambda s: setattr(ns,"_state",s)
    ns._wave=types.MethodType(RoverBrain._wave,ns)
    return ns

# 1. A single call must return immediately -- this is the actual bug being fixed.
f=fb()
t0=time.perf_counter()
f._wave({},0.0)
assert time.perf_counter()-t0<0.1, "must not block the tick thread"
assert f._state=="WAVE"  # sequence not complete after one step
assert len(f.arm.pulses)==1

# 2. Re-ticking before the per-step delay elapses is a no-op (no duplicate pulses).
before=len(f.arm.pulses)
f._wave({},0.0)
assert len(f.arm.pulses)==before

# 3. Fast-forwarding through all steps completes the full 3-swing sequence and returns to IDLE,
#    ending centered (the arm must not settle at an offset).
steps=0
while f._state=="WAVE" and steps<20:
    f._wave({},0.0); steps+=1
    if f._wave_deadline is not None: f._wave_deadline=0
assert f._state=="IDLE", f._state
assert steps==7, steps  # 3 swings (2 pulses each) + final recenter
assert f.arm.pulses[-1]==("wrist_rot",config.ARM_SERVO_CENTER_US), f.arm.pulses[-1]

print("WAVE_CHECK_OK")
'''

def test_wave_is_non_blocking_and_completes_centered():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'WAVE_CHECK_OK' in result.stdout, (
        f'wave-hello non-blocking test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
