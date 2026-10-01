import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-01: with the startup self-test failing (base off), _tick() returned before either voice
# drain pass, so Willie heard every command and answered none. Pinned: queries and diagnostics are
# answered with the self-test reason, and anything else is refused out loud, not left queued.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import queue,time,types
from brain import RoverBrain

REASON="battery ADC not reporting; encoders not reporting"

def fb():
    said=[]; calls=[]
    ns=types.SimpleNamespace(
        _shutdown_pending=False,_roam_ask_pending=False,_state="INIT",
        _motion_enabled=False,_init_fail_reason=REASON,
        voice=types.SimpleNamespace(pending_commands=queue.Queue(),available=True,
                                    speak=lambda t,**k:said.append(t)),
        adc=types.SimpleNamespace(battery_volts=-0.001,battery_pct=0),
        retrieval=types.SimpleNamespace(start=lambda t:(calls.append(("start",t)),(True,"ok"))[1]),
        _go=lambda s:calls.append(("go",s)),
        _self_test=lambda:(calls.append(("selftest",)),(False,REASON))[1],
    )
    ns.said=said; ns.calls=calls
    for m in ("_drain_voice_commands","_drain_voice_in_selftest_fault"):
        setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
    return ns

def q(ns,intent,**args):
    ns.voice.pending_commands.put({"source":"voice","intent":intent,"args":args,
                                    "text":intent,"ts":time.time()})

# 1. "status" says what is wrong, not "battery at -0.0 volts".
f=fb(); q(f,"status"); f._drain_voice_in_selftest_fault()
assert len(f.said)==1 and REASON in f.said[0] and "volts" not in f.said[0], f.said

# 2. "diagnostics" runs the self-test and speaks the result.
f=fb(); q(f,"diagnostics"); f._drain_voice_in_selftest_fault()
assert ("selftest",) in f.calls and any(REASON in s for s in f.said), (f.calls,f.said)

# 3. A task intent is refused out loud and REMOVED, so it cannot block the queries behind it.
f=fb(); q(f,"retrieve",object="ball"); q(f,"status")
f._drain_voice_in_selftest_fault()
assert ("start","ball") not in f.calls and f.calls==[], f.calls
assert "can't do that" in f.said[-1] and REASON in f.said[-1], f.said
f._drain_voice_in_selftest_fault()
assert "can't move" in f.said[-1], f.said
assert f.voice.pending_commands.empty()

# 4. "battery" with a dead ADC says so instead of reading out a nonsense voltage.
f=fb(); q(f,"battery"); f._drain_voice_in_selftest_fault()
assert f.said==["I can't read my battery right now."], f.said

print("SELFTEST_VOICE_OK")
'''

def test_willie_explains_a_failing_self_test_by_voice():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'SELFTEST_VOICE_OK' in r.stdout, r.stdout+r.stderr
