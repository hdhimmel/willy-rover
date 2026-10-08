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

def test_reach_opens_the_elbow_first_and_steps_the_shoulder(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_REACH',{'shoulder':1200,'elbow':1300,'wrist_pitch':1500})
    plan=grip.reach_plan(1500,2010,None)
    joints=[j for j,_,_ in plan]
    assert joints[0]=='gripper' and plan[0][1]==config.GRIP_OPEN_US
    assert joints.index('elbow')<joints.index('shoulder')            # elbow opens first
    sh=[u for j,u,_ in plan if j=='shoulder']
    assert max(abs(b-a) for a,b in zip([2010]+sh,sh))<=config.ARM_WAVE_APPROACH_STEP_US
    assert not any(j=='elbow' and u==config.ARM_SERVO_CENTER_US for j,u,_ in plan)

def test_fetch_refuses_aloud_without_a_reach_pose(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_REACH',None)
    from retrieval_task import RetrievalTask
    said=[]
    arm=types.SimpleNamespace(set_pulse=lambda j,u: None,pulse=lambda j: 1500,was_driven=lambda j: False)
    voice=types.SimpleNamespace(speak=lambda t,**k: said.append(t))
    t=RetrievalTask(types.SimpleNamespace(),arm,types.SimpleNamespace(),voice=voice)
    t.state='GRASP'; t._grasp({},0)
    assert t.state=='FAILED' and 'reach' in said[-1]
