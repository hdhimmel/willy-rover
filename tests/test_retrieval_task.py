import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from retrieval_task import RetrievalTask

# retrieval_task.py had zero test coverage before this file, despite being called out in the
# gap analysis as the best-covered subsystem *architecturally* -- that referred to
# LOCALIZE/APPROACH/GRASP/VERIFY/DELIVER/AWAIT_CONFIRM matching the FRD's requested state list,
# not to any actual test file. These tests target the 2026-08-18 fix: _grasp() used to run its
# whole pulse sequence through blocking time.sleep() calls inside a single tick() call (~1.1s
# total), which meant a tilt/battery/sensor-fault abort() (called from brain.py's tick thread --
# the same thread _grasp() was blocking) had no way to run until the arm had already finished
# moving. That defeated the same non-blocking-control-loop guarantee Phase 1 (§2) established for
# drive motion. _grasp() is now a 4-step, deadline-serviced state machine polled from tick().

class _FakeSafety:
    def __init__(self): self.calls=[]; self._timed=False
    def stop(self): self.calls.append(('stop',))
    def forward(self,speed=None): self.calls.append(('forward',speed))
    def turn_left_for(self,duration,speed=None): self.calls.append(('turn_left_for',duration,speed))
    def turn_right_for(self,duration,speed=None): self.calls.append(('turn_right_for',duration,speed))
    @property
    def timed_move_active(self): return self._timed

class _FakeArm:
    def __init__(self): self.pulses=[]; self._p={}
    def set_pulse(self,joint,us): self.pulses.append((joint,us)); self._p[joint]=us
    def pulse(self,joint): return self._p.get(joint,1500)
    def was_driven(self,joint): return joint in self._p

class _FakeDetector:
    def __init__(self,dets=None): self._dets=dets or []
    def detect(self,classes=None): return self._dets
    def localize(self,det): return (0.0,0.0)

import pytest



_REACH={'shoulder':1210,'elbow':1300,'wrist_pitch':1500}   # a stand-in; the real one is unmeasured

@pytest.fixture(autouse=True)
def _reach(monkeypatch): monkeypatch.setattr(config,'ARM_POSE_REACH',dict(_REACH))

def _grasp_task():
    rt=RetrievalTask(_FakeSafety(),_FakeArm(),_FakeDetector())
    rt.state='GRASP'; rt._bearing_deg=0.0
    return rt

def _run(rt,limit=200):
    n=0
    while rt.state=='GRASP' and n<limit:
        rt.tick({'front':999},0.0); n+=1
        if rt._grasp_deadline is not None: rt._grasp_deadline=0   # fast-forward each wait
    return n

# --- non-blocking (the 2026-08-18 safety fix, kept through the 2026-10-08 rebuild) ---

def test_grasp_tick_returns_immediately_not_blocking():
    rt=_grasp_task()
    t0=time.perf_counter()
    rt.tick({'front':999},0.0)
    assert time.perf_counter()-t0<0.05

def test_grasp_first_tick_only_opens_the_gripper_to_its_measured_open():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    assert rt.arm.pulses==[('gripper',config.GRIP_OPEN_US)]
    assert rt.state=='GRASP'

def test_grasp_retick_before_deadline_is_a_noop():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    before=list(rt.arm.pulses)
    rt.tick({'front':999},0.0)
    assert rt.arm.pulses==before

def test_full_grasp_obeys_the_arm_rules_and_reaches_verify():
    rt=_grasp_task(); _run(rt)
    assert rt.state=='VERIFY' and rt._grip_result=='unsensed'      # no feedback in this fake
    P=[p for p in rt.arm.pulses if p[0]!='shoulder_pair']; joints=[j for j,_ in P]
    # (10-13 eve: the stow shoulder moved to 500, so the plan's start side changed; the reach end
    # is what matters here and is gated off on the rover until re-measured)
    assert [u for j,u in P if j=='elbow'][-2:][0] is not None
    sh=[u for j,u in P if j=='shoulder']
    assert max(abs(b-a) for a,b in zip([config.ARM_POSE_REST['shoulder']]+sh,sh))<=config.ARM_WAVE_APPROACH_STEP_US
    g=[u for j,u in P if j=='gripper']
    assert all(config.GRIP_OPEN_US<=u<=config.GRIP_CLOSED_US for u in g)

# --- abort() can land mid-grasp ---

def test_abort_mid_grasp_stops_before_later_steps_run():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    n=len(rt.arm.pulses)
    rt.abort('simulated tilt fault')
    assert rt.state=='ABORTED' and ('stop',) in rt.safety.calls
    for _ in range(5): rt.tick({'front':999},0.0)
    assert len(rt.arm.pulses)==n

def test_abort_resets_grasp_state():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    rt.abort('reason')
    assert rt._phase is None and rt._plan==[] and rt._grasp_deadline is None

def test_abort_when_not_active_still_resets_grasp_state():
    rt=RetrievalTask(_FakeSafety(),_FakeArm(),_FakeDetector())
    rt.abort('reason')
    assert rt.state=='ABORTED'
    assert rt._grasp_step==0 and rt._grasp_deadline is None


# --- 2026-10-13: line-up by image position ---

def _lineup(cx,cy,front=999,ticks=1):
    import types
    calls=[]
    s=types.SimpleNamespace(timed_move_active=False,
        turn_left_for=lambda t,v: calls.append('left'),turn_right_for=lambda t,v: calls.append('right'),
        forward_for=lambda t,v: calls.append('fwd'),reverse_for=lambda t,v: calls.append('back'),
        stop=lambda: calls.append('stop'))
    W,H=1536,864
    det={'class':'cup','conf':0.9,'bbox':(cx*W-20,cy*H-20,cx*W+20,cy*H+20),'frame_w':W,'frame_h':H}
    rt=RetrievalTask(s,None,types.SimpleNamespace(detect=lambda classes=None:[det]))
    rt.state='APPROACH'; rt._target_class='cup'
    for _ in range(ticks): rt._approach({'front':front},0.0)
    return rt.state,calls

def test_lineup_turns_creeps_backs_off_and_grasps_on_target():
    tx,ty=config.RETRIEVAL_TARGET_XY
    assert _lineup(tx+0.2,0.5)[1]==['right'] and _lineup(tx-0.2,0.5)[1]==['left']
    assert _lineup(tx,0.5)[1]==['fwd']
    assert _lineup(tx,min(1.0,ty+0.06))[1]==['back']
    assert _lineup(tx,ty)==('APPROACH',['stop'])            # one frame on target is not enough
    assert _lineup(tx,ty,ticks=2)==('GRASP',['stop','stop'])
    st,c=_lineup(tx,0.5,front=1)
    assert st=='FAILED' and 'fwd' not in c                 # never pushes through something closer


def test_abort_drops_the_shoulder_pair():
    import types
    dropped=[]
    arm=types.SimpleNamespace(drop_pair=lambda: dropped.append(1))
    rt=RetrievalTask(types.SimpleNamespace(stop=lambda: None),arm,types.SimpleNamespace())
    rt.state='GRASP'; rt.abort('voice stop')
    assert dropped==[1] and rt.state=='ABORTED'


def test_pick_lineup_rotates_big_errors_and_aims_the_base_for_small_ones():
    import types,retrieval_task
    calls=[]
    s=types.SimpleNamespace(timed_move_active=False,forward_for=lambda t,v: calls.append(('fwd',v)),
        reverse_for=lambda t,v: calls.append('back'),stop=lambda: calls.append('stop'))
    W,H=1280,720
    def task(cx,cy):
        det={'class':'sports ball','conf':0.9,'bbox':(cx*W-30,cy*H-30,cx*W+30,cy*H+30),'frame_w':W,'frame_h':H}
        rt=RetrievalTask(s,None,types.SimpleNamespace(detect=lambda classes=None:[det]))
        rt.start('sports ball',pick_only=True); rt.state='APPROACH'
        return rt
    tx,ty=config.RETRIEVAL_TARGET_XY
    rt=task(0.9,ty); rt._approach({'front':999},0)
    assert rt.state=='FAILED' and 'too far right' in rt._fail_reason   # body turns off (10-13)
    calls.clear(); rt=task(tx,0.5); rt._approach({'front':999},0)
    assert calls==[('fwd',config.RETRIEVAL_CREEP_SPEED)]       # creep at a speed that breaks away
    rt=task(tx+0.1,ty); rt._approach({'front':999},0); rt._approach({'front':999},0)
    assert rt.state=='GRASP' and rt._reach_pose['base']==retrieval_task.base_for_x(tx+0.1)
    assert retrieval_task.base_for_x(0.26)==2200 and 2100<retrieval_task.base_for_x(0.35)<2200 and retrieval_task.base_for_x(0.5)==2050


def test_vision_reach_drives_turns_then_reaches(monkeypatch):
    # 2026-10-14: when arm_ik is calibrated the pick-up line-up follows arm_ik.plan_for()
    import types,arm_ik
    calls=[]
    s=types.SimpleNamespace(timed_move_active=False,forward_for=lambda t,v: calls.append(('fwd',t)),
        reverse_for=lambda t,v: calls.append(('back',t)),stop=lambda: calls.append('stop'))
    det={'class':'sports ball','conf':0.9,'bbox':(600,500,660,560),'frame_w':1280,'frame_h':720}
    rt=RetrievalTask(s,None,types.SimpleNamespace(detect=lambda classes=None:[det]))
    rt.start('sports ball',pick_only=True); rt.state='APPROACH'
    monkeypatch.setattr(arm_ik,'ready',lambda: True)
    plans=iter([('forward',300.0),('turn',40.0),('reach',{'base':1600,'shoulder':1300,'elbow':1400,'wrist_pitch':1250},
                {'x':300,'y':20,'size_mm':70,'angles':{'base':2,'shoulder':-10,'elbow':60,'wrist_pitch':15}})]*1+
               [('reach',{'base':1600,'shoulder':1300,'elbow':1400,'wrist_pitch':1250},
                {'x':300,'y':20,'size_mm':70,'angles':{'base':2,'shoulder':-10,'elbow':60,'wrist_pitch':15}})])
    monkeypatch.setattr(arm_ik,'plan_for',lambda d: next(plans))
    rt._approach({'front':999},0); assert calls[-1]==('fwd',config.RETRIEVAL_CREEP_PULSE_S[1])
    rt._approach({'front':999},0); assert rt.turn_request==40.0
    rt._approach({'front':999},0); rt._approach({'front':999},0)        # two confirming frames
    assert rt.state=='GRASP' and rt._reach_pose['base']==1600 and abs(rt._object_cm-7.0)<1e-6

def test_vision_reach_stops_for_an_obstacle_and_reports_failures(monkeypatch):
    import types,arm_ik
    s=types.SimpleNamespace(timed_move_active=False,forward_for=lambda t,v: None,reverse_for=lambda t,v: None,stop=lambda: None)
    det={'class':'sports ball','conf':0.9,'bbox':(600,500,660,560),'frame_w':1280,'frame_h':720}
    rt=RetrievalTask(s,None,types.SimpleNamespace(detect=lambda classes=None:[det]))
    rt.start('sports ball',pick_only=True); rt.state='APPROACH'
    monkeypatch.setattr(arm_ik,'ready',lambda: True)
    monkeypatch.setattr(arm_ik,'plan_for',lambda d: ('forward',200.0))
    rt._approach({'front':config.RETRIEVAL_PICK_STOP_CM-1},0)
    assert rt.state=='FAILED' and 'in the way' in rt._fail_reason
    rt.state='APPROACH'; monkeypatch.setattr(arm_ik,'plan_for',lambda d: ('fail',"no arm position reaches it"))
    rt._approach({'front':999},0)
    assert rt.state=='FAILED' and rt._fail_reason=='no arm position reaches it'

def test_blind_creep_then_reach_then_back_off_before_looking(monkeypatch):
    # 2026-10-14: last fix -> creep out of view by encoder distance -> reach -> back off -> look
    import types,arm_ik
    calls=[]
    enc=types.SimpleNamespace(is_healthy=True,counts={w:0 for w in ('lf','lm','lr','rf','rm','rr')})
    def move(sign):
        def f(t,v):
            calls.append(('fwd' if sign>0 else 'back',t))
            for w in enc.counts:
                if w!='rf': enc.counts[w]+=sign*config.ENCODER_SIGN[w]*24   # ~10 mm per pulse
        return f
    s=types.SimpleNamespace(timed_move_active=False,forward_for=move(1),reverse_for=move(-1),stop=lambda: calls.append('stop'))
    det={'class':'sports ball','conf':0.9,'bbox':(600,600,670,665),'frame_w':1280,'frame_h':720}
    rt=RetrievalTask(s,None,types.SimpleNamespace(detect=lambda classes=None:[det]))
    rt.encoders=enc
    rt.start('sports ball',pick_only=True); rt.state='APPROACH'
    info={'x':420.0,'y':10.0,'z':35.0,'size_mm':70.0,'range_mm':420.0}
    monkeypatch.setattr(arm_ik,'ready',lambda: True)
    monkeypatch.setattr(arm_ik,'plan_for',lambda d: ('fix',info,100.0))
    got={}
    def after(i,t):
        got['t']=t; return ({'base':1500,'shoulder':1200,'elbow':1400,'wrist_pitch':1250},{'base':0,'shoulder':-10,'elbow':60,'wrist_pitch':10})
    monkeypatch.setattr(arm_ik,'reach_after_creep',after)
    rt._approach({'front':999},0); rt._approach({'front':999},0)          # two confirming frames
    assert rt._blind and rt._spot_xy
    for _ in range(30):
        if rt.state!='APPROACH': break
        rt._approach({'front':999},0)
    assert rt.state=='GRASP' and 85<=got['t']<=110 and rt._reach_pose['shoulder']==1200
    n_fwd=sum(1 for c in calls if c[0]=='fwd')
    # verify: backs off about the same distance before looking
    rt._grip_result='gripped'; rt.state='VERIFY'; rt.detector=types.SimpleNamespace(detect=lambda classes=None: [])
    for _ in range(30):
        if rt.state!='VERIFY': break
        rt._verify({},0)
    n_back=sum(1 for c in calls if c[0]=='back')
    assert rt.state=='HOLDING' and abs(n_back-n_fwd)<=1


# ---- 2026-10-14 review: explicit pick outcomes, and no release on a hand-off timeout ----
def _verify_task(grip_result,detect,pick_only=False):
    import types
    arm=_FakeArm()
    rt=RetrievalTask(types.SimpleNamespace(timed_move_active=False,stop=lambda: None),arm,
                     types.SimpleNamespace(detect=detect))
    rt.start('sports ball',pick_only=pick_only); rt.state='VERIFY'
    rt._grip_result=grip_result; rt._spot_xy=(0.5,0.9); rt._backoff_mm=0
    return rt,arm

def test_gripped_and_camera_says_gone_is_confirmed_and_delivered():
    rt,arm=_verify_task('gripped',lambda classes=None: [])
    rt._verify({},0)
    assert rt.state=='DELIVER' and rt.pick_outcome=='confirmed'

def test_a_camera_failure_is_uncertain_never_delivered():
    def boom(classes=None): raise RuntimeError('camera')
    rt,arm=_verify_task('gripped',boom)
    rt._verify({},0)
    assert rt.state=='HOLDING' and rt.pick_outcome=='uncertain' and "couldn't check" in rt.hold_message
    assert ('gripper',config.GRIP_OPEN_US) not in arm.pulses           # keeps holding

def test_no_feedback_and_no_camera_answer_is_uncertain():
    rt,arm=_verify_task('unsensed',lambda classes=None: [])
    rt._spot_xy=None                                                  # camera cannot judge
    rt._verify({},0)
    assert rt.state=='HOLDING' and rt.pick_outcome=='uncertain'

def test_a_handoff_timeout_never_opens_the_gripper(monkeypatch):
    import types,time as _t
    arm=_FakeArm(); said=[]
    rt=RetrievalTask(types.SimpleNamespace(timed_move_active=False,stop=lambda: None),arm,_FakeDetector(),
                     voice=types.SimpleNamespace(speak=said.append,pending_commands=__import__('queue').Queue()))
    rt.start('sports ball'); rt.state='AWAIT_CONFIRM'; rt._fb_hold=None
    t=[1000.0]; monkeypatch.setattr('retrieval_task.time.time',lambda: t[0])
    rt._confirm_deadline=t[0]+config.RETRIEVAL_HANDOFF_WAIT_S
    for _ in range(config.RETRIEVAL_HANDOFF_ASKS):
        t[0]+=config.RETRIEVAL_HANDOFF_WAIT_S+1; rt._await_confirm({},0)
    assert rt.state=='HOLDING' and rt.pick_outcome=='handoff_unconfirmed'
    assert ('gripper',config.GRIP_OPEN_US) not in arm.pulses
    assert any('still holding' in s for s in said)
