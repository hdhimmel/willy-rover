import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-14: no stall check while a pick-up/fetch is lining up (its short slow pulses read as a
# stall and cut every line-up off in 1-2 s). Outside the line-up a stall is still caught.
# Subprocess under WILLY_SIMULATE=1, as tests/test_brain_wave.py.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types,config
from brain import RoverBrain
config.STALL_IGNORE_WHEELS=()
def ns(state):
    n=types.SimpleNamespace(_stall_since={'lf':0.0})
    n.retrieval=types.SimpleNamespace(state=state)
    n.motors=types.SimpleNamespace(commanded={'lf':True})
    n.encoders=types.SimpleNamespace(stalled=lambda w,c: True)
    return n
for st in ('LOCALIZE','APPROACH'): assert RoverBrain._check_stall(ns(st))==[], st
for st in ('IDLE','GRASP'): assert RoverBrain._check_stall(ns(st))==['lf'], st
print('STALL_LINEUP_OK')
'''

def test_no_stall_check_during_lineup_only():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=30)
    assert 'STALL_LINEUP_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}'
