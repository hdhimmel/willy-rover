import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-02, seen on the rover: in a latched fault, emergency_stop() every tick woke the
# released drivers and braked, the ramp loop released them again, and the wake+brake pin writes
# made every wheel twitch. Pinned: brake() on a stopped, released drive touches nothing; a brake
# while moving still writes brake to every wheel.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import config,time
from motors import DriveBase
d=DriveBase()
writes=[]; wakes=[]
d._write=lambda w,v: writes.append((w,v))
real_wake=d._wake; d._wake=lambda: (wakes.append(1),real_wake())
with d._lock: d._coast()
d.brake(); d.brake(); d.brake()
assert writes==[] and wakes==[], (writes,wakes)
with d._lock:
    d._coasting=False; d._actual["lf"]=0.5; d._target["lf"]=0.5
d.brake()
assert sorted(w for w,v in writes)==sorted(d._WHEELS) and all(v==0.0 for w,v in writes), writes
d._running=False
print("BRAKE_OK")
'''

def test_brake_does_not_wake_a_stopped_released_drive():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'BRAKE_OK' in r.stdout, r.stdout+r.stderr
