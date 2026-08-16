import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Voice-triggered forward/reverse/turn_left/turn_right were previously queued by voice.py but
# never wired to an executor in brain.py's _drain_voice_commands() -- found and fixed 2026-08-16.
# 'stop' used to be wired here too, but as of the FR-1000/FR-900 voice vocabulary pass it bypasses
# pending_commands entirely (VoicePipeline.stop_requested, checked at the top of brain.py's
# _tick() before any Directive gating) -- every other queued intent only gets drained from IDLE,
# so a spoken "stop" mid-RETRIEVE/NAVIGATE/PURSUE would otherwise never be picked up. Runs as a
# subprocess under WILLY_SIMULATE=1, same reasoning as tests/test_brain_battery.py: importing
# brain.py directly only happens to work on this Pi (Adafruit Blinka installed), and lightweight
# SimpleNamespace stand-ins avoid constructing a full RoverBrain (which pulls in the entire
# hardware/subsystem stack) just to exercise methods that only ever touch
# self.voice/self.safety/self._state/self._manual_action.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types,queue,threading,config
from brain import RoverBrain
from voice import VoicePipeline
from safety import Rejected,ApprovedMotion

class FakeSafety:
    def __init__(self,reject=None):
        self.calls=[]; self._timed_move_active=True; self._reject=reject
    def _for(self,action,duration,speed):
        self.calls.append((action,duration,speed))
        if self._reject: return Rejected(self._reject)
        return ApprovedMotion(action,min(speed,config.SPEED_MAX),min(duration,config.MAX_COMMAND_DURATION_S))
    def forward_for(self,duration,speed=None): return self._for("forward",duration,speed)
    def reverse_for(self,duration,speed=None): return self._for("reverse",duration,speed)
    def turn_left_for(self,duration,speed=None): return self._for("turn_left",duration,speed)
    def turn_right_for(self,duration,speed=None): return self._for("turn_right",duration,speed)
    def stop(self): self.calls.append(("stop",))
    @property
    def timed_move_active(self): return self._timed_move_active

class FakeQueue:
    def __init__(self,items): self._items=list(items)
    def get_nowait(self):
        if not self._items: raise Exception("empty")
        return self._items.pop(0)

class FakeVoice:
    def __init__(self,cmds,available=False):
        self.pending_commands=FakeQueue(cmds); self.available=available; self.spoken=[]
    def speak(self,text,tone=None): self.spoken.append(text)

def make_brain(cmds,reject=None,available=False):
    ns=types.SimpleNamespace()
    ns.voice=FakeVoice(cmds,available=available)
    ns.safety=FakeSafety(reject=reject)
    ns._manual_action=None; ns._state="IDLE"; ns._shutdown_pending=False
    ns._go=types.MethodType(RoverBrain._go,ns)
    ns._drain_voice_commands=types.MethodType(RoverBrain._drain_voice_commands,ns)
    return ns

# 1. Approved forward -> real safety call with the requested args, transitions to MANUAL.
b=make_brain([{"intent":"forward","args":{"speed":0.9,"duration":10.0}}])
b._drain_voice_commands()
assert b.safety.calls==[("forward",10.0,0.9)], b.safety.calls
assert b._state=="MANUAL", b._state
assert b._manual_action=="forward", b._manual_action

# 2. All four directions route to the correct SafetyController method.
for intent,expect in [("reverse","reverse"),("turn_left","turn_left"),("turn_right","turn_right")]:
    b=make_brain([{"intent":intent,"args":{}}])
    b._drain_voice_commands()
    assert b.safety.calls[0][0]==expect, (intent,b.safety.calls)
    assert b._state=="MANUAL" and b._manual_action==expect

# 3. Rejected motion (e.g. tilt/obstacle/battery) leaves state untouched and speaks the reason
#    when voice is available -- nothing bypasses SafetyController\\'s real decision.
b=make_brain([{"intent":"forward","args":{}}],reject="tilt 30.0deg exceeds limit",available=True)
b._drain_voice_commands()
assert b._state=="IDLE", b._state
assert b._manual_action is None
assert any("tilt 30.0deg exceeds limit" in s for s in b.voice.spoken), b.voice.spoken

# 4. 'stop' bypasses pending_commands entirely -- VoicePipeline._act_on_intent sets
#    stop_requested immediately instead of queuing (brain.py's _tick() is the consumer, not
#    _drain_voice_commands()). Bare SimpleNamespace stand-in, same pattern as make_brain() above.
vp=types.SimpleNamespace()
vp.pending_commands=queue.Queue(); vp.stop_requested=threading.Event(); vp.spoken=[]
vp.speak=lambda text,tone=None: vp.spoken.append(text)
vp._act_on_intent=types.MethodType(VoicePipeline._act_on_intent,vp)
vp._act_on_intent({"intent":"stop","args":{},"reply":"Stopping."},"stop")
assert vp.stop_requested.is_set()
assert vp.pending_commands.empty()
assert vp.spoken==["Stopping."], vp.spoken

# 5. _manual() stays in MANUAL (and updates the display) while the timed move is still active,
#    then returns to IDLE once safety reports it finished (deadline elapsed or obstacle-aborted --
#    either way is just "no longer active" from _manual()\\'s point of view).
ns=types.SimpleNamespace()
ns._state="MANUAL"; ns._manual_action="forward"; ns.safety=FakeSafety()
upd_calls=[]
ns._upd=lambda *a,**k: upd_calls.append((a,k))
ns._manual=types.MethodType(RoverBrain._manual,ns)
ns._go=types.MethodType(RoverBrain._go,ns)
ns.safety._timed_move_active=True
ns._manual({},0.0)
assert ns._state=="MANUAL" and len(upd_calls)==1
ns.safety._timed_move_active=False
ns._manual({},0.0)
assert ns._state=="IDLE", ns._state

print("MANUAL_DRIVE_OK")
'''

def test_voice_manual_drive_under_simulation():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'MANUAL_DRIVE_OK' in result.stdout, (
        f'manual drive test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
