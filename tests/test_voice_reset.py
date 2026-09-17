import os,sys,subprocess,queue
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-300-003, voice half. Owner decision 2026-09-17: an operator reset is EITHER a screen tap
# OR the 'reset' voice intent. A latched fault returns early from _tick() before the normal
# voice drain runs, so brain._voice_reset_requested() pulls the intent out of the queue itself.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types, queue
from brain import RoverBrain

class FakeVoice:
    def __init__(self,items=()):
        self.pending_commands=queue.Queue()
        for i in items: self.pending_commands.put(i)

class FakeDisplay:
    def __init__(self): self.updates=[]
    def reset_tapped(self): return False
    def update_state(self,**kw): self.updates.append(kw)

class FakeSafety:
    def __init__(self): self.calls=[]
    def emergency_stop(self,reason): self.calls.append(reason)

def fb(voice_items,has_voice=True):
    ns=types.SimpleNamespace(_state="SENSOR_FAULT",_motor_rail_lost=False,_bat_xcheck_flagged=False)
    ns.display=FakeDisplay(); ns.safety=FakeSafety()
    if has_voice: ns.voice=FakeVoice(voice_items)
    ns._go=lambda s: setattr(ns,"_state",s)
    ns._upd=types.MethodType(RoverBrain._upd,ns)
    ns._voice_reset_requested=types.MethodType(RoverBrain._voice_reset_requested,ns)
    ns._await_reset_or_resume=types.MethodType(RoverBrain._await_reset_or_resume,ns)
    return ns

# 1. A 'reset' intent clears a latched fault, exactly like a screen tap.
f=fb([{"intent":"reset"}])
assert f._await_reset_or_resume("sensor fault",{"front":999},0.0,"CLEARED") is True
assert f._state=="IDLE"
assert f.safety.calls==[]

# 2. It is found anywhere in the queue, not just at the head -- a fault can sit latched while
#    other commands pile up behind it.
f=fb([{"intent":"status"},{"intent":"forward"},{"intent":"reset"}])
assert f._voice_reset_requested() is True
# and the other commands are left untouched, in order
assert [c["intent"] for c in list(f.voice.pending_commands.queue)]==["status","forward"]

# 3. Consumed exactly once -- the same contract as display.reset_tapped().
f=fb([{"intent":"reset"}])
assert f._voice_reset_requested() is True
assert f._voice_reset_requested() is False

# 4. No reset queued -> the fault stays latched and keeps braking.
f=fb([{"intent":"status"}])
assert f._await_reset_or_resume("sensor fault",{"front":999},0.0,"CLEARED") is False
assert f._state=="SENSOR_FAULT"
assert f.safety.calls==["sensor fault cleared, awaiting operator reset"]

# 5. A brain with no voice subsystem at all must not raise -- the screen tap still works.
f=fb([],has_voice=False)
assert f._voice_reset_requested() is False

print("VOICE_RESET_OK")
'''

def test_voice_reset_clears_a_latched_fault():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                          capture_output=True,text=True,timeout=60)
    assert 'VOICE_RESET_OK' in result.stdout, (
        f'voice reset test failed\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}')


def test_reset_is_a_recognised_local_intent():
    # The fast-path pattern must actually match, and must not swallow 'stop' or its negation.
    sys.path.insert(0,_REPO_ROOT)
    os.environ['WILLY_SIMULATE']='1'
    import voice
    def intent_for(text):
        for pat,name,_reply in voice._FAST_PATH_PATTERNS:
            if pat.fullmatch(text.strip().lower()): return name
        return None
    assert intent_for('reset')=='reset'
    assert intent_for('clear the fault')=='reset'
    assert intent_for('all clear')=='reset'
    assert intent_for('stop')=='stop'
