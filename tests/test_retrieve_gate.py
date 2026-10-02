import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-1500-005 / FR-1700 (2026-10-02). 2026-10-01 a bare "Hey, Willie" was classified as
# 'retrieve'. Pinned: the wake phrase alone is never interpreted, and with
# ENABLE_RETRIEVAL_TASK off a 'retrieve' intent is answered and refused, never started.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_bare_wake_phrase_is_recognised():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    code=('from voice import _BARE_ADDRESS as B\n'
          'for t in ("Hey, Willie","Hey Willie.","willie","OK Willie!"," Hey Willie? "):\n'
          '    assert B.fullmatch(t), t\n'
          'for t in ("Hey Willie, stop","Willie come here","what is Willie doing"):\n'
          '    assert not B.fullmatch(t), t\n'
          'print("BARE_OK")\n')
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'BARE_OK' in r.stdout, r.stdout+r.stderr

_SCRIPT='''
import queue,time,types,config
from brain import RoverBrain
assert config.ENABLE_RETRIEVAL_TASK is False
said=[]; started=[]
ns=types.SimpleNamespace(_shutdown_pending=False,_roam_ask_pending=False,_state="IDLE",
    voice=types.SimpleNamespace(pending_commands=queue.Queue(),available=True,speak=lambda t,**k:said.append(t)),
    retrieval=types.SimpleNamespace(start=lambda t:(started.append(t),(True,"ok"))[1]),
    _go=lambda s:None)
for m in ("_drain_voice_commands","_say"): setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
ns.voice.pending_commands.put({"source":"voice","intent":"retrieve","args":{"object":"ball"},"text":"hey willie","ts":time.time()})
ns._drain_voice_commands()
assert started==[], started
assert said and "can't fetch" in said[0], said
print("GATE_OK")
'''

def test_retrieve_is_refused_while_the_task_is_disabled():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'GATE_OK' in r.stdout, r.stdout+r.stderr
