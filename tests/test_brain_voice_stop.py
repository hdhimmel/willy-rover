import os,sys,subprocess

# FRD gap audit, 2026-10-01 (FR-900-004 / FR-1000-004 / Directive 1). A voice "stop" braked and
# aborted tasks but left _state alone, so the dispatch at the bottom of the same tick ran _roam()
# and drove again. The existing tests only checked that stop_requested got SET; nothing drove it
# through _tick(). This does, in every motion state that commands the wheels from dispatch.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import time,brain
b=brain.RoverBrain(); b.start(); time.sleep(1.0)
assert b._motion_enabled, b._init_fail_reason
for st in ("ROAM","SLOW","AVOID"):
    b._go(st); b._tick(); time.sleep(0.05)
    b.voice.stop_requested.set()
    b._tick()
    assert b._state=="IDLE", f"voice stop left the rover in {b._state} (was {st})"
    t=b.motors._target
    assert all(v==0.0 for v in t.values()), f"still commanded after stop from {st}: {t}"
# A latched fault must NOT be cleared by a voice stop.
b._go("TILT_FAULT"); b.voice.stop_requested.set(); b._tick()
assert b._state!="IDLE", "voice stop cleared a latched fault"
b.stop()
print("VOICE_STOP_OK")
'''

def test_voice_stop_leaves_the_motion_state_in_the_same_tick():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                     capture_output=True,text=True,timeout=60)
    assert 'VOICE_STOP_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}'
