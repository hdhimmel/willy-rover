import os,sys,threading,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
from multiprocessing import Pipe
import pytest
import config

# FR-1400-006 real fix: the Hailo chip lives in a child process (hailo_server.py). These drive
# the real serve() loop and the real client over in-memory pipes; the child's backends are fakes.

class _Proc:
    def __init__(self): self.killed=False
    def kill(self): self.killed=True
    def wait(self,timeout=None): return 0

def _launcher(on_detect,on_llm,info=None,procs=None):
    import hailo_server
    info=info or {'yolo':True,'llm':True,'input_shape':(640,640,3)}
    def launch():
        d_parent,d_child=Pipe(); l_parent,l_child=Pipe()
        threading.Thread(target=hailo_server.serve,args=(d_child,on_detect),daemon=True).start()
        threading.Thread(target=hailo_server.serve,args=(l_child,on_llm),daemon=True).start()
        p=_Proc()
        if procs is not None: procs.append(p)
        return p,d_parent,l_parent,info
    return launch

def test_detect_and_generate_round_trip():
    import hailo_server
    c=hailo_server.HailoServerClient(_launcher(lambda op,f: [f*2],lambda op,r: r['prompt'].upper()))
    assert c.detect(21)==[42]
    assert c.generate('hi',0.1,0.9,8)=='HI'
    assert hailo_server.RemoteYolo(c).get_input_shape()==(640,640,3)

def test_a_server_side_error_is_raised_but_the_server_keeps_serving():
    import hailo_server
    def on_llm(op,r):
        if r['prompt']=='bad': raise ValueError('nope')
        return 'fine'
    c=hailo_server.HailoServerClient(_launcher(lambda op,f: f,on_llm))
    with pytest.raises(RuntimeError,match='nope'): c.generate('bad',0,0,1)
    assert c.generate('good',0,0,1)=='fine'

def test_a_slow_generation_does_not_hold_up_detection():
    import hailo_server
    release=threading.Event()
    def on_llm(op,r): release.wait(5); return 'done'
    c=hailo_server.HailoServerClient(_launcher(lambda op,f: f,on_llm))
    out={}
    t=threading.Thread(target=lambda: out.setdefault('g',c.generate('x',0,0,1))); t.start()
    time.sleep(0.1)
    t0=time.monotonic(); assert c.detect(7)==7
    assert time.monotonic()-t0<1.0                      # separate channel, separate lock
    release.set(); t.join(5); assert out['g']=='done'

def test_a_timeout_kills_the_child_and_restarts_later(monkeypatch):
    import hailo_server
    monkeypatch.setattr(config,'HAILO_SERVER_DETECT_TIMEOUT_S',0.2)
    monkeypatch.setattr(config,'HAILO_SERVER_RESTART_S',0.0)
    hang=threading.Event(); procs=[]
    def on_detect(op,f):
        if f=='hang': hang.wait(2)
        return f
    c=hailo_server.HailoServerClient(_launcher(on_detect,lambda op,r: '',procs=procs))
    with pytest.raises(hailo_server.ServerDown): c.detect('hang')
    assert procs[0].killed
    assert c.detect('ok')=='ok' and len(procs)==2       # restarted on the next call
    hang.set()

def test_restart_is_rate_limited(monkeypatch):
    import hailo_server
    monkeypatch.setattr(config,'HAILO_SERVER_RESTART_S',60.0)
    calls=[]
    def launch():
        calls.append(1); raise hailo_server.ServerDown('no chip')
    c=hailo_server.HailoServerClient(launch)
    assert not c.start() and not c.start()
    assert len(calls)==1

def test_intent_model_uses_the_server_and_never_brakes(monkeypatch):
    import types
    for name in ('picamera2','picamera2.devices','hailo_platform','hailo_platform.genai'):
        mod=types.ModuleType(name); mod.Hailo=object; mod.LLM=object
        monkeypatch.setitem(sys.modules,name,mod)
    monkeypatch.delitem(sys.modules,'hailo_llm',raising=False)
    import hailo_llm
    braked=[]; hailo_llm.set_before_generate(lambda: braked.append(1))
    try:
        m=object.__new__(hailo_llm.HailoIntentModel); m._enabled=True; m._llm=None
        m._remote=types.SimpleNamespace(generate=lambda p,t,tp,mx: '{"intent":"stop","args":{},"reply":""}')
        r=m._call('stop')
        assert r.parse_success and braked==[]
    finally:
        hailo_llm.set_before_generate(None)

def test_simulation_never_starts_a_server(monkeypatch):
    import hailo_server
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',True)
    monkeypatch.setattr(hailo_server,'HailoServerClient',lambda: pytest.fail('started a server'))
    assert hailo_server.get_client() is None

@pytest.mark.skipif(sys.platform=='win32',reason='AF_UNIX listener: Linux only (CI, the rover)')
def test_the_real_child_process_starts_answers_and_quits():
    # No Hailo runtime on CI: the child still comes up, reports nothing loaded, and answers
    # every request with an error instead of dying. Proves the launch/handshake/quit path.
    import hailo_server
    c=hailo_server.HailoServerClient()
    try:
        assert c.start()
        assert c.info=={'yolo':False,'llm':False,'input_shape':None} or c.info.get('yolo') is not None
        if not c.info.get('yolo'):
            with pytest.raises(RuntimeError,match='unsupported'): c.detect(1)
        proc=c._proc
    finally:
        c.close()
    assert proc.poll() is not None
