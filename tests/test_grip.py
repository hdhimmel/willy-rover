import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest, config, grip




# 2026-10-08 grasp rebuild: gripper closed against its own position feedback, measured end points
# only, elbow-first reach, no guessed pose.

class _Jaw:
    """A simulated gripper: the jaw follows the command until it meets an object at `block_us`."""
    def __init__(self,block_us=None):
        self.block_us=block_us; self.cmd=config.GRIP_OPEN_US; self.cmds=[]
    def set(self,us): self.cmd=us; self.cmds.append(us)
    def fb(self):
        pos=self.cmd if self.block_us is None else min(self.cmd,self.block_us)
        return 0.2+0.0004*(pos-config.GRIP_OPEN_US)        # ratio rises as the jaw closes

def _close(jaw,limit=200):
    c=grip.GripCloser(jaw.set,jaw.fb)
    for _ in range(limit):
        r=c.step()
        if r: return r,c
    raise AssertionError('never decided')

def test_an_object_stops_the_jaw_and_it_is_held_with_a_small_squeeze():
    jaw=_Jaw(block_us=1600); r,c=_close(jaw)
    assert r=='gripped'
    assert 1600<=c.held_us<=1600+config.GRIP_SQUEEZE_US+config.GRIP_CLOSE_STEP_US

def test_closing_on_nothing_is_empty_and_stays_inside_the_measured_range():
    jaw=_Jaw(); r,c=_close(jaw)
    assert r=='empty' and max(jaw.cmds)==config.GRIP_CLOSED_US
    assert all(config.GRIP_OPEN_US<=u<=config.GRIP_CLOSED_US for u in jaw.cmds)

def test_no_feedback_closes_only_partway_and_says_unsensed():
    sent=[]; c=grip.GripCloser(sent.append,lambda: None)
    assert c.step()=='unsensed' and sent==[config.GRIP_UNSENSED_US] and config.GRIP_UNSENSED_US<2210

def test_handoff_is_sensed_when_the_jaw_moves():
    assert grip.released_by_person(0.30,0.30+config.GRIP_HANDOFF_DELTA)
    assert not grip.released_by_person(0.30,0.302)
    assert not grip.released_by_person(None,0.4)

def test_feedback_is_a_ratio_to_the_arm_rail():
    adc=types.SimpleNamespace(grip_feedback_volts=lambda: 3.0)
    cur=types.SimpleNamespace(rail=lambda n: {'voltage_v':6.0})
    assert abs(grip.read_feedback(adc,cur)-0.5)<1e-9
    low=types.SimpleNamespace(rail=lambda n: {'voltage_v':1.0})
    assert grip.read_feedback(adc,low) is None

def test_no_reach_plan_until_the_pose_is_measured(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_REACH',None)
    assert grip.reach_plan(1500,2010,None) is None

def test_reach_turns_base_folded_then_lowers_by_opening_the_elbow(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_REACH',{'shoulder':1200,'elbow':1300,'wrist_pitch':1500})
    plan=[p for p in grip.reach_plan(1500,2010,None) if p[0]!='shoulder_pair']
    joints=[j for j,_,_ in plan]
    assert joints[0]=='gripper' and plan[0][1]==config.GRIP_OPEN_US
    b=joints.index('base')
    sh=[u for j,u,_ in plan[:b] if j=='shoulder']; el=[u for j,u,_ in plan[:b] if j=='elbow']
    assert sh[-1]==config.ARM_BASE_TURN_SHOULDER_US and el[-1]==config.ARM_POSE_REST['elbow']   # folded, raised
    after=plan[b+1:]
    last_sh=max(i for i,(j,_,_) in enumerate(after) if j=='shoulder')
    assert all(j!='elbow' for j,_,_ in after[:last_sh])                 # forward while still folded
    el2=[u for j,u,_ in after if j=='elbow']
    assert el2[-1]==1300 and el2==sorted(el2,reverse=True)               # then the hand comes DOWN
    shs=[u for j,u,_ in plan if j=='shoulder']
    assert max(abs(y-x) for x,y in zip([2010]+shs,shs))<=config.ARM_WAVE_APPROACH_STEP_US

def test_fetch_refuses_aloud_without_a_reach_pose(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_REACH',None)
    from retrieval_task import RetrievalTask
    said=[]
    arm=types.SimpleNamespace(set_pulse=lambda j,u: None,pulse=lambda j: 1500,was_driven=lambda j: False)
    voice=types.SimpleNamespace(speak=lambda t,**k: said.append(t))
    t=RetrievalTask(types.SimpleNamespace(),arm,types.SimpleNamespace(),voice=voice)
    t.state='GRASP'; t._grasp({},0)
    assert t.state=='FAILED' and 'reach' in said[-1]


def test_shoulder_ramp_pairs_only_forward_of_upright():
    assert not any(j=='shoulder_pair' for j,_,_ in grip.shoulder_ramp(2000,config.ARM_STOW_UPRIGHT_US))
    assert not any(j=='shoulder_pair' for j,_,_ in grip.shoulder_ramp(config.ARM_STOW_UPRIGHT_US,1300))  # lowering

def test_shoulder_ramp_engages_the_pair_and_steps_slowly():
    r=grip.shoulder_ramp(1300,1500)
    assert r[0][:2]==('shoulder_pair',1) and r[-1][:2]==('shoulder_pair',0)
    sh=[u for j,u,_ in r if j=='shoulder']
    assert sh[-1]==1500 and all(abs(b-a)<=config.ARM_PAIR_STEP_US for a,b in zip([1300]+sh,sh))


def test_hover_height_follows_the_object():
    det={'bbox':(100,400,240,560),'frame_w':1280,'frame_h':720}      # 160 px tall, not clipped
    h=grip.object_height_cm(det); assert abs(h-160/config.RETRIEVAL_PX_PER_CM_AT_TARGET)<1e-9
    clipped={'bbox':(100,600,241,720),'frame_w':1280,'frame_h':720}  # cut by the bottom: use width
    assert abs(grip.object_height_cm(clipped)-141/config.RETRIEVAL_PX_PER_CM_AT_TARGET)<1e-9
    tall=grip.reach_plan(2200,2000,1775,object_cm=10); short=grip.reach_plan(2200,2000,1775,object_cm=2)
    top=lambda p: [u for j,u,dl in p if j=='elbow' and dl==0.8][0]        # the hover step
    assert top(tall)>top(short)>config.ARM_POSE_REACH['elbow']


def test_camera_check_after_lift():
    import grip
    spot=(0.5,0.8)
    def det(x,y): return {'bbox':(x*100-5,y*100-5,x*100+5,y*100+5),'frame_w':100,'frame_h':100}
    assert grip.camera_check(lambda: det(0.52,0.79),spot)=='on_floor'
    assert grip.camera_check(lambda: None,spot)=='gone'
    assert grip.camera_check(lambda: det(0.5,0.3),spot)=='in_hand'
    seq=iter([None,det(0.5,0.8)])                       # one sighting at the spot = a miss
    assert grip.camera_check(lambda: next(seq),spot)=='on_floor'
    assert grip.camera_check(lambda: None,None)=='unknown'
    def boom(): raise RuntimeError('no camera')
    assert grip.camera_check(boom,spot)=='unknown'


def test_feedback_that_does_not_read_open_at_the_start_is_not_trusted():
    # 2026-10-14: a dead/misread feedback made every grasp "grip" at the open position
    import grip
    sent=[]
    gc=grip.GripCloser(sent.append,lambda: 0.02)          # nowhere near the open ratio
    assert gc.step()=='unsensed' and sent==[config.GRIP_UNSENSED_US]
    sent.clear()
    gc=grip.GripCloser(sent.append,lambda: config.GRIP_FB_OPEN_RATIO+0.01)
    assert gc.step() is None and sent==[]                 # a sane open reading: normal close


def test_handoff_is_the_jaw_closing_not_any_change():
    # 2026-10-15: the jaw CLOSES (ratio rises) when the object is pulled out; opening is not a take
    assert not grip.released_by_person(0.30,0.30-config.GRIP_HANDOFF_DELTA*2)
    # the squeeze travel is ~0.010; the threshold must sit well inside it
    travel=config.GRIP_SQUEEZE_US*config.GRIP_FB_PER_US
    assert 0.003<config.GRIP_HANDOFF_DELTA<0.8*travel
