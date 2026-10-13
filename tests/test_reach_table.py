import os,sys,types,queue,threading
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config,reach_table

# Reach by example (2026-10-13): taught image spot -> arm pose, blended for new objects.

@pytest.fixture(autouse=True)
def _mem(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',True)

def test_empty_table_gives_nothing():
    assert reach_table.pose_for((0.5,0.9))==(None,None)

def test_exact_spot_returns_its_pose_and_between_spots_blends():
    reach_table.add((0.4,0.9),{'shoulder':1300,'elbow':1300,'wrist_pitch':1275,'base':1450})
    reach_table.add((0.6,0.9),{'shoulder':1300,'elbow':1300,'wrist_pitch':1275,'base':1550})
    assert reach_table.pose_for((0.4,0.9))[0]['base']==1450
    mid,d=reach_table.pose_for((0.5,0.9))
    assert mid['base']==1500 and abs(d-0.1)<1e-9

def test_too_far_from_every_taught_spot_refuses():
    reach_table.add((0.5,0.9),{'shoulder':1300,'elbow':1300})
    pose,d=reach_table.pose_for((0.5,0.5))
    assert pose is None and d>config.REACH_TABLE_MAX_DIST

def test_old_epoch_spots_are_ignored(monkeypatch):
    reach_table.add((0.5,0.9),{'shoulder':1300,'elbow':1300})
    monkeypatch.setattr(config,'ARM_POSE_EPOCH','after-a-servo-change')
    assert reach_table.load()==[]

def test_reach_plan_uses_the_given_pose_and_its_base():
    import grip
    plan=[p for p in grip.reach_plan(1500,2000,1825,pose={'shoulder':1350,'elbow':1400,'base':1620})
          if p[0]!='shoulder_pair']
    assert ('base',1620,0.4) in plan
    assert [u for j,u,_ in plan if j=='shoulder'][-1]==1350
    assert [u for j,u,_ in plan if j=='elbow'][-1]==1400

# ---- brain: learn, save, touch

class FakeArm:
    def __init__(self): self.p={}; self.released=False; self.log=[]
    def set_pulse(self,j,us): self.log.append((j,us)); self.p[j]=us if j!='shoulder_pair' else self.p.get(j)
    def pulse(self,j): return self.p.get(j,1500)
    def was_driven(self,j): return j in self.p and j!='shoulder_pair'
    def release(self): self.released=True
    @property
    def joints(self): return ['base','shoulder','elbow','wrist_rot','wrist_pitch','gripper']
    def keep_alive(self): pass

def _brain(dets):
    import teach
    from brain import RoverBrain
    b=types.SimpleNamespace(arm=FakeArm(),teacher=teach.ArmTeacher(),routine=teach.RoutineRunner(),
                            _state='IDLE',said=[],started=[],_release_after_seq=False)
    b._say=b.said.append
    b.detector=types.SimpleNamespace(detect=lambda classes=None:[d for d in dets if not classes or d['class'] in classes])
    b._start_arm_sequence=b.started.append
    for m in ('_teach_cmd','_arm_now','_reach_object','_shoulder_now','_stow_and_release','_at_rest','_rest_plan'):
        f=getattr(RoverBrain,m)
        setattr(b,m,f if isinstance(RoverBrain.__dict__.get(m),staticmethod) else types.MethodType(f,b))
    return b

CUP={'class':'cup','conf':0.8,'bbox':(880,760,920,800),'frame_w':1536,'frame_h':864}

def test_learn_then_save_then_touch():
    b=_brain([CUP])
    b._teach_cmd({'intent':'reach_learn','args':{}})
    assert b.teacher.active and b.started and 'cup' in b.said[-1]
    b.arm.p.update({'shoulder':1300,'elbow':1350,'wrist_pitch':1275,'base':1510})
    b._teach_cmd({'intent':'reach_save','args':{}})
    rows=reach_table.load()
    assert len(rows)==1 and rows[0]['pose']['elbow']==1350 and not b.teacher.active
    b.started.clear()
    b._teach_cmd({'intent':'reach_touch','args':{'object':'cup'}})
    plan=b.started[-1]
    assert [u for j,u,_ in plan if j=='elbow'][-1]==1350 and ('base',1510,0.4) in plan

def test_touch_with_nothing_learned_says_so():
    b=_brain([CUP])
    b._teach_cmd({'intent':'reach_touch','args':{'object':'cup'}})
    assert "haven't learned" in b.said[-1] and not b.started


def test_numpy_floats_are_saved_and_a_failed_write_cannot_corrupt():
    import numpy as np
    reach_table.add((np.float32(0.58),np.float32(0.81)),{'shoulder':np.int64(1300),'elbow':1300})
    assert reach_table.load()[0]['xy']==[0.58,0.81]
    det={'bbox':(np.float32(10),np.float32(10),np.float32(30),np.float32(30)),'frame_w':100,'frame_h':100}
    assert all(type(v) is float for v in reach_table.box_xy(det))

def test_save_after_teach_ended_refuses():
    b=_brain([CUP])
    b._teach_cmd({'intent':'reach_learn','args':{}})
    b.teacher.end()                                       # timed out, arm stowed
    b.arm.p.update({'shoulder':2000,'elbow':1825})
    b._teach_cmd({'intent':'reach_save','args':{}})
    assert reach_table.load()==[] and 'again' in b.said[-1]
