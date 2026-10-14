import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-14: ROAM/SLOW brake for what the camera sees in his path (he hit a chair and a coffee
# table that sonar and ToF looked under), and a roam that sets off with something close turns
# away first instead of creeping at it. Subprocess under WILLY_SIMULATE=1, as test_brain_wave.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types,config,arm_ik
from brain import RoverBrain
def brain(cam_cm):
    b=types.SimpleNamespace(_state='ROAM',_last_action='none',calls=[],_roam_fresh=False)
    b.safety=types.SimpleNamespace(obstacle_stop=lambda: b.calls.append('brake'),stop=lambda: b.calls.append('stop'),
                                   forward=lambda s: b.calls.append(('fwd',s)))
    b._stair_planning_front=lambda d:(d['front'],True)
    b._upd=lambda *a,**k: None
    b._go=lambda s: b.calls.append(('go',s))
    b.adc=types.SimpleNamespace(battery_pct=80)
    b.detector=types.SimpleNamespace(detect=lambda classes=None:[{'x':1}])
    b._cam_brake_t=0.0; b._roam_curve=lambda d,f: None   # steering early is tested in test_roam_steer_early
    for m in ('_roam','_slow','_camera_front_cm','_front_with_camera'): setattr(b,m,types.MethodType(getattr(RoverBrain,m),b))
    arm_ik.obstacle_cm=lambda dets,cam=None: cam_cm
    return b
# sonar/ToF clear (100 cm) but the camera sees a table 15 cm ahead -> brake and avoid
b=brain(15.0); b._roam({'front':100.0},0)
assert 'brake' in b.calls and ('go','AVOID') in b.calls, b.calls
# camera sees it at 30 cm -> slow down
b=brain(30.0); b._roam({'front':100.0},0); assert ('go','SLOW') in b.calls, b.calls
# camera sees nothing -> cruise on sonar
b=brain(None); b._roam({'front':100.0},0); assert ('fwd',config.SPEED_ROAM) in b.calls, b.calls
# setting off with something at 30 cm -> turn away first, not creep
b=brain(None); b._roam_fresh=True; b._roam({'front':30.0},0); assert ('go','AVOID') in b.calls, b.calls
# the same mid-roam -> slow, as before
b=brain(None); b._roam({'front':30.0},0); assert ('go','SLOW') in b.calls, b.calls
# SLOW also brakes for the camera
b=brain(10.0); b._state='SLOW'; b._slow({'front':100.0},0); assert 'brake' in b.calls, b.calls
print('CAMERA_BRAKE_OK')
'''

def test_camera_brake_and_turn_away_at_roam_start():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert 'CAMERA_BRAKE_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr[-3000:]}'
