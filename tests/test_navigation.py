import os,sys,math,tempfile,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from world_model import WorldModel
from navigation import Navigator,Mission

# Pure-logic tests for navigation.py -- no hardware needed (§20/§11 of
# docs/WildWilly_Claude_Fix_Implementation_Plan.md). Fakes stand in for safety.SafetyController
# (Navigator only ever calls its public request/forward/turn_*_for/stop/timed_move_active
# interface, same contract retrieval_task.py already relies on) and odometry.Odometry (Navigator
# only reads .pose). Route-resolution tests use a real WorldModel against a temp db, since that
# logic is the point under test (get_room/all_rooms/all_doorways/get_route), not something worth
# re-faking.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class _FakePose:
    def __init__(self,x=0.0,y=0.0,heading=0.0): self.x=x; self.y=y; self.heading=heading

class _FakeOdometry:
    def __init__(self,pose=None): self.pose=pose or _FakePose()

class _FakeSafety:
    def __init__(self):
        self.timed_move_active=False; self.calls=[]
    def stop(self): self.calls.append(('stop',))
    def forward(self,speed=None): self.calls.append(('forward',speed))
    def turn_left_for(self,duration,speed=None):
        self.calls.append(('turn_left_for',duration,speed)); self.timed_move_active=True
    def turn_right_for(self,duration,speed=None):
        self.calls.append(('turn_right_for',duration,speed)); self.timed_move_active=True
    def request(self,action,speed=None,duration=None):
        self.calls.append(('request',action,speed,duration))
        if duration is not None: self.timed_move_active=True

_CLEAR={'front':999.0,'left':999.0,'right':999.0}

def _wm(tmp_path):
    return WorldModel(_FakeOdometry(),db_path=os.path.join(tmp_path,'nav_test.db'))

# --- route resolution ---

def test_mission_raw_xy_is_a_single_waypoint():
    with tempfile.TemporaryDirectory() as d:
        nav=Navigator(_FakeSafety(),_FakeOdometry(),_wm(d))
        ok,_=nav.start(Mission(xy=(3.0,4.0)))
        assert ok and nav._waypoints==[(3.0,4.0)]

def test_mission_known_route_uses_its_waypoints():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d); wm.add_route('to_kitchen',[(1.0,1.0),(2.0,2.0)])
        nav=Navigator(_FakeSafety(),_FakeOdometry(),wm)
        ok,_=nav.start(Mission(route='to_kitchen'))
        assert ok and nav._waypoints==[(1.0,1.0),(2.0,2.0)]

def test_mission_unknown_route_fails_to_start():
    with tempfile.TemporaryDirectory() as d:
        nav=Navigator(_FakeSafety(),_FakeOdometry(),_wm(d))
        ok,msg=nav.start(Mission(route='nonexistent'))
        assert ok is False and nav.state=='FAILED'

def test_mission_unknown_room_fails_to_start():
    with tempfile.TemporaryDirectory() as d:
        nav=Navigator(_FakeSafety(),_FakeOdometry(),_wm(d))
        ok,_=nav.start(Mission(room='nonexistent'))
        assert ok is False and nav.state=='FAILED'

def test_mission_room_no_current_room_falls_back_to_target_centroid():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d); wm.add_room('kitchen',cx=5.0,cy=5.0,radius_m=1.0)
        odo=_FakeOdometry(_FakePose(x=100.0,y=100.0))  # nowhere near any known room
        nav=Navigator(_FakeSafety(),odo,wm)
        ok,_=nav.start(Mission(room='kitchen'))
        assert ok and nav._waypoints==[(5.0,5.0)]

def test_mission_room_graph_path_through_doorway():
    with tempfile.TemporaryDirectory() as d:
        wm=_wm(d)
        wm.add_room('hallway',cx=0.0,cy=0.0,radius_m=1.0)
        wm.add_room('kitchen',cx=5.0,cy=0.0,radius_m=1.0)
        wm.add_doorway('hallway','kitchen',x=2.5,y=0.0)
        odo=_FakeOdometry(_FakePose(x=0.0,y=0.0))  # inside hallway's radius
        nav=Navigator(_FakeSafety(),odo,wm)
        ok,_=nav.start(Mission(room='kitchen'))
        assert ok and nav._waypoints==[(5.0,0.0)]  # single-hop path -> just the target centroid

# --- local planner (_seeking/_avoiding) ---

def test_seeking_drives_forward_when_aligned_and_far():
    with tempfile.TemporaryDirectory() as d:
        odo=_FakeOdometry(_FakePose(x=0.0,y=0.0,heading=0.0))
        safety=_FakeSafety()
        nav=Navigator(safety,odo,_wm(d))
        nav.start(Mission(xy=(5.0,0.0)))
        nav.tick(_CLEAR,0.0)
        assert ('forward',config.SPEED_SLOW) in safety.calls
        assert nav.state=='SEEKING'

def test_seeking_turns_when_bearing_error_large():
    with tempfile.TemporaryDirectory() as d:
        odo=_FakeOdometry(_FakePose(x=0.0,y=0.0,heading=0.0))
        safety=_FakeSafety()
        nav=Navigator(safety,odo,_wm(d))
        nav.start(Mission(xy=(0.0,5.0)))  # waypoint is 90deg off current heading
        nav.tick(_CLEAR,0.0)
        assert any(c[0]=='turn_left_for' for c in safety.calls)

def test_seeking_arrival_advances_and_completes_on_last_waypoint():
    with tempfile.TemporaryDirectory() as d:
        odo=_FakeOdometry(_FakePose(x=0.0,y=0.0,heading=0.0))
        safety=_FakeSafety()
        nav=Navigator(safety,odo,_wm(d))
        nav.start(Mission(xy=(0.0,0.0)))  # already at the only waypoint
        nav.tick(_CLEAR,0.0)
        assert nav.state=='DONE'
        assert ('stop',) in safety.calls

def test_seeking_obstacle_transitions_to_avoiding():
    with tempfile.TemporaryDirectory() as d:
        odo=_FakeOdometry(_FakePose(x=0.0,y=0.0,heading=0.0))
        safety=_FakeSafety()
        nav=Navigator(safety,odo,_wm(d))
        nav.start(Mission(xy=(5.0,0.0)))
        nav.tick({'front':10.0,'left':999.0,'right':999.0},0.0)  # under DIST_STOP
        assert nav.state=='AVOIDING'

def test_avoiding_resumes_seeking_once_clear():
    with tempfile.TemporaryDirectory() as d:
        odo=_FakeOdometry(_FakePose(x=0.0,y=0.0,heading=0.0))
        safety=_FakeSafety()
        nav=Navigator(safety,odo,_wm(d))
        nav.start(Mission(xy=(5.0,0.0)))
        nav.tick({'front':10.0,'left':999.0,'right':999.0},0.0)
        assert nav.state=='AVOIDING'
        nav.tick(_CLEAR,0.0)  # front now clear
        assert nav.state=='SEEKING'

def test_avoiding_timeout_fails():
    with tempfile.TemporaryDirectory() as d:
        odo=_FakeOdometry(_FakePose(x=0.0,y=0.0,heading=0.0))
        safety=_FakeSafety()
        nav=Navigator(safety,odo,_wm(d))
        nav.start(Mission(xy=(5.0,0.0)))
        nav.state='AVOIDING'; nav._avoid_start=0.0  # force elapsed time past STUCK_TIMEOUT
        nav.tick({'front':10.0,'left':999.0,'right':999.0},0.0)
        assert nav.state=='FAILED'

# --- start/abort/reset ---

def test_start_while_active_rejected():
    with tempfile.TemporaryDirectory() as d:
        nav=Navigator(_FakeSafety(),_FakeOdometry(),_wm(d))
        nav.start(Mission(xy=(1.0,1.0)))
        ok,_=nav.start(Mission(xy=(2.0,2.0)))
        assert ok is False

def test_abort_while_active_stops_and_marks_aborted():
    with tempfile.TemporaryDirectory() as d:
        safety=_FakeSafety()
        nav=Navigator(safety,_FakeOdometry(),_wm(d))
        nav.start(Mission(xy=(1.0,1.0)))
        nav.abort('tilt fault')
        assert nav.state=='ABORTED' and ('stop',) in safety.calls

def test_reset_returns_to_idle():
    with tempfile.TemporaryDirectory() as d:
        nav=Navigator(_FakeSafety(),_FakeOdometry(),_wm(d))
        nav.start(Mission(xy=(1.0,1.0))); nav.abort('x')
        nav.reset()
        assert nav.state=='IDLE'

# --- full RoverBrain lifecycle under simulation (§19/§20 pattern) ---

_NAV_SCRIPT='''
import brain,time
b=brain.RoverBrain()
b.start()
time.sleep(1.0)
assert b._motion_enabled, f"self-test failed under simulation: {b._init_fail_reason}"

from navigation import Mission
ok,msg=b.navigator.start(Mission(xy=(1.0,0.0)))
assert ok, msg
b._go("NAVIGATE")
for _ in range(5): b._tick()
assert b._state in ("NAVIGATE","IDLE"), f"unexpected state {b._state}"

b.stop()
print("NAV_SIM_OK")
'''

def test_navigation_full_lifecycle_under_simulation():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_NAV_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'NAV_SIM_OK' in result.stdout, (
        f'sim-mode navigation lifecycle failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
