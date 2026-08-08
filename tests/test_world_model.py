import os,sys,time,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from world_model import WorldModel,Observation,Object

# Pure-logic tests for world_model.py -- no hardware needed (§20/§9/§10 of
# docs/WildWilly_Claude_Fix_Implementation_Plan.md). A minimal fake stands in for odometry.Odometry
# since WorldModel only ever reads its .pose property (get_robot_pose() delegates, doesn't
# duplicate odometry's own logic -- that's covered by tests/test_odometry.py).

class _FakeOdometry:
    def __init__(self,pose=None): self.pose=pose

def _wm(tmp_path,pose=None):
    return WorldModel(_FakeOdometry(pose),db_path=os.path.join(tmp_path,'wm_test.db'))

def test_get_robot_pose_delegates_to_odometry():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d,pose='sentinel-pose')
        assert wm.get_robot_pose()=='sentinel-pose'

def test_obstacle_nearby_and_age_eviction():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.update_observation(Observation('obstacle',1.0,0.0,timestamp=time.time()))
        wm.update_observation(Observation('obstacle',5.0,5.0,timestamp=time.time()))
        near=wm.get_nearby_obstacles(0.0,0.0,radius_m=2.0)
        assert len(near)==1 and near[0].x==1.0
        # stale entry (older than OBSTACLE_MAX_AGE_S) must be pruned even if spatially close
        wm.update_observation(Observation('obstacle',1.5,0.0,timestamp=time.time()-config.OBSTACLE_MAX_AGE_S-1))
        near=wm.get_nearby_obstacles(0.0,0.0,radius_m=2.0)
        assert all(o.x!=1.5 for o in near)

def test_object_dedupe_on_proximity_merges_not_duplicates():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.update_observation(Observation('object',1.0,1.0,payload={'cls':'bottle','confidence':0.6}))
        wm.update_observation(Observation('object',1.05,1.02,payload={'cls':'bottle','confidence':0.9}))
        bottles=wm.get_objects('bottle')
        assert len(bottles)==1
        assert bottles[0].confidence==0.9  # dedupe keeps the higher confidence seen so far

def test_object_far_away_is_a_separate_object():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.update_observation(Observation('object',0.0,0.0,payload={'cls':'bottle','confidence':0.5}))
        wm.update_observation(Observation('object',10.0,10.0,payload={'cls':'bottle','confidence':0.5}))
        assert len(wm.get_objects('bottle'))==2

def test_remember_object_explicit_api_uses_same_dedupe():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.remember_object(Object('mug',2.0,2.0,0.7))
        wm.remember_object(Object('mug',2.01,1.99,0.8))
        assert len(wm.get_objects('mug'))==1

def test_get_room_nearest_match_within_radius():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.add_room('kitchen',cx=0.0,cy=0.0,radius_m=1.0)
        wm.add_room('hallway',cx=5.0,cy=0.0,radius_m=1.0)
        assert wm.get_room(0.2,0.2).name=='kitchen'
        assert wm.get_room(5.1,0.0).name=='hallway'
        assert wm.get_room(2.5,0.0) is None  # outside both radii

def test_save_load_round_trip():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.add_room('kitchen',cx=1.0,cy=2.0,radius_m=1.5)
        wm.add_doorway('kitchen','hallway',x=1.0,y=0.0)
        wm.remember_landmark('dock',x=0.0,y=0.0,kind='charging_dock')
        wm.remember_object(Object('bottle',3.0,3.0,0.9))
        wm.add_route('to_kitchen',[(0.0,0.0),(1.0,2.0)])
        wm.save()

        wm2=_wm(d)  # separate instance, same db_path (same tempdir d) -> __init__'s own load() picks it up
        assert wm2.get_room(1.0,2.0).name=='kitchen'
        assert len(wm2.all_doorways())==1
        assert wm2.get_landmark('dock').kind=='charging_dock'
        assert len(wm2.get_objects('bottle'))==1
        assert wm2.get_route('to_kitchen').waypoints==[(0.0,0.0),(1.0,2.0)]

def test_obstacles_are_not_persisted():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.update_observation(Observation('obstacle',1.0,1.0))
        wm.save()
        wm2=_wm(d)  # fresh instance loading the same db -- obstacles must not have crossed over
        assert wm2.get_nearby_obstacles(1.0,1.0,radius_m=5.0)==[]
