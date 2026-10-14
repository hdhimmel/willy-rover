import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config
from safety import approve_crab,Rejected

# 2026-10-14 (owner): blocked on one side, after trying twice, turn the wheels hard toward the open
# side and side-step instead of going back and forth.

def test_crab_is_gated_and_clamped():
    assert approve_crab(40).speed==40 and approve_crab(-90).speed==-config.SIDESTEP_MAX_DEG
    assert isinstance(approve_crab(40,motion_enabled=False),Rejected)

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT='''
import types,time,config
from brain import RoverBrain
def brain(repeats):
    b=types.SimpleNamespace(_avoid_repeats=repeats,_avoid_phase=None,calls=[])
    b.safety=types.SimpleNamespace(crab=lambda deg: (b.calls.append(('crab',deg)),deg)[1],
                                   request=lambda a,s,t: (b.calls.append((a,t)),types.SimpleNamespace(action=a))[1])
    b.steering=types.SimpleNamespace(center_all=lambda: b.calls.append('centre'))
    for m in ('_start_sidestep','_sidestep_move'): setattr(b,m,types.MethodType(getattr(RoverBrain,m),b))
    return b
LEFT_BLOCKED={'left':20,'right':120}
# only twice so far: no side-step yet
b=brain(2); assert not b._start_sidestep(LEFT_BLOCKED,80) and b.calls==[]
# third time, left blocked, room in front: wheels right, forward
b=brain(3); assert b._start_sidestep(LEFT_BLOCKED,80)
assert b.calls==[('crab',config.SIDESTEP_DEG)] and b._sidestep[0]=='forward' and b._avoid_phase=='sidestep_settle'
b._sidestep=('forward',0.0); b._sidestep_move({},0)
assert b.calls[-1]==('forward',config.SIDESTEP_TIME_S) and b._avoid_phase=='sidestep_move'
# right blocked, front blocked: reverse with wheels RIGHT -> still moves left (away from the block)
b=brain(3); assert b._start_sidestep({'left':120,'right':20},10)
assert b.calls==[('crab',config.SIDESTEP_DEG)] and b._sidestep[0]=='reverse'
# both sides blocked or both open: no side-step
assert not brain(3)._start_sidestep({'left':20,'right':20},80)
assert not brain(3)._start_sidestep({'left':120,'right':120},80)
print('SIDESTEP_OK')
'''

def test_sidestep_after_two_tries_toward_the_open_side():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert 'SIDESTEP_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr[-3000:]}'
