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
    def __init__(self): self.pulses=[]; self.driven=set()
    def set_pulse(self,joint,us): self.pulses.append((joint,us)); self.driven.add(joint)
    def pulse(self,j): return 1500
    def was_driven(self,j): return j in self.driven

def fb():
    ns=types.SimpleNamespace(_state="IDLE",voice=types.SimpleNamespace(available=False))
    ns.arm=FakeArm()
    ns._go=lambda s: setattr(ns,"_state",s)
    for m in ("_wave","_start_wave","_shoulder_now","_start_arm_sequence"): setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
    ns._wave_plan=RoverBrain._wave_plan; ns._rest_plan=RoverBrain._rest_plan
    return ns

f=fb(); f._start_wave(); assert f._state=="WAVE"
# 1. one tick returns at once and drives one joint
t0=time.perf_counter(); f._wave({},0.0)
assert time.perf_counter()-t0<0.1 and len(f.arm.pulses)==1
# 2. re-ticking before the delay is a no-op
f._wave({},0.0); assert len(f.arm.pulses)==1
# 3. run it out
n=0
while f._state=="WAVE" and n<500:
    if f._wave_deadline is not None: f._wave_deadline=0
    f._wave({},0.0); n+=1
assert f._state=="IDLE"
P=f.arm.pulses; W=config.ARM_POSE_WAVE_HELLO; R=config.ARM_POSE_REST
# elbow opens BEFORE the shoulder moves; shoulder never jumps more than one step
assert P[0]==("elbow",W["elbow"])
sh=[us for j,us in P if j=="shoulder"]
steps=[abs(b-a) for a,b in zip([R["shoulder"]]+sh,sh)]
assert max(steps)<=config.ARM_WAVE_APPROACH_STEP_US, max(steps)
assert W["shoulder"] in sh
# the wave is the wrist PITCH between the verified limits, ARM_WAVE_CYCLES times
lo,hi=config.ARM_WAVE_WRIST_US
assert sum(1 for j,us in P if j=="wrist_pitch" and us==lo)==config.ARM_WAVE_CYCLES
# never touches wrist rotation, never centres the elbow
assert not any(j=="wrist_rot" for j,_ in P)
assert ("elbow",config.ARM_SERVO_CENTER_US) not in P
# returns: shoulder back to rest BEFORE the elbow closes
last_sh=max(i for i,(j,_) in enumerate(P) if j=="shoulder"); last_el=max(i for i,(j,_) in enumerate(P) if j=="elbow")
assert P[last_sh]==("shoulder",R["shoulder"]) and last_sh<last_el
assert P[-1]==("wrist_pitch",config.ARM_REST_WRIST_US)
# stow: from a raised shoulder, step down to rest -- never a single jump
plan=RoverBrain._rest_plan(750)
sh=[p[1] for p in plan if p[0]=="shoulder"]
assert max(abs(b-a) for a,b in zip([750]+sh,sh))<=config.ARM_WAVE_APPROACH_STEP_US and sh[-1]==R["shoulder"]
assert [p[0] for p in plan][-2:]==["elbow","wrist_pitch"]
print("WAVE_CHECK_OK")
'''

def test_wave_uses_the_verified_pose_and_is_non_blocking():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'WAVE_CHECK_OK' in result.stdout, (
        f'wave-hello non-blocking test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
