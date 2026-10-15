import os,sys,threading,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import types
import config,voice

# 2026-10-15: the local model took 30-39 s on some requests and he was deaf the whole time.
# Past VOICE_LOCAL_AI_MAX_S he gives up on it and the caller asks the cloud.


def _pipeline(delay,result='R'):
    p=object.__new__(voice.VoicePipeline)
    gate=threading.Event()
    def ask_sync(prompt,schema=None):
        gate.wait(delay); return result
    p._local_ai=types.SimpleNamespace(ask_sync=ask_sync)
    return p,gate


def test_a_quick_answer_is_used(monkeypatch):
    monkeypatch.setattr(config,'VOICE_LOCAL_AI_MAX_S',1.0)
    p,_=_pipeline(0.0)
    assert p._ask_local_capped('x')=='R'


def test_a_slow_answer_is_abandoned_and_the_next_skips_local(monkeypatch):
    monkeypatch.setattr(config,'VOICE_LOCAL_AI_MAX_S',0.2)
    p,gate=_pipeline(5.0)
    t0=time.time(); assert p._ask_local_capped('x') is None; assert time.time()-t0<1.0
    t0=time.time(); assert p._ask_local_capped('y') is None; assert time.time()-t0<0.1   # still busy
    gate.set(); p._local_thread.join(1.0)
    assert p._ask_local_capped('z')=='R'                                                # free again


def test_a_failing_model_is_not_understood(monkeypatch):
    monkeypatch.setattr(config,'VOICE_LOCAL_AI_MAX_S',1.0)
    p=object.__new__(voice.VoicePipeline)
    def boom(prompt,schema=None): raise RuntimeError('down')
    p._local_ai=types.SimpleNamespace(ask_sync=boom)
    assert p._ask_local_capped('x') is None
