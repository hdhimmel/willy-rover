import os,sys,math,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from world_model import project_point
from mapping import MappingSession

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pure-logic tests for mapping.py + world_model.project_point() -- no hardware needed (§20/§10 of
# docs/WildWilly_Claude_Fix_Implementation_Plan.md). Fakes stand in for world_model.WorldModel and
# vision.ObjectDetector since MappingSession only ever calls their public interface
# (get_robot_pose/update_observation/save, detect/localize) -- real WorldModel persistence is
# already covered by tests/test_world_model.py.

class _FakePose:
    def __init__(self,x=0.0,y=0.0,heading=0.0): self.x=x; self.y=y; self.heading=heading

class _FakeWorldModel:
    def __init__(self,pose=None): self._pose=pose or _FakePose(); self.observations=[]; self.saved=0
    def get_robot_pose(self): return self._pose
    def update_observation(self,obs): self.observations.append(obs)
    def save(self): self.saved+=1

class _FakeDetector:
    def __init__(self,dets=None): self._dets=dets or []
    def detect(self,classes=None): return self._dets
    def localize(self,det): return det['dist_cm'],det['bearing_deg']

# --- project_point() pure math ---

def test_project_point_straight_ahead():
    pose=_FakePose(x=0.0,y=0.0,heading=0.0)
    x,y=project_point(pose,bearing_deg=0.0,distance_m=2.0)
    assert math.isclose(x,2.0,abs_tol=1e-9) and math.isclose(y,0.0,abs_tol=1e-9)

def test_project_point_left_sonar_perpendicular():
    pose=_FakePose(x=0.0,y=0.0,heading=0.0)
    x,y=project_point(pose,bearing_deg=config.SONAR_BEARING_DEG['left'],distance_m=1.0)
    assert math.isclose(x,0.0,abs_tol=1e-9)
    assert y<0 or y>0  # perpendicular to heading -- sign depends on rotation convention, just not 0

def test_project_point_accounts_for_robot_pose_and_heading():
    pose=_FakePose(x=5.0,y=5.0,heading=math.pi/2)  # facing +y
    x,y=project_point(pose,bearing_deg=0.0,distance_m=1.0)
    assert math.isclose(x,5.0,abs_tol=1e-9)
    assert math.isclose(y,6.0,abs_tol=1e-9)

# --- MappingSession ---

def test_start_stop_toggles_active_and_saves_on_stop():
    ms=MappingSession(_FakeWorldModel())
    ok,_=ms.start()
    assert ok and ms.active is True
    ok,_=ms.stop()
    assert ok and ms.active is False
    assert ms.world_model.saved==1

def test_start_twice_rejected():
    ms=MappingSession(_FakeWorldModel())
    ms.start()
    ok,msg=ms.start()
    assert ok is False

def test_stop_when_inactive_rejected_and_no_save():
    ms=MappingSession(_FakeWorldModel())
    ok,_=ms.stop()
    assert ok is False and ms.world_model.saved==0

def test_tick_inactive_records_nothing():
    wm=_FakeWorldModel()
    ms=MappingSession(wm,detector=_FakeDetector([{'class':'bottle','conf':0.9,'dist_cm':50,'bearing_deg':0.0}]))
    ms.tick({'front':999,'left':999,'right':999},0.0)
    assert wm.observations==[]

def test_tick_active_records_detections_as_object_observations():
    pose=_FakePose(x=0.0,y=0.0,heading=0.0)
    wm=_FakeWorldModel(pose)
    ms=MappingSession(wm,detector=_FakeDetector([{'class':'bottle','conf':0.9,'dist_cm':100,'bearing_deg':0.0}]))
    ms.start()
    ms.tick({'front':999,'left':999,'right':999},0.0)
    assert len(wm.observations)==1
    obs=wm.observations[0]
    assert obs.kind=='object' and obs.payload['cls']=='bottle' and obs.payload['confidence']==0.9
    assert math.isclose(obs.x,1.0,abs_tol=1e-9) and math.isclose(obs.y,0.0,abs_tol=1e-9)

def test_tick_without_detector_is_a_noop():
    wm=_FakeWorldModel()
    ms=MappingSession(wm,detector=None)
    ms.start()
    ms.tick({'front':999,'left':999,'right':999},0.0)  # must not raise, must not record
    assert wm.observations==[]

def test_abort_while_active_saves_and_deactivates():
    wm=_FakeWorldModel()
    ms=MappingSession(wm)
    ms.start()
    ms.abort('tilt fault 30.0deg')
    assert ms.active is False and wm.saved==1

def test_abort_while_inactive_is_noop():
    wm=_FakeWorldModel()
    ms=MappingSession(wm)
    ms.abort('shutdown')  # never started
    assert wm.saved==0

# --- full RoverBrain lifecycle under simulation (§19/§20 pattern, see test_sim_hardware.py) ---

_MAP_SCRIPT='''
import brain,time
b=brain.RoverBrain()
b.start()
time.sleep(1.0)
assert b._motion_enabled, f"self-test failed under simulation: {b._init_fail_reason}"

ok,msg=b.mapping.start()
assert ok, msg
b._tick(); b._tick()
assert b.mapping.active is True

# §9's passive per-tick sonar feed (brain.py) should have populated at least one obstacle by now
# -- sensors.py's simulated Sonar._ping() returns a fixed 200cm "clear path" reading, still a
# real non-timeout hit that brain.py records into the world model regardless of mapping state.
pose=b.odometry.pose
near=b.world_model.get_nearby_obstacles(pose.x,pose.y,radius_m=100.0)
assert len(near)>0, "expected at least one obstacle observation from the passive sonar feed"

ok,msg=b.mapping.stop()
assert ok, msg
assert b.mapping.active is False

b.world_model.load()  # §10 steps 7/8: save() (via mapping.stop()) then load() must round-trip cleanly
b.stop()
print("MAP_SIM_OK")
'''

def test_mapping_session_full_lifecycle_under_simulation():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_MAP_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'MAP_SIM_OK' in result.stdout, (
        f'sim-mode mapping lifecycle failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
