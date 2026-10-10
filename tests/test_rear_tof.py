import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# Rear ToF (2026-10-10): second SEN0628 facing backward, mounted upside down -- floor rows 0-1,
# Willie's left = columns 0-3 (measured with a hand, owner confirmed). Reversing stops on it the
# way forward stops on the front sensor; no reading means "unknown", which leaves reversing as before.

def test_reverse_is_refused_with_an_obstacle_behind():
    from safety import approve_motion,Rejected
    r=approve_motion('reverse',0.3,None,front_cm=200,rear_cm=config.DIST_STOP-1)
    assert isinstance(r,Rejected) and 'behind' in r.reason

def test_reverse_is_allowed_when_clear_or_unknown():
    from safety import approve_motion,ApprovedMotion
    assert isinstance(approve_motion('reverse',0.3,None,front_cm=200,rear_cm=150),ApprovedMotion)
    assert isinstance(approve_motion('reverse',0.3,None,front_cm=200,rear_cm=None),ApprovedMotion)

def test_rear_obstacle_never_blocks_forward():
    from safety import approve_motion,ApprovedMotion
    assert isinstance(approve_motion('forward',0.3,None,front_cm=200,rear_cm=5),ApprovedMotion)

def test_a_timed_reverse_aborts_when_something_appears_behind(monkeypatch):
    import safety
    calls=[]
    d=types.SimpleNamespace(reverse=lambda s: calls.append('reverse'),brake=lambda: calls.append('brake'),
                            forward=lambda s: None,turn_left=lambda s: None,turn_right=lambda s: None,
                            stop=lambda: calls.append('stop'),commanded={})
    sc=safety.SafetyController(d)
    sc.update_context(front_cm=200,tilt_deg=0,bat_tier='normal',motion_enabled=True,rear_cm=100)
    sc.reverse_for(2.0,0.3); assert calls==['reverse']
    sc.update_context(rear_cm=10); sc.tick()
    assert calls[-1]=='brake' and not sc.timed_move_active

def test_rear_geometry_is_per_sensor():
    from tof import ToFSensor,FloorProfile
    rear=ToFSensor(source=lambda: None,profile_path='/nonexistent',floor_rows=(0,1),left_columns=(0,1,2,3))
    front=ToFSensor(source=lambda: None,profile_path='/nonexistent')
    assert rear.floor_rows==(0,1) and front.floor_rows==config.TOF_FLOOR_ROWS
    # Upper rows on the rear unit are 2-7: a 30 cm return in row 3 is an obstacle, in row 0 (floor) it
    # is judged against the floor profile instead.
    rear.profile=FloorProfile([None]*64)
    assert rear._is_obstacle(3*8+2,300) and not rear._is_obstacle(0*8+2,300)

def test_rear_sides_use_willies_left():
    from tof import ToFSensor,FloorProfile
    frame=[None]*64; frame[3*8+1]=200     # column 1 = Willie's left on the rear unit
    s=ToFSensor(source=lambda: frame,profile_path='/nonexistent',floor_rows=(0,1),left_columns=(0,1,2,3))
    s.profile=FloorProfile([None]*64)
    assert s.side_obstacles_cm()==(20.0,None)

def test_rear_cm_reports_drop_as_stop_and_never_raises():
    pytest.importorskip('fcntl',reason='sensors.py needs fcntl: Linux only (CI, the rover)')
    import sensors
    a=object.__new__(sensors.SonarArray)
    a.tof_rear=types.SimpleNamespace(drop_detected=lambda: True,nearest_obstacle_cm=lambda: 80.0)
    assert a.rear_cm()==0.0
    a.tof_rear=types.SimpleNamespace(drop_detected=lambda: False,nearest_obstacle_cm=lambda: 80.0)
    assert a.rear_cm()==80.0
    def boom(): raise OSError('uart')
    a.tof_rear=types.SimpleNamespace(drop_detected=boom,nearest_obstacle_cm=boom)
    assert a.rear_cm() is None
    a.tof_rear=None
    assert a.rear_cm() is None

def test_rear_drop_ignores_the_grazing_row():
    from tof import ToFSensor,FloorProfile
    zones=[None]*64
    for i in range(24): zones[i]=300.0          # rows 0-2 profiled as floor
    frame=list(zones); frame[2*8+3]=None        # row 2 zone loses its return (grazing angle)
    s=ToFSensor(source=lambda: frame,profile_path='/nonexistent',floor_rows=(0,1,2),
                left_columns=(0,1,2,3),drop_rows=(0,1))
    s.profile=FloorProfile(zones)
    assert not s.drop_detected()
    frame[0*8+3]=None                           # a near floor row loses it: that is a real drop
    assert s.drop_detected()
