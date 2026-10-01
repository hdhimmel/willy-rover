import os,sys,subprocess

# 2026-10-01: brain.py fed every sonar reading below 999 cm into the world model as an
# obstacle -- the 999 timeout sentinel the Pico cutover retired. The Pico B path reports
# "no echo, nothing in range" as config.SONAR_MAX_CM (400, a CLEAR path) and "no fresh
# frame" as 0.0 (unknown -> STOP). Both are below 999, so an open room painted a phantom
# wall 4 m out on every tick, and a stale link painted one on top of the rover. Only a
# reading strictly between 0 and SONAR_MAX_CM is an echo off something real.
# Subprocess for the same reason as test_brain_stall.py: brain.py needs the sim stack.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import config
from brain import _sonar_returns
M=config.SONAR_MAX_CM
assert _sonar_returns({'front':0.0,'left':M,'right':M}) == {}, 'stale and clear are not obstacles'
assert _sonar_returns({'front':120.0,'left':M,'right':0.0}) == {'front':120.0}
assert _sonar_returns({'front':M-0.1,'left':2.0,'right':M+1}) == {'front':M-0.1,'left':2.0}
print("SONAR_WM_OK")
'''

def test_only_real_echoes_become_world_model_obstacles():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=60)
    assert 'SONAR_WM_OK' in result.stdout, (
        f'--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}')
