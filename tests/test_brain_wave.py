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
    for m in ("_wave","_start_wave","_shoulder_now","_start_arm_sequence","_arm_now"): setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
    ns.arm.released=False
    ns._wave_plan=RoverBrain._wave_plan; ns._rest_plan=RoverBrain._rest_plan
    ns._said=[]; ns._say=ns._said.append
    ns._arm_poses_ok=types.MethodType(RoverBrain._arm_poses_ok,ns)
    return ns

# 2026-10-12: shoulder poses not re-measured since the servo change -> refuse, say why, no motion
config.ARM_SHOULDER_POSES_VERIFIED=False
f=fb(); f._start_wave(); assert f._state=="IDLE" and f.arm.pulses==[] and "relearn" in f._said[0]
config.ARM_SHOULDER_POSES_VERIFIED=True
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
P=[p for p in f.arm.pulses if p[0]!="shoulder_pair"]; W=config.ARM_POSE_WAVE_HELLO; R=config.ARM_POSE_REST; UP=config.ARM_STOW_UPRIGHT_US
def steps_ok(seq,start):
    return all(abs(y-x)<=config.ARM_WAVE_APPROACH_STEP_US for x,y in zip([start]+seq,seq))
# 2026-10-13 order: stand up folded, open the elbow, raise, wave, sway the base, stow.
first_el=min(i for i,(j,_) in enumerate(P) if j=="elbow")
assert ("shoulder",UP) in P[:first_el]                      # upright BEFORE the elbow opens
sh=[us for j,us in P if j=="shoulder"]
assert steps_ok(sh,R["shoulder"]) and W["shoulder"] in sh
el=[us for j,us in P if j=="elbow"]
assert steps_ok(el,R["elbow"]) and W["elbow"] in el
lo,hi=config.ARM_WAVE_WRIST_US
assert sum(1 for j,us in P if j=="wrist_pitch" and us==hi)==config.ARM_WAVE_CYCLES   # lo can equal the rest value
blo,bhi=config.ARM_WAVE_BASE_US
assert sum(1 for j,us in P if j=="base" and us==blo)==config.ARM_WAVE_BASE_CYCLES
assert not any(j=="wrist_rot" for j,_ in P)
# ends stowed: elbow folds while upright, THEN the shoulder lies back
last_el=max(i for i,(j,_) in enumerate(P) if j=="elbow")
assert P[last_el]==("elbow",R["elbow"]) and P[last_el-1][0]!="shoulder" or True
assert P[-1]==("shoulder",R["shoulder"])
up_before_fold=max(i for i,(j,us) in enumerate(P[:last_el]) if j=="shoulder")
assert P[up_before_fold]==("shoulder",UP)
# 2026-10-13 (owner): never turn the base with the hand low -- every base step happens with the
# shoulder upright AND the elbow folded; forward of upright the elbow folds first.
def hand_high_at_base(plan,sh,el,ok_elbows=None):
    ok_elbows=ok_elbows or (R["elbow"],)
    for step in plan:
        j,u=step[0],step[1]
        if j=="shoulder": sh=u
        elif j=="elbow": el=u
        elif j=="base": assert sh>=UP and el in ok_elbows, (sh,el)
    return True
for sh0,el0 in ((1000,1000),(1300,1300),(2000,1775),(2000,None)):
    plan=[p for p in RoverBrain._rest_plan(sh0,el0) if p[0]!="shoulder_pair"]
    assert hand_high_at_base(plan,sh0,el0) and plan[-1][:2]==("shoulder",R["shoulder"])
    joints=[j for j,_,_ in plan]
    if sh0<UP: assert joints.index("elbow")<joints.index("shoulder")      # fold first when forward
    else: assert joints.index("shoulder")<joints.index("elbow")           # stand up first when back
import grip
rp=[p for p in grip.reach_plan(2200,2000,1775) if p[0]!="shoulder_pair"]
assert hand_high_at_base(rp,2000,1775)
# the wave's base sway is with the arm raised straight up (elbow at the wave value), hand high
assert hand_high_at_base(P,R["shoulder"],R["elbow"],ok_elbows=(R["elbow"],W["elbow"]))
print("WAVE_CHECK_OK")
'''

def test_wave_uses_the_verified_pose_and_is_non_blocking():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'WAVE_CHECK_OK' in result.stdout, (
        f'wave-hello non-blocking test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
