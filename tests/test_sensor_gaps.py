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
