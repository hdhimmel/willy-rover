import os,sys,json,queue,threading,types,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import remote_cmd
from remote_cmd import RemoteCommandServer

# remote_cmd.py (2026-10-01): Home Assistant -> Willie. Pinned: no token, no entry; only the fixed
# intents; stop takes the immediate stop_requested path, never the queue; everything else is
# queued exactly like a spoken command and the caller gets the reply brain.py speaks.

def server(token='s3cret'):
    srv=RemoteCommandServer.__new__(RemoteCommandServer)
    said=[]
    srv.voice=types.SimpleNamespace(pending_commands=queue.Queue(),stop_requested=threading.Event(),
                                    speak=lambda t,**k:said.append(t))
    srv._token=token; srv.said=said
    return srv

def body(intent): return json.dumps({'intent':intent}).encode()

def test_rejects_missing_or_wrong_token():
    s=server()
    assert s.handle(None,body('status'))[0]==401
    assert s.handle('Bearer wrong',body('status'))[0]==401
    assert s.voice.pending_commands.empty()

def test_no_token_configured_rejects_everything():
    s=server(token=None)
    assert s.handle('Bearer ',body('status'))[0]==401
    assert s.handle('Bearer None',body('status'))[0]==401

def test_unknown_intent_and_bad_body_rejected():
    s=server()
    assert s.handle('Bearer s3cret',body('forward'))[0]==400   # motion is not on the list
    assert s.handle('Bearer s3cret',b'not json')[0]==400
    assert s.voice.pending_commands.empty()

def test_stop_is_immediate_not_queued():
    s=server()
    status,resp=s.handle('Bearer s3cret',body('stop'))
    assert status==200 and s.voice.stop_requested.is_set()
    assert s.voice.pending_commands.empty()

def test_query_returns_the_reply_brain_gives():
    s=server()
    def brain():  # stands in for brain._say() answering the queued command
        cmd=s.voice.pending_commands.get(timeout=2)
        assert cmd['source']=='remote' and cmd['intent']=='status' and 'ts' in cmd
        cmd['on_reply']("I can't move. My self-test is failing: encoders not reporting.")
    t=threading.Thread(target=brain); t.start()
    status,resp=s.handle('Bearer s3cret',body('status')); t.join()
    assert status==200 and 'encoders not reporting' in resp['reply']

def test_unanswered_command_times_out_honestly(monkeypatch):
    monkeypatch.setattr(remote_cmd.config,'REMOTE_CMD_REPLY_TIMEOUT_S',0.05)
    s=server()
    status,resp=s.handle('Bearer s3cret',body('come_here'))
    assert status==200 and 'busy' in resp['reply']

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT='''
import queue,types
from brain import RoverBrain
said=[]; replies=[]
ns=types.SimpleNamespace(voice=types.SimpleNamespace(available=True,speak=lambda t,**k:said.append(t)))
ns._say=types.MethodType(RoverBrain._say,ns)
ns._reply_to=replies.append
ns._say("hello")
ns._say("again")
assert said==["hello","again"], said
assert replies==["hello"], replies   # one reply per command, never a later unrelated line
ns.voice.available=False; ns._reply_to=replies.append
ns._say("voice off")
assert replies[-1]=="voice off"      # HA still gets an answer with voice disabled
print("SAY_OK")
'''

def test_brain_say_hands_reply_to_remote_caller_once():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'SAY_OK' in r.stdout, r.stdout+r.stderr
