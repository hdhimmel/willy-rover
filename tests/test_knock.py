import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# FR-1000-006 knock at a shut door: a bounded, timed arm oscillation from a sonar-measured
# standoff, never move-until-contact. Unmeasured pose = ask only. Wheels stopped throughout.

POSE={'shoulder':1200,'elbow':1400,'wrist_pitch':1500}

class _Arm:
    def __init__(self): self.p={'shoulder':config.ARM_POSE_REST['shoulder'],'elbow':config.ARM_POSE_REST['elbow']}; self.log=[]; self.released=False
    def set_pulse(self,j,us): self.p[j]=us; self.log.append((j,us))
    def pulse(self,j): return self.p.get(j,1500)
    def was_driven(self,j): return False

class _Safety:
    def __init__(self): self.stops=0
    def stop(self): self.stops+=1

def _nav(arm,said):
    from navigation import Navigator
    n=Navigator(_Safety(),types.SimpleNamespace(pose=types.SimpleNamespace(x=0,y=0)),None,say=said.append,arm=arm)
    n.state='DOOR_WAIT'; n._target_room='kitchen'
    return n

def test_no_pose_means_no_plan_and_ask_only(monkeypatch):
    import knock
    monkeypatch.setattr(config,'ARM_POSE_KNOCK',None)
    assert knock.knock_plan(2010,None) is None
    said=[]; arm=_Arm(); n=_nav(arm,said)
    n._attempt_at_door(25)
    assert n._knock is None and arm.log==[] and 'let me in' in said[-1]

def test_plan_is_bounded_elbow_first_and_ends_at_rest(monkeypatch):
    import knock
    monkeypatch.setattr(config,'ARM_POSE_KNOCK',POSE)
    plan=knock.knock_plan(config.ARM_POSE_REST['shoulder'],None)
    assert plan[0]==('elbow',config.ARM_POSE_WAVE_HELLO['elbow'],0.6)     # elbow open before the shoulder
    first_sh=next(i for i,s in enumerate(plan) if s[0]=='shoulder'); assert first_sh==1
    sh=[s[1] for s in plan if s[0]=='shoulder']
    assert all(abs(b-a)<=config.ARM_WAVE_APPROACH_STEP_US for a,b in zip([config.ARM_POSE_REST['shoulder']]+sh,sh))
    taps=[s for s in plan if s[0]==config.ARM_KNOCK_TAP_JOINT and s[1]==POSE['wrist_pitch']+config.ARM_KNOCK_TAP_US]
    assert len(taps)==config.ARM_KNOCK_TAPS
    assert plan[-1]==('wrist_pitch',config.ARM_REST_WRIST_US,0.0)
    assert ('shoulder',config.ARM_POSE_REST['shoulder'],0.3) in plan[-6:]
    assert sum(s[2] for s in plan)<30                                      # timed, finite

def test_standoff_band(monkeypatch):
    import knock
    lo,hi=config.ARM_KNOCK_STANDOFF_CM
    assert knock.standoff_ok(lo) and knock.standoff_ok(hi) and not knock.standoff_ok(hi+1)
    assert not knock.standoff_ok(None)
    monkeypatch.setattr(config,'ARM_POSE_KNOCK',POSE)
    said=[]; arm=_Arm(); n=_nav(arm,said)
    n._attempt_at_door(hi+20)                        # too far: ask, never drive closer
    assert n._knock is None and arm.log==[] and said

def test_knock_then_ask_with_wheels_stopped(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_KNOCK',POSE)
    said=[]; arm=_Arm(); n=_nav(arm,said)
    n._attempt_at_door(25)
    assert n._knock is not None and said==[]
    n._knock._due=0.0
    for _ in range(500):
        n._knock and setattr(n._knock,'_due',0.0)
        n._door_wait({'front':25},0.0)
        if n._knock is None: break
    assert n._knock is None and 'let me in' in said[-1]
    assert n.safety.stops>=len(arm.log)              # stopped on every knock tick
    assert arm.p['shoulder']==config.ARM_POSE_REST['shoulder']

def test_release_mid_knock_stops_it_and_asks_only_after(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_KNOCK',POSE)
    said=[]; arm=_Arm(); n=_nav(arm,said)
    n._attempt_at_door(25); n._knock._due=0.0; n._door_wait({'front':25},0.0)
    arm.released=True; n._knock._due=0.0; before=len(arm.log)
    n._door_wait({'front':25},0.0)
    assert n._knock is None and len(arm.log)==before and n._knock_off and said
    n._attempt_at_door(25); assert n._knock is None

def test_door_opens_mid_knock_arm_goes_home_before_driving(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_KNOCK',POSE)
    said=[]; arm=_Arm(); n=_nav(arm,said)
    n._attempt_at_door(25)
    for _ in range(8): n._knock._due=0.0; n._door_wait({'front':25},0.0)
    for _ in range(500):
        if n._knock is None: break
        n._knock._due=0.0; n._door_wait({'front':100},0.0)
        assert n.state=='DOOR_WAIT' or n._knock is None
    assert n.state=='SEEKING' and arm.p['shoulder']==config.ARM_POSE_REST['shoulder']
    assert not [s for s in said if 'let me in' in s]

def test_abort_mid_knock_holds_the_arm(monkeypatch):
    monkeypatch.setattr(config,'ARM_POSE_KNOCK',POSE)
    said=[]; arm=_Arm(); n=_nav(arm,said)
    n._attempt_at_door(25); n._knock._due=0.0; n._door_wait({'front':25},0.0)
    before=len(arm.log); n.abort('voice stop')
    assert n._knock is None and len(arm.log)==before
