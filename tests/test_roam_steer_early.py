import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config
from safety import approve_curve,Rejected

# 2026-10-14 (owner): curve away early (within ROAM_STEER_EARLY_CM) toward the clearer side while
# roaming, instead of driving straight at things until the 40 cm slow-down.

def test_curve_is_gated_like_motion_but_allowed_while_moving():
    assert approve_curve(15).speed==15
    assert approve_curve(90).speed==config.ROAM_STEER_MAX_DEG
    assert isinstance(approve_curve(10,motion_enabled=False),Rejected)
    assert isinstance(approve_curve(10,tilt_deg=config.IMU_TILT_LIMIT+1),Rejected)
    assert isinstance(approve_curve(10,bat_tier='safe'),Rejected)

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT='''
import types,time,config,avoidance
from brain import RoverBrain
def brain(side):
    b=types.SimpleNamespace(_state='ROAM',calls=[],_curve_deg=0.0)
    b.safety=types.SimpleNamespace(steer_curve=lambda deg: (b.calls.append(('curve',deg)),deg)[1])
    b.sonars=types.SimpleNamespace(tof=None)
    avoidance.choose_turn=lambda d,tof=None,det=None: side
    b._roam_curve=types.MethodType(RoverBrain._roam_curve,b)
    return b
D={'front':80,'left':50,'right':150}
# something 80 cm ahead, right is clearer -> curve right
b=brain('turn_right'); b._roam_curve(D,80.0); assert b.calls==[('curve',config.ROAM_STEER_DEG)], b.calls
# path clear -> straighten
b._roam_curve(D,300.0); assert b.calls[-1]==('curve',0.0), b.calls
# left clearer -> curve left
b=brain('turn_left'); b._roam_curve(D,80.0); assert b.calls==[('curve',-config.ROAM_STEER_DEG)]
# no flip-flop inside the hold time
avoidance.choose_turn=lambda d,tof=None,det=None: 'turn_right'
b._roam_curve(D,80.0); assert b.calls==[('curve',-config.ROAM_STEER_DEG)], b.calls
# after the hold it may switch
b._curve_t-=config.ROAM_STEER_HOLD_S+0.1; b._roam_curve(D,80.0); assert b.calls[-1]==('curve',config.ROAM_STEER_DEG)
# far away: nothing happens
b=brain('turn_right'); b._roam_curve(D,config.ROAM_STEER_EARLY_CM+1); assert b.calls==[]
print('STEER_EARLY_OK')
'''

def test_roam_curves_toward_the_clearer_side_and_straightens():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert 'STEER_EARLY_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr[-3000:]}'
