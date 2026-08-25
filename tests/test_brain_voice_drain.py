import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# _drain_voice_commands() was gated entirely on IDLE (plus mapping.active), so a query asked while
# the rover was driving sat in the queue until it stopped. "How's your battery?" during a ROAM
# went unanswered, which reads as the rover ignoring you. Reported by Jules 2026-08-25.
#
# The fix splits the gate rather than removing it: queries that only READ cached state are drained
# every tick, while anything that moves the rover or starts a task stays IDLE-gated exactly as
# before.
#
# Two of the intents Jules listed as speech-only are deliberately NOT included, because "speaks
# rather than moves" is the wrong test -- what matters is whether it blocks the tick thread:
#   diagnostics     runs a real I2C scan synchronously, ~0.5s+. brain.py's own comment says that
#                   cost is "accepted: this only ever runs from IDLE". Draining it while driving
#                   stalls the tick -- and therefore obstacle checks -- for half a second at
#                   speed, which is the hazard _grasp() and _wave() were both rewritten to remove.
#   what_do_you_see runs a detector inference synchronously. Cheap on the Hailo, several hundred
#                   ms on the CPU-YOLO fallback, and the fallback is exactly when the rover is
#                   already struggling.
# Both stay IDLE-gated until they are made non-blocking.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import queue,time,types,config
from brain import RoverBrain

def fb(shutdown_pending=False):
    said=[]; calls=[]
    ns=types.SimpleNamespace(
        _shutdown_pending=shutdown_pending,
        _state="ROAM",
        voice=types.SimpleNamespace(pending_commands=queue.Queue(),available=True,
                                    speak=lambda t,**k:said.append(t)),
        adc=types.SimpleNamespace(battery_volts=11.5,battery_pct=82),
        retrieval=types.SimpleNamespace(start=lambda t:(calls.append(("start",t)),(True,"ok"))[1]),
        mapping=types.SimpleNamespace(start=lambda:(True,"ok"),stop=lambda:(True,"ok")),
        _go=lambda s:calls.append(("go",s)),
        _self_test=lambda:(calls.append(("selftest",)),(True,""))[1],
    )
    ns.said=said; ns.calls=calls
    ns._drain_voice_commands=types.MethodType(RoverBrain._drain_voice_commands,ns)
    return ns

def q(ns,intent,**args):
    ns.voice.pending_commands.put({"source":"voice","intent":intent,"args":args,
                                    "text":intent,"ts":time.time()})

# 1. A query is answered while driving -- the whole point of the change.
f=fb(); q(f,"battery"); f._drain_voice_commands(speech_only=True)
assert any("Battery is at" in s for s in f.said), f.said

# 2. status likewise, and it reports the live state rather than pretending to be idle.
f=fb(); q(f,"status"); f._drain_voice_commands(speech_only=True)
assert any("roam" in s.lower() for s in f.said), f.said

# 3. A motion/task intent is NOT drained in speech-only mode, and is still queued afterwards so
#    the IDLE-gated pass can pick it up normally. Draining it here would start a task mid-drive.
f=fb(); q(f,"retrieve",object="ball"); f._drain_voice_commands(speech_only=True)
assert f.calls==[], f.calls
assert f.voice.pending_commands.qsize()==1, "motion intent must stay queued, not be discarded"

# 4. diagnostics stays IDLE-gated: it blocks the tick thread on a real I2C scan.
f=fb(); q(f,"diagnostics"); f._drain_voice_commands(speech_only=True)
assert ("selftest",) not in f.calls, f.calls
assert f.voice.pending_commands.qsize()==1

# 5. While a shutdown confirmation is pending, the speech-only pass must not touch the queue at
#    all -- the next queued command is that confirmation'\''s yes/no answer, and intercepting it
#    here would silently consume the user'\''s reply.
f=fb(shutdown_pending=True); q(f,"battery")
f._drain_voice_commands(speech_only=True)
assert f.said==[], f.said
assert f.voice.pending_commands.qsize()==1

# 6. The normal (non-speech-only) pass is unchanged: it still drains whatever is at the head.
f=fb(); q(f,"retrieve",object="ball"); f._drain_voice_commands()
assert ("start","ball") in f.calls, f.calls

print("VOICE_DRAIN_OK")
'''

def test_queries_are_answered_while_driving_but_task_intents_stay_idle_gated():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    result=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,
                          cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'VOICE_DRAIN_OK' in result.stdout, (
        f'voice drain test failed\n{result.stdout}\n{result.stderr}')
