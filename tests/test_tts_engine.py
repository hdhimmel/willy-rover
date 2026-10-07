import os,sys,types,wave,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest

# 2026-10-07 "faster responses": Piper used to start a new process (and load the voice model)
# for every reply -- 2.6-5.1 s of the measured latency. PiperEngine loads once, caches short
# replies, and falls back to the old subprocess so speech is never lost.

def _tmp():
    f=tempfile.NamedTemporaryFile(suffix='.wav',delete=False); f.close(); return f.name

def _fake_piper(monkeypatch,new_api=True,load_fails=False):
    calls={'load':0,'synth':0}
    class Voice:
        @classmethod
        def load(cls,path):
            calls['load']+=1
            if load_fails: raise FileNotFoundError(path)
            return cls()
        def _write(self,w):
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b'\x00\x01'*100)
            calls['synth']+=1
        def synthesize_wav(self,text,w,syn_config=None): calls['scale']=syn_config.length_scale; self._write(w)
        def synthesize(self,text,w,length_scale=1.0): calls['scale']=length_scale; self._write(w)
    mod=types.ModuleType('piper'); mod.PiperVoice=Voice
    if new_api:
        mod.SynthesisConfig=lambda length_scale=1.0: types.SimpleNamespace(length_scale=length_scale)
    monkeypatch.setitem(sys.modules,'piper',mod)
    return calls

@pytest.mark.parametrize('new_api',[True,False])
def test_voice_loads_once_and_synthesises_in_process(monkeypatch,new_api):
    from voice import PiperEngine
    calls=_fake_piper(monkeypatch,new_api=new_api)
    sub=[]; e=PiperEngine('m.onnx',lambda t,p,s: sub.append(t))
    for text in ('a long sentence that is far too long to be worth caching at all, really','another long one that will not be cached either, honestly'):
        p=_tmp(); e.synthesize(text,p,0.92); os.remove(p)
    assert calls['load']==1 and calls['synth']==2 and sub==[] and e.last_path=='inproc'
    assert calls['scale']==0.92

def test_short_replies_are_cached(monkeypatch):
    from voice import PiperEngine
    calls=_fake_piper(monkeypatch)
    e=PiperEngine('m.onnx',lambda t,p,s: None)
    p1=_tmp(); e.synthesize('Turning left.',p1); first=open(p1,'rb').read(); os.remove(p1)
    p2=_tmp(); e.synthesize('Turning left.',p2); second=open(p2,'rb').read(); os.remove(p2)
    assert calls['synth']==1 and e.last_path=='cache' and first==second

def test_a_missing_python_api_falls_back_to_the_subprocess(monkeypatch):
    from voice import PiperEngine
    _fake_piper(monkeypatch,load_fails=True)
    sub=[]
    def fallback(t,p,s):
        sub.append(t)
        with wave.open(p,'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b'\x00\x00'*10)
    e=PiperEngine('m.onnx',fallback)
    p=_tmp(); e.synthesize('Checking a much longer sentence that will not be cached at all here',p); os.remove(p)
    assert sub and e.last_path=='subprocess'
