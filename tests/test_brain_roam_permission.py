import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Owner decision 2026-09-09: autonomous ROAM must ASK before it starts, rather than self-enabling
# on the idle timeout / charged-on-dock triggers. ENABLE_AUTONOMOUS_ROAM=True now means "allowed to
# ask"; the session grant (_roam_permission, false at every boot) is what actually opens the gate.
#
# Shape of the ask, per the owner:
#   - permission lasts the rest of the session once given, and is revoked by voice stop or reboot
#   - a spoken "no" and nobody answering land in the SAME place: cooldown, then ask again. That is
#     why there is only an ALLOW button on the panel and no DECLINE button -- declining and
#     ignoring are the same outcome, so a second button would be a distinction without a difference
#   - either channel answers: a screen tap or a spoken yes
#
# ROAM_PERMISSION_REQUIRED=False restores the pre-2026-09-09 behaviour exactly (roams unattended).

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import queue,time,types,config
from brain import RoverBrain

config.ROAM_PERMISSION_REQUIRED=True
config.ROAM_ASK_TIMEOUT_S=30.0
config.ROAM_ASK_COOLDOWN_S=600.0

def fb(tapped=False,shutdown_pending=False,state="IDLE"):
    said=[]; offers=[]; calls=[]
    ns=types.SimpleNamespace(
        _roam_permission=False,
        _roam_ask_pending=False,
        _roam_ask_deadline=0.0,
        _roam_ask_next=0.0,
        _shutdown_pending=shutdown_pending,
        _state=state,
        voice=types.SimpleNamespace(pending_commands=queue.Queue(),available=True,
                                    speak=lambda t,**k:said.append(t)),
        display=types.SimpleNamespace(offer_roam=lambda v:offers.append(v),
                                      roam_tapped=lambda:tapped),
        adc=types.SimpleNamespace(battery_volts=11.5,battery_pct=82),
        retrieval=types.SimpleNamespace(start=lambda t:(calls.append(("start",t)),(True,"ok"))[1]),
        mapping=types.SimpleNamespace(start=lambda:(True,"ok"),stop=lambda:(True,"ok")),
        _go=lambda s:calls.append(("go",s)),
        _self_test=lambda:(calls.append(("selftest",)),(True,""))[1],
    )
    ns.said=said; ns.offers=offers; ns.calls=calls
    for m in ("_roam_allowed","_begin_roam_ask","_end_roam_ask","_service_roam_ask",
              "_revoke_roam_permission","_drain_voice_commands"):
        setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
    return ns

def q(ns,intent,text=None,**args):
    ns.voice.pending_commands.put({"source":"voice","intent":intent,"args":args,
                                    "text":text if text is not None else intent,"ts":time.time()})

# 1. The flag off restores the old behaviour: roams with no ask at all.
config.ROAM_PERMISSION_REQUIRED=False
f=fb()
assert f._roam_allowed() is True
assert f.said==[] and f.offers==[], "must not ask when permission is not required"
config.ROAM_PERMISSION_REQUIRED=True

# 2. First trigger does NOT roam -- it opens the ask, on both channels.
f=fb()
assert f._roam_allowed() is False, "must not roam before permission is given"
assert f._roam_ask_pending is True
assert any("explore" in s.lower() for s in f.said), f.said
assert f.offers==[True], f.offers

# 3. A pending ask is not re-asked every tick. The idle timeout keeps firing; he must not repeat
#    himself 20 times a second.
f=fb(); f._roam_allowed()
before=len(f.said)
assert f._roam_allowed() is False
assert len(f.said)==before, "must not re-ask while an ask is already pending"

# 4. Nobody answers -> the ask closes, the panel button is withdrawn, and a cooldown starts.
f=fb(); f._roam_allowed()
f._roam_ask_deadline=time.time()-1
f._service_roam_ask()
assert f._roam_ask_pending is False
assert f.offers[-1] is False, "panel button must be withdrawn when the ask closes"
assert f._roam_ask_next>time.time()+500, "timeout must start the re-ask cooldown"
assert f._roam_permission is False

# 5. During the cooldown he stays put and stays quiet.
said_before=len(f.said)
assert f._roam_allowed() is False
assert len(f.said)==said_before, "must stay quiet during the cooldown"
assert f._roam_ask_pending is False

# 6. Once the cooldown elapses he asks again -- refusal is not permanent.
f._roam_ask_next=time.time()-1
assert f._roam_allowed() is False
assert f._roam_ask_pending is True, "must ask again after the cooldown elapses"

# 7. Screen tap grants it, and it holds for the rest of the session.
f=fb(tapped=True); f._roam_allowed()
f._service_roam_ask()
assert f._roam_permission is True
assert f._roam_ask_pending is False
assert f.offers[-1] is False
assert f._roam_allowed() is True, "permission must persist for the session"

# 8. A spoken yes grants it the same way.
f=fb(); f._roam_allowed()
q(f,"unknown",text="yes go ahead")
f._drain_voice_commands()
assert f._roam_permission is True, f.said
assert f._roam_ask_pending is False

# 9. A spoken no is acknowledged, and lands in the cooldown -- same place as silence.
f=fb(); f._roam_allowed()
q(f,"unknown",text="no not right now")
f._drain_voice_commands()
assert f._roam_permission is False
assert f._roam_ask_pending is False
assert f._roam_ask_next>time.time()+500
assert any("later" in s.lower() for s in f.said), f.said

# 10. The every-tick speech-only pass must not eat the reply while the ask is outstanding --
#     exactly the hazard the shutdown confirmation already guards against.
f=fb(); f._roam_allowed()
q(f,"battery")
f._drain_voice_commands(speech_only=True)
assert f.voice.pending_commands.qsize()==1, "the reply must stay queued for the ask to claim"
assert not any("Battery is at" in s for s in f.said), f.said

# 11. An outstanding shutdown confirmation wins -- do not stack two yes/no questions on the owner.
f=fb(shutdown_pending=True)
assert f._roam_allowed() is False
assert f._roam_ask_pending is False, "must not ask to roam while a shutdown confirm is pending"
assert f.said==[]

# 12. Voice stop revokes the session grant, so "stop" ends autonomy rather than just this wander.
f=fb(tapped=True); f._roam_allowed(); f._service_roam_ask()
assert f._roam_permission is True
f._revoke_roam_permission()
assert f._roam_permission is False
assert f._roam_allowed() is False, "revoked permission must require asking again"

# 13. Revoking mid-ask withdraws the panel button too -- it must not sit there live after a stop.
f=fb(); f._roam_allowed()
f._revoke_roam_permission()
assert f._roam_ask_pending is False
assert f.offers[-1] is False

print("ROAM_PERMISSION_OK")
'''

def test_autonomous_roam_asks_permission_before_enabling():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    result=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,
                          cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'ROAM_PERMISSION_OK' in result.stdout, (
        f'roam-permission test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
