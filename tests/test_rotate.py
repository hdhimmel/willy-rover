import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import rotate
from rotate import Rotation,rotation_pulses,wheel_targets,rotation_angle_deg,corner_us

# Rotation mode (owner 2026-10-07). Geometry from the measured wheelbase/track and the measured
# steering direction; the task stops on IMU heading and watches sonar/ToF and the camera.

class _Steer:
    def __init__(self): self.pulses={}; self.centred=0
    def set_pulse(self,c,us): self.pulses[c]=us; return us
    def center_all(self): self.centred+=1

class _Drive:
    def __init__(self): self.wheels=None; self.stops=0
    def set_wheels(self,t): self.wheels=dict(t)
    def stop(self): self.stops+=1; self.wheels=None

class _IMU:
    def __init__(self,h=0.0): self.heading=h

class _Clock:
    def __init__(self): self.t=1000.0
    def __call__(self): return self.t

_CLEAR={'front':999,'left':999,'right':999}

def _task(cam=None):
    s,dr,imu,clk,said=_Steer(),_Drive(),_IMU(10.0),_Clock(),[]
    r=Rotation(s,dr,imu,None,camera_grab=cam,say=said.append,clock=clk)
    return r,s,dr,imu,clk,said

def test_corner_angle_is_the_turning_circle_tangent():
    assert abs(rotation_angle_deg()-46.1)<0.5          # atan(0.16/0.155)

def test_corners_point_along_the_circle_and_middles_stay_straight():
    p=rotation_pulses()
    # measured: +us = right on all four corners. FL and RR right, FR and RL left.
    assert p['lf']>1500 and p['rr']>1500 and p['rf']<1500 and p['lr']<1500
    assert p['lm']==1500 and p['rm']==1500

def test_corner_pulses_never_leave_the_allowed_servo_range():
    p=rotation_pulses()
    assert all(config.SERVO_MIN_US<=v<=config.SERVO_MAX_US for v in p.values())
    assert corner_us('lf',90)==config.SERVO_MAX_US and corner_us('lf',-90)==config.SERVO_MIN_US

def test_left_spin_drives_left_side_back_right_side_forward_corners_faster():
    t=wheel_targets(+1,1.0)
    assert t['lf']<0 and t['lm']<0 and t['lr']<0 and t['rf']>0 and t['rm']>0 and t['rr']>0
    assert abs(t['rf'])==1.0 and abs(abs(t['rm'])-0.155/0.2223)<0.01
    assert wheel_targets(-1,1.0)['lf']>0

def test_steers_first_drives_after_settle_and_stops_on_heading():
    r,s,dr,imu,clk,_=_task()
    ok,_=r.start(90)
    assert ok and r.state=='SETTLE' and s.pulses and dr.wheels is None
    clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    assert r.state=='SPIN' and dr.wheels['rf']>0
    imu.heading=10+40; clk.t+=0.5; r.tick(_CLEAR,0)
    assert r.state=='SPIN'
    imu.heading=10+90-config.ROTATE_STOP_EARLY_DEG; clk.t+=0.5; r.tick(_CLEAR,0)
    assert r.state=='DONE' and dr.stops==1 and s.centred==1

def test_heading_wraps_across_180():
    r,s,dr,imu,clk,_=_task(); imu.heading=170.0
    r.start(40); clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    imu.heading=-155.0                         # +35 deg through the wrap
    clk.t+=0.2; r.tick(_CLEAR,0)
    assert r.state=='DONE'

def test_something_close_stops_the_spin_and_says_so():
    r,s,dr,imu,clk,said=_task()
    r.start(90); clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    r.tick({'front':999,'left':8,'right':999},0)
    assert r.state=='FAILED' and dr.stops==1 and 'centimetres' in said[-1]

def test_turning_the_wrong_way_stops():
    r,s,dr,imu,clk,_=_task()
    r.start(90); clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    imu.heading=10-config.ROTATE_WRONG_WAY_DEG-1; r.tick(_CLEAR,0)
    assert r.state=='FAILED' and 'wrong way' in r.fail_reason

def test_a_turn_that_is_not_happening_times_out():
    r,s,dr,imu,clk,said=_task()
    r.start(90); clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    clk.t+=config.ROTATE_TIMEOUT_S+0.1; r.tick(_CLEAR,0)
    assert r.state=='FAILED' and 'only turned' in said[-1]

def test_camera_disagreeing_with_the_gyro_stops(monkeypatch):
    r,s,dr,imu,clk,said=_task(cam=lambda:None)
    r.start(180); clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    monkeypatch.setattr(r._cam,'update',lambda:2.0)      # scene barely moved
    imu.heading=10+60; clk.t+=config.ROTATE_CAMERA_GRACE_S+0.1; r.tick(_CLEAR,0)
    assert r.state=='FAILED' and 'camera' in said[-1]

def test_camera_agreeing_lets_it_finish(monkeypatch):
    r,s,dr,imu,clk,said=_task(cam=lambda:None)
    r.start(90); clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    monkeypatch.setattr(r._cam,'update',lambda:80.0)
    imu.heading=10+88; clk.t+=config.ROTATE_CAMERA_GRACE_S+0.1; r.tick(_CLEAR,0)
    assert r.state=='DONE'

def test_abort_stops_and_recentres():
    r,s,dr,imu,clk,_=_task()
    r.start(90); clk.t+=config.ROTATE_SETTLE_S; r.tick(_CLEAR,0)
    r.abort('voice stop')
    assert r.state=='ABORTED' and dr.stops==1 and s.centred==1 and not r.active

def test_steering_is_reasserted_before_the_idle_release():
    assert config.ROTATE_RESTEER_S<config.STEER_RELEASE_AFTER_S
    r,s,dr,imu,clk,_=_task()
    r.start(90); s.pulses.clear()
    clk.t+=config.ROTATE_RESTEER_S; r.tick(_CLEAR,0)
    assert s.pulses
