import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Voice commands carry a 'ts' set by voice.py::_act_on_intent, but nothing ever read it --
# _drain_voice_commands() executed whatever it found regardless of age. Say "turn right" while a
# 30s retrieval is running and the queue holds it until the task finishes, then drives the rover
# half a minute after you asked, in a situation you are no longer watching for. Reported by Jules
# 2026-08-25; confirmed by grep that 'ts' was written and never read anywhere in the codebase.
#
# Two intents are deliberately exempt. confirm_receipt answers retrieval_task.py's AWAIT_CONFIRM
# state, which can legitimately wait longer than the expiry window -- expiring it would stall the
# task rather than protect anyone. The shutdown confirmation is handled before the expiry check
# for the same reason, and has its own separate timeout in _tick().
#
# Subprocess under WILLY_SIMULATE=1 with a SimpleNamespace stand-in for self, same reasoning as
# tests/test_brain_battery.py: importing brain.py in-process only works on the real Pi.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import queue,time,types,config
from brain import RoverBrain

def fb():
    """A stand-in self carrying only what _drain_voice_commands() touches."""
    calls=[]
    ns=types.SimpleNamespace(
        _shutdown_pending=False,
        voice=types.SimpleNamespace(pending_commands=queue.Queue(),available=True,
                                    speak=lambda *a,**k:None),
        retrieval=types.SimpleNamespace(start=lambda t:(calls.append(("start",t)),(True,"ok"))[1]),
        mapping=types.SimpleNamespace(start=lambda:(True,"ok"),stop=lambda:(True,"ok")),
        _go=lambda s:calls.append(("go",s)),
    )
    ns.calls=calls
    ns._drain_voice_commands=types.MethodType(RoverBrain._drain_voice_commands,ns)
    return ns

def q(ns,intent,age_s,**args):
    ns.voice.pending_commands.put({"source":"voice","intent":intent,"args":args,
                                    "text":intent,"ts":time.time()-age_s})

# 1. A fresh command is dispatched as before.
f=fb(); q(f,"retrieve",0.0,object="ball"); f._drain_voice_commands()
assert ("start","ball") in f.calls, f.calls

# 2. A command older than the window is dropped, not executed.
f=fb(); q(f,"retrieve",config.VOICE_COMMAND_MAX_AGE_S+5.0,object="ball")
f._drain_voice_commands()
assert f.calls==[], f.calls

# 3. Right at the boundary it still runs -- expiry is strictly greater than the window, so a
#    command is never dropped for being exactly as old as the limit allows.
f=fb(); q(f,"retrieve",config.VOICE_COMMAND_MAX_AGE_S-0.5,object="ball")
f._drain_voice_commands()
assert ("start","ball") in f.calls, f.calls

# 4. confirm_receipt is exempt: retrieval AWAIT_CONFIRM may wait longer than the window, and
#    expiring it stalls the task instead of protecting anyone.
f=fb(); q(f,"confirm_receipt",config.VOICE_COMMAND_MAX_AGE_S+60.0)
f._drain_voice_commands()   # must not raise, must not be swallowed as an expired command

# 5. A command with no timestamp at all is treated as fresh rather than dropped -- absence of a
#    ts means an unknown source, not an old command, and silently eating it would be worse.
f=fb()
f.voice.pending_commands.put({"source":"test","intent":"retrieve","args":{"object":"ball"},
                               "text":"retrieve"})
f._drain_voice_commands()
assert ("start","ball") in f.calls, f.calls

print("VOICE_EXPIRY_OK")
'''

def test_stale_voice_commands_are_dropped_rather_than_executed_late():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    result=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,
                          cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'VOICE_EXPIRY_OK' in result.stdout, (
        f'voice command expiry test failed\n{result.stdout}\n{result.stderr}')
