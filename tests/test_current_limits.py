import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-02 gap closures, pinned:
#   FR-700-001  arm rail over ARM_CURRENT_LIMIT_A for ARM_CURRENT_LIMIT_S -> arm released
#   FR-200-002  bus/steering rail over OVERCURRENT_LIMIT_A for OVERCURRENT_S -> reason returned
#   FR-2000-008 the STUCK alert's capture+SMTP no longer runs on the tick thread

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types,time as _t,config,threading
import brain
from brain import RoverBrain
clock=[100.0]
brain.time.time=lambda: clock[0]

def fb(rails):
    released=[]
    ns=types.SimpleNamespace(_arm_over_since=None,_oc_since={},
        current=types.SimpleNamespace(rail=lambda n:{"current_a":rails.get(n,0.0),"voltage_v":12.0}),
        arm=types.SimpleNamespace(released=False,release=lambda: released.append(1)),
        voice=types.SimpleNamespace(available=False))
    for m in ("_check_arm_current","_check_overcurrent"): setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
    ns.released=released; return ns

# arm: a short spike is tolerated, a sustained one releases
f=fb({"arm_6v":config.ARM_CURRENT_LIMIT_A+1})
f._check_arm_current(); clock[0]+=config.ARM_CURRENT_LIMIT_S/2; f._check_arm_current()
assert f.released==[]
clock[0]+=config.ARM_CURRENT_LIMIT_S; f._check_arm_current()
assert f.released==[1], f.released

# overcurrent: per rail, held for OVERCURRENT_S
f=fb({"bus_12v":config.OVERCURRENT_LIMIT_A["bus_12v"]+1})
assert f._check_overcurrent()==""
clock[0]+=config.OVERCURRENT_S+0.1
r=f._check_overcurrent(); assert "bus_12v" in r, r
f=fb({"bus_12v":1.0}); clock[0]+=5; assert f._check_overcurrent()==""

# STUCK alert returns at once even when the send takes seconds
config.ENABLE_STUCK_ALERT_EMAIL=True
sent=threading.Event()
def slow_send(*a,**k): _t.sleep(2); sent.set()
ns=types.SimpleNamespace(_stuck_alert_t=0.0,_stuck_alert_count=0,_stuck_count=1,
    email=types.SimpleNamespace(available=True,send_alert=slow_send),
    detector=types.SimpleNamespace(capture_still=lambda: None),
    world_model=types.SimpleNamespace(get_robot_pose=lambda: types.SimpleNamespace(x=0,y=0,heading=0)),
    sonars=types.SimpleNamespace(distances={"front":50,"left":60,"right":70}),
    adc=types.SimpleNamespace(battery_volts=11.5))
clock[0]+=10**6
t0=_t.perf_counter(); RoverBrain._send_stuck_alert(ns); dt=_t.perf_counter()-t0
assert dt<0.5, dt
assert sent.wait(5), "the alert must still be sent, on its own thread"
print("LIMITS_OK")
'''

def test_current_limits_and_nonblocking_alert():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'LIMITS_OK' in r.stdout, r.stdout+r.stderr
