import os,sys,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import avoidance
from tof import ToFSensor,FloorProfile
from world_model import WorldModel
from navigation import Navigator,Mission
from come_to_me_task import ComeToMeTask

# FR-1000-006 come to me, its doorway routing and shut-door asking, and the FR-1000-002 turn
# choice (side sonar + ToF columns + camera). Pure logic against fakes, same as test_navigation.

class _Pose:
    def __init__(self,x=0.0,y=0.0,heading=0.0): self.x=x; self.y=y; self.heading=heading

class _Odo:
    def __init__(self,pose=None): self.pose=pose or _Pose()

class _Safety:
    def __init__(self): self.timed_move_active=False; self.calls=[]
    def stop(self): self.calls.append(('stop',))
    def forward(self,speed=None): self.calls.append(('forward',speed))
    def turn_left_for(self,t,speed=None): self.calls.append(('turn_left_for',t)); self.timed_move_active=True
    def turn_right_for(self,t,speed=None): self.calls.append(('turn_right_for',t)); self.timed_move_active=True
    def request(self,action,speed=None,duration=None):
        self.calls.append(('request',action,duration))
        if duration is not None: self.timed_move_active=True

_CLEAR={'front':999.0,'left':999.0,'right':999.0}
_BLOCKED={'front':10.0,'left':100.0,'right':100.0}

def _tmp(): return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

def _house(d,odo):
    wm=WorldModel(odo,db_path=os.path.join(d,'ctm.db'))
    wm.add_room('lounge',cx=0.0,cy=0.0,radius_m=1.0)
    wm.add_room('hall',cx=4.0,cy=0.0,radius_m=1.0)
    wm.add_room('kitchen',cx=8.0,cy=0.0,radius_m=1.0)
    wm.add_doorway('lounge','hall',x=2.0,y=0.0)
    wm.add_doorway('hall','kitchen',x=6.0,y=0.0)
    return wm

# --- doorway routing (design §4.4) ---

def test_multi_hop_route_goes_through_each_doorway_then_each_centroid():
    with _tmp() as d:
        odo=_Odo(); nav=Navigator(_Safety(),odo,_house(d,odo))
        ok,_=nav.start(Mission(room='kitchen'))
        assert ok and nav._waypoints==[(2.0,0.0),(4.0,0.0),(6.0,0.0),(8.0,0.0)]
        assert nav._doorway_wps=={0,2}

# --- shut door, ask-only (design §4.7) ---

def _at_first_door(d,said):
    odo=_Odo(); safety=_Safety()
    nav=Navigator(safety,odo,_house(d,odo),say=said.append)
    nav.start(Mission(room='kitchen'))
    odo.pose=_Pose(x=1.6)            # 40 cm short of the lounge/hall doorway
    return nav,safety

def test_blocked_at_a_labelled_doorway_asks_instead_of_avoiding():
    with _tmp() as d:
        said=[]; nav,safety=_at_first_door(d,said)
        nav.tick(_BLOCKED,0.0)
        assert nav.state=='DOOR_WAIT' and nav.active
        assert len(said)==1 and 'kitchen' in said[0]
        assert not any(c[0]=='request' for c in safety.calls)   # no reverse-and-turn at a door

def test_blocked_away_from_a_doorway_is_ordinary_avoidance():
    with _tmp() as d:
        said=[]; nav,_=_at_first_door(d,said)
        nav._wp_index=1; nav.odometry.pose=_Pose(x=3.6)          # heading for the hall centroid
        nav.tick(_BLOCKED,0.0)
        assert nav.state=='AVOIDING' and said==[]

def test_door_opening_resumes_at_the_same_waypoint():
    with _tmp() as d:
        said=[]; nav,_=_at_first_door(d,said)
        nav.tick(_BLOCKED,0.0); nav.tick(_CLEAR,0.0)
        assert nav.state=='SEEKING' and nav._wp_index==0

def test_door_never_opening_fails_after_the_last_ask():
    with _tmp() as d:
        said=[]; nav,_=_at_first_door(d,said)
        nav.tick(_BLOCKED,0.0)
        for _ in range(config.DOOR_MAX_ASKS):
            nav._door_since-=config.DOOR_WAIT_S+1; nav.tick(_BLOCKED,0.0)
        assert nav.state=='FAILED' and nav.fail_reason=='door shut'
        assert len(said)==config.DOOR_MAX_ASKS+1 and 'nobody let me in' in said[-1]

def test_abort_reaches_a_rover_waiting_at_a_door():
    with _tmp() as d:
        said=[]; nav,_=_at_first_door(d,said)
        nav.tick(_BLOCKED,0.0); nav.abort('voice stop')
        assert nav.state=='ABORTED'

# --- ComeToMeTask sequencing ---

class _Nav:
    def __init__(self): self.state='IDLE'; self.fail_reason=''; self.missions=[]; self.aborted=None
    @property
    def active(self): return self.state in('SEEKING','AVOIDING','DOOR_WAIT')
    def start(self,m): self.missions.append(m); self.state='SEEKING'; return True,'started'
    def abort(self,r): self.state='ABORTED'; self.fail_reason=r; self.aborted=r
    def reset(self): self.state='IDLE'
    def tick(self,d,t): pass

class _Pursuit:
    def __init__(self): self.state='IDLE'; self._fail_reason=''; self.modes=[]
    @property
    def active(self): return self.state in('LOCALIZE','APPROACH','FOLLOWING')
    def start(self,mode='come_here'): self.modes.append(mode); self.state='LOCALIZE'; return True,'started'
    def abort(self,r): self.state='ABORTED'; self._fail_reason=r
    def reset(self): self.state='IDLE'
    def tick(self,d,t): pass

class _Det:
    def __init__(self,available=True): self.available=available

def _task(d,pose=None,camera=True):
    odo=_Odo(pose or _Pose()); wm=_house(d,odo); said=[]
    nav=_Nav(); pur=_Pursuit()
    return ComeToMeTask(nav,pur,wm,_Det(camera),say=said.append),nav,pur,said

def test_unknown_room_refuses_before_moving():
    with _tmp() as d:
        t,nav,pur,said=_task(d)
        ok,_=t.start('attic')
        assert not ok and nav.missions==[] and "don't know where the attic" in said[0]

def test_no_camera_refuses_before_moving():
    with _tmp() as d:
        t,nav,pur,said=_task(d,camera=False)
        ok,_=t.start('kitchen')
        assert not ok and nav.missions==[] and 'camera' in said[0]

def test_navigate_then_find_then_found():
    with _tmp() as d:
        t,nav,pur,said=_task(d)
        ok,_=t.start('Kitchen')
        assert ok and t.state=='LEG_NAVIGATE' and nav.missions[0].room=='kitchen'
        nav.state='DONE'; t.tick(_CLEAR,0.0)
        assert t.state=='LEG_FIND' and pur.modes==['come_here']
        pur.state='DONE'; t.tick(_CLEAR,0.0)
        assert t.state=='DONE' and said[-1]=='Found you.'

def test_already_in_the_room_skips_navigation():
    with _tmp() as d:
        t,nav,pur,said=_task(d,pose=_Pose(x=8.0))
        ok,_=t.start('kitchen')
        assert ok and t.state=='LEG_FIND' and nav.missions==[]

def test_navigation_failure_never_starts_the_find_leg():
    with _tmp() as d:
        t,nav,pur,said=_task(d)
        t.start('kitchen'); nav.state='FAILED'; nav.fail_reason='stuck avoiding obstacle'
        t.tick(_CLEAR,0.0)
        assert t.state=='FAILED' and pur.modes==[] and "couldn't get to the kitchen" in said[-1]

def test_shut_door_failure_is_not_announced_twice():
    with _tmp() as d:
        t,nav,pur,said=_task(d)
        t.start('kitchen'); n=len(said); nav.state='FAILED'; nav.fail_reason='door shut'
        t.tick(_CLEAR,0.0)
        assert t.state=='FAILED' and len(said)==n

def test_arrived_but_nobody_found_is_its_own_outcome():
    with _tmp() as d:
        t,nav,pur,said=_task(d)
        t.start('kitchen'); nav.state='DONE'; t.tick(_CLEAR,0.0)
        pur.state='FAILED'; t.tick(_CLEAR,0.0)
        assert t.state=='FAILED' and "in the kitchen but I can't see you" in said[-1]

def test_abort_in_either_leg_stops_that_leg():
    with _tmp() as d:
        t,nav,pur,said=_task(d)
        t.start('kitchen'); t.abort('tilt')
        assert t.state=='ABORTED' and nav.aborted=='tilt'
        t,nav,pur,said=_task(d)
        t.start('kitchen'); nav.state='DONE'; t.tick(_CLEAR,0.0); t.abort('voice stop')
        assert t.state=='ABORTED' and pur.state=='ABORTED'

def test_a_leg_aborted_from_brain_does_not_block_the_next_command():
    with _tmp() as d:
        t,nav,pur,said=_task(d)
        t.start('kitchen'); nav.abort('low battery')     # brain's Directive site, not the task
        assert not t.active
        nav.reset(); ok,_=t.start('hall')
        assert ok

# --- FR-1000-002 turn choice ---

class _ToF:
    available=True
    def __init__(self,sides): self.sides=sides
    def side_obstacles_cm(self): return self.sides

class _Cam:
    available=True
    def __init__(self,dets): self.dets=dets
    def detect(self,classes=None): return [{'d':d,'b':b} for d,b in self.dets]
    def localize(self,det): return det['d'],det['b']

def test_sonar_alone_still_picks_the_more_open_side():
    assert avoidance.choose_turn({'front':10,'left':30,'right':80})=='turn_right'
    assert avoidance.choose_turn({'front':10,'left':80,'right':30})=='turn_left'
    assert avoidance.choose_turn({'front':10,'left':50,'right':50}) is None

def test_tof_sees_a_chair_leg_sonar_misses():
    d={'front':10,'left':30,'right':80}
    assert avoidance.choose_turn(d,tof=_ToF((None,20.0)))=='turn_left'

def test_camera_biases_the_turn_away_from_what_it_sees():
    d={'front':10,'left':80,'right':70}
    assert avoidance.choose_turn(d,detector=_Cam([(40.0,-20.0)]))=='turn_right'

def test_camera_detection_dead_ahead_counts_for_neither_side():
    d={'front':10,'left':80,'right':70}
    assert avoidance.choose_turn(d,detector=_Cam([(5.0,0.0)]))=='turn_left'

def test_camera_off_by_config_is_ignored(monkeypatch):
    monkeypatch.setattr(config,'AVOID_USE_CAMERA',False)
    d={'front':10,'left':80,'right':70}
    assert avoidance.choose_turn(d,detector=_Cam([(40.0,-20.0)]))=='turn_left'

def test_a_broken_sensor_never_makes_a_side_look_better():
    class _Bad:
        available=True
        def side_obstacles_cm(self): raise IOError('uart')
        def detect(self,classes=None): raise RuntimeError('hailo')
    d={'front':10,'left':30,'right':80}
    assert avoidance.choose_turn(d,tof=_Bad(),detector=_Bad())=='turn_right'

def test_tof_reports_no_sides_until_its_orientation_is_known(monkeypatch):
    frame=[1000.0]*config.TOF_ZONES; frame[0]=200.0            # one obstacle zone, column 0
    s=ToFSensor(source=lambda:list(frame)); s.profile=FloorProfile([1000.0]*config.TOF_ZONES)
    monkeypatch.setattr(config,'TOF_LEFT_COLUMNS',None)
    assert s.side_obstacles_cm()==(None,None)
    monkeypatch.setattr(config,'TOF_LEFT_COLUMNS',(0,1,2,3))
    assert s.side_obstacles_cm()==(20.0,None)
    monkeypatch.setattr(config,'TOF_LEFT_COLUMNS',(4,5,6,7))
    assert s.side_obstacles_cm()==(None,20.0)

# --- voice ---

def test_voice_fast_path_parses_the_room():
    import voice
    fp=lambda t: voice.VoicePipeline._fast_path(None,t)
    assert fp("Willie, I'm in the kitchen, come to me")=={'intent':'come_to_me','args':{'room':'kitchen'},'reply':''}
    assert fp('come and find me in the living room')['args']=={'room':'living room'}
    assert fp('this is the kitchen')['intent']=='name_room'
    assert fp("I'm in the kitchen") is None
