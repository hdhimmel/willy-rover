import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-2000-011/012/013 (built 2026-10-02). Pinned: DKIM must pass on OUR receiver's header and
# align with From; forged/other-server headers don't count; stale commands are refused; only the
# owner commands; allowlist changes only via this path; one command per poll; queued commands
# carry source='email' and never answer a pending yes/no ask.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT=r'''
import email,time,types,queue,email.utils
import config,email_client
from email_client import command_text,dkim_verified,message_age_s,EmailClient

def mk(frm,subject,auth=(),date=None):
    m=email.message.EmailMessage()
    for a in auth: m["Authentication-Results"]=a
    m["From"]=frm; m["Subject"]=subject
    m["Date"]=email.utils.formatdate(date if date is not None else time.time())
    m.set_content("body")
    return m
G="mx.google.com; dkim=pass header.i=@gmail.com header.s=20230601 header.b=abc; spf=pass; dmarc=pass header.from=gmail.com"

# subject parsing
assert command_text("Willie: go to the kitchen")=="go to the kitchen"
assert command_text("re: willie, status")=="status"
assert command_text("Hello Willie")is None and command_text("Willie:   ") is None

# DKIM
o=config.OWNER_EMAIL
assert dkim_verified(mk(o,"x",[G]),o)
assert not dkim_verified(mk(o,"x",[]),o)                                            # no header
assert not dkim_verified(mk(o,"x",[G.replace("dkim=pass","dkim=fail")]),o)          # failed
assert not dkim_verified(mk(o,"x",["evil.example; dkim=pass header.d=gmail.com"]),o) # other server
assert not dkim_verified(mk(o,"x",[G.replace("@gmail.com","@evil.com")]),o)         # not aligned
# only the TOPMOST header from our receiver counts: a forged pass lower down is ignored
forged=mk(o,"x",[G.replace("dkim=pass","dkim=fail"),G])
assert not dkim_verified(forged,o)

# age
assert message_age_s(mk(o,"x",[G],date=time.time()-900))>=899

# the command path
c=EmailClient.__new__(EmailClient)
c._inbox_summaries=queue.Queue(); sent=[]; handled=[]
c.send_owner_reply=lambda s,b: sent.append((s,b))
c._command_handler=lambda text,reply: (handled.append(text),reply("done"))
store=set()
c._inbound_allowlist=lambda: set(store)
c._allowlist_path=lambda: "NUL" if os.name=="nt" else "/dev/null"
def add(e,owner_confirmed=False): store.add(e.lower()); return True,"added"
def rm(e,owner_confirmed=False): store.discard(e.lower()); return True,"removed"
c.add_allowed_sender=add; c.remove_allowed_sender=rm

c._handle_command(mk(o,"Willie: go to the kitchen",[G]),o,"Willie: go to the kitchen","go to the kitchen")
assert handled==["go to the kitchen"] and sent[-1][1].startswith("done")
c._handle_command(mk(o,"s",[]),o,"s","go forward")                                  # unverified
assert handled==["go to the kitchen"] and "unverified" in c._inbox_summaries.get_nowait()["subject"]
c._handle_command(mk(o,"s",[G],date=time.time()-3600),o,"s","go forward")           # stale
assert handled==["go to the kitchen"] and "Not done" in sent[-1][1]
c._handle_command(mk("bob@gmail.com","s",[G]),"bob@gmail.com","s","go forward")     # not owner
assert handled==["go to the kitchen"]
c._handle_command(mk(o,"s",[G]),o,"s","allow sender Carol@Example.com")             # FR-2000-011
assert "carol@example.com" in store and "added" in sent[-1][1]
c._handle_command(mk(o,"s",[G]),o,"s","remove sender carol@example.com")
assert "carol@example.com" not in store
print("EMAIL_OK")
'''

def test_email_command_channel():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'EMAIL_OK' in r.stdout, r.stdout+r.stderr

_BRAIN=r'''
import queue,types,time
import config
from brain import RoverBrain
said=[]; replies=[]
ns=types.SimpleNamespace(voice=types.SimpleNamespace(available=True,speak=lambda t,**k:said.append(t),
        pending_commands=queue.Queue(),stop_requested=__import__("threading").Event(),
        interpret_text=lambda t: {"intent":"go_to","args":{"room":"kitchen"},"reply":""} if "kitchen" in t
                       else ({"intent":"stop"} if t=="stop" else None)))
RoverBrain._email_command(ns,"go to the kitchen",replies.append)
cmd=ns.voice.pending_commands.get_nowait()
assert cmd["source"]=="email" and cmd["intent"]=="go_to" and callable(cmd["on_reply"])
assert any("emailed: go to the kitchen" in s for s in said), said
RoverBrain._email_command(ns,"gibberish",replies.append)
assert "didn't understand" in replies[-1] and ns.voice.pending_commands.empty()
RoverBrain._email_command(ns,"stop",replies.append)
assert ns.voice.stop_requested.is_set() and ns.voice.pending_commands.empty()
import brain; assert "email" in brain._NON_SPOKEN_SOURCES
print("BRAIN_EMAIL_OK")
'''

def test_brain_queues_email_commands_like_speech():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_BRAIN],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'BRAIN_EMAIL_OK' in r.stdout, r.stdout+r.stderr
