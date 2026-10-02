import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-02 gap closures, pinned:
#   FR-800-004  a dead sonar channel is named (stuck-ECHO flag or per-channel staleness)
#   FR-800-001  IMU exposes heading (yaw) from the quaternion
#   FR-500-003  wheels turning with no command are reported once per episode

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types,math,config
import sensors, brain
from brain import RoverBrain
config.SIMULATE_HARDWARE=False   # after import: exercise the real-hardware branches

# --- sonar: frame fields per firmware/README: [.., .., .., f_mm, f_age, l_mm, l_age, r_mm, r_age, flags]
S=sensors.SonarArray.__new__(sensors.SonarArray)
frame=["$S",1,0, 500,10, 600,999, 700,10, 0b100]
S._link=types.SimpleNamespace(fresh=lambda k,s: frame)
f=S.failed_channels
assert set(f)=={"left","right"}, f
assert "stuck" in f["right"] and "not updated" in f["left"], f
frame[9]=0; frame[6]=10
assert S.failed_channels=={}, S.failed_channels
S._link=types.SimpleNamespace(fresh=lambda k,s: None)
assert S.failed_channels=={}   # a whole stale link is is_healthy's job

# --- IMU heading: a quaternion for a 90 deg yaw
import threading
I=sensors.IMU.__new__(sensors.IMU); I._lock=threading.Lock(); I._last_q=None
import time as _t; I._last_change=_t.monotonic()
h=math.radians(90)/2
I._bno=types.SimpleNamespace(quaternion=(0.0,0.0,math.sin(h),math.cos(h)))
I._update()
assert abs(I.heading-90.0)<0.5, I.heading

# --- uncommanded motion
clock=[0.0]; brain.time.time=lambda: clock[0]
events=[]; brain.log_event=lambda lg,ev,**k: events.append(ev)
ns=types.SimpleNamespace(_uncmd_since=None,_uncmd_reported=False,
    motors=types.SimpleNamespace(commanded={"lf":False,"rf":False}),
    encoders=types.SimpleNamespace(is_healthy=True,counts_per_sec={"lf":200.0,"rf":0.0}))
chk=types.MethodType(RoverBrain._check_uncommanded_motion,ns)
chk(); clock[0]+=1; chk(); assert events==[]
clock[0]+=config.UNCOMMANDED_GRACE_S; chk(); chk()
assert events==["UNCOMMANDED_MOTION"], events
ns.motors.commanded["lf"]=True; chk(); ns.motors.commanded["lf"]=False
clock[0]+=0.1; chk(); assert events==["UNCOMMANDED_MOTION"]   # commanding resets, grace again
print("SENSOR_GAPS_OK")
'''

def test_sensor_gap_closures():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'SENSOR_GAPS_OK' in r.stdout, r.stdout+r.stderr

def test_vision_range_uses_per_class_width():
    # FR-1000-006 / FR-1700-008: a person is ranged with ~45 cm, not the 8 cm fallback.
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    code=('import vision\n'
          'D=vision.ObjectDetector.__new__(vision.ObjectDetector)\n'
          'p,_=D.localize({"bbox":(270,0,370,10),"frame_w":640,"class":"person"})\n'
          'c,_=D.localize({"bbox":(270,0,370,10),"frame_w":640,"class":"cup"})\n'
          'u,_=D.localize({"bbox":(270,0,370,10),"frame_w":640,"class":"unicorn"})\n'
          'assert abs(p/c-45/8)<1e-6 and u==c, (p,c,u)\n'
          'print("WIDTH_OK")\n')
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'WIDTH_OK' in r.stdout, r.stdout+r.stderr

def test_come_here_searches_before_giving_up():
    # FR-1000-006: nobody in view -> PURSUIT_SEARCH_STEPS turns, then FAILED; a person found
    # mid-sweep moves straight to APPROACH.
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    code=('import types,config\n'
          'from pursuit_task import PursuitTask\n'
          'turns=[]\n'
          'safety=types.SimpleNamespace(timed_move_active=False,stop=lambda:None,'
          'turn_left_for=lambda t,s: turns.append(t))\n'
          'seen=[False]\n'
          'det=types.SimpleNamespace(detect=lambda classes=None: [{"conf":0.9,"class":"person","bbox":(0,0,1,1),"frame_w":640}] if seen[0] else [],'
          'localize=lambda d:(300.0,0.0))\n'
          'p=PursuitTask(safety,det); p.start("come_here")\n'
          'for _ in range((config.PURSUIT_LOOK_TICKS+1)*(config.PURSUIT_SEARCH_STEPS+1)+5): p.tick({},0)\n'
          'assert len(turns)==config.PURSUIT_SEARCH_STEPS and p.state=="FAILED", (len(turns),p.state)\n'
          'turns.clear(); p.reset(); p.start("come_here")\n'
          'for _ in range(config.PURSUIT_LOOK_TICKS+2): p.tick({},0)\n'
          'seen[0]=True; p.tick({},0)\n'
          'assert len(turns)==1 and p.state=="APPROACH", (turns,p.state)\n'
          'print("SWEEP_OK")\n')
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'SWEEP_OK' in r.stdout, r.stdout+r.stderr

def test_odometry_takes_rotation_from_the_imu_when_enabled():
    # FR-1000-003: with ODOM_USE_IMU_HEADING the tick's rotation is the IMU yaw delta; wheels
    # still give distance; a None yaw falls back to the wheels.
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    code=('import math,types,config\n'
          'config.ODOM_USE_IMU_HEADING=True\n'
          'import odometry\n'
          'counts={w:0 for w in ("lf","lm","lr","rf","rm","rr")}\n'
          'enc=types.SimpleNamespace(is_healthy=True,counts=counts)\n'
          'yaw=[10.0]\n'
          'o=odometry.Odometry(enc,heading_source=lambda: yaw[0])\n'
          'o.update(); yaw[0]=40.0; o.update()\n'
          'assert abs(math.degrees(o.pose.heading)-30.0)<1e-6, math.degrees(o.pose.heading)\n'
          'yaw[0]=None; o.update(); assert abs(math.degrees(o.pose.heading)-30.0)<1e-6\n'
          'config.ODOM_USE_IMU_HEADING=False; yaw[0]=90.0; o.update()\n'
          'assert abs(math.degrees(o.pose.heading)-30.0)<1e-6\n'
          'print("ODOM_OK")\n')
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'ODOM_OK' in r.stdout, r.stdout+r.stderr
