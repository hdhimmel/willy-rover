import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-07, live: a 5.4 s Hailo generation froze the whole process -- IMU, encoders, current
# monitors, battery ADC and sonars all faulted at once and recovered within 0.1 s of it returning.
# generate_all() holds the GIL. Interim fix: brake synchronously before every generation.

def _import_hailo_llm(monkeypatch):
    # The Hailo runtime only exists on the rover; stub it so the hook can be tested anywhere.
    pc=types.ModuleType('picamera2'); dev=types.ModuleType('picamera2.devices'); dev.Hailo=object
    hp=types.ModuleType('hailo_platform'); gen=types.ModuleType('hailo_platform.genai'); gen.LLM=object
    for name,mod in (('picamera2',pc),('picamera2.devices',dev),('hailo_platform',hp),('hailo_platform.genai',gen)):
        monkeypatch.setitem(sys.modules,name,mod)
    monkeypatch.delitem(sys.modules,'hailo_llm',raising=False)
    import hailo_llm
    return hailo_llm

def test_the_hook_runs_before_every_generation(monkeypatch):
    hl=_import_hailo_llm(monkeypatch)
    order=[]
    class _LLM:
        def generate_all(self,prompt,**k): order.append('generate'); return '{"intent":"chat","args":{},"reply":"","confidence":0.9}'
        def clear_context(self): pass
    m=object.__new__(hl.HailoIntentModel)
    m._enabled=True; m._llm=_LLM()
    hl.set_before_generate(lambda: order.append('brake'))
    try:
        try: m._call('hello')
        except Exception: pass               # parsing details are not under test here
        assert order[:2]==['brake','generate'], order
    finally:
        hl.set_before_generate(None)

def test_a_failing_hook_does_not_stop_the_generation(monkeypatch):
    hl=_import_hailo_llm(monkeypatch)
    called=[]
    class _LLM:
        def generate_all(self,prompt,**k): called.append(1); return '{}'
        def clear_context(self): pass
    m=object.__new__(hl.HailoIntentModel); m._enabled=True; m._llm=_LLM()
    def boom(): raise RuntimeError('bus')
    hl.set_before_generate(boom)
    try:
        try: m._call('hello')
        except Exception: pass
        assert called==[1]
    finally:
        hl.set_before_generate(None)

def _brain(commanded):
    from brain import RoverBrain
    b=types.SimpleNamespace(braked=0)
    b.motors=types.SimpleNamespace(commanded=commanded)
    b.safety=types.SimpleNamespace(brake_now=lambda reason: setattr(b,'braked',b.braked+1))
    b._brake_before_hailo=types.MethodType(RoverBrain._brake_before_hailo,b)
    return b

def test_brain_brakes_only_when_something_is_moving():
    b=_brain({'lf':True,'lm':False,'lr':False,'rf':False,'rm':False,'rr':False})
    b._brake_before_hailo(); assert b.braked==1
    b=_brain({w:False for w in ('lf','lm','lr','rf','rm','rr')})
    b._brake_before_hailo(); assert b.braked==0

def test_brake_now_brakes_from_any_thread_and_leaves_timed_state_alone():
    from safety import SafetyController
    calls=[]
    s=SafetyController(types.SimpleNamespace(brake=lambda: calls.append('brake')))
    s._deadline=123.0; s._active_action='forward'
    s.brake_now('test')
    assert calls==['brake'] and s._deadline==123.0 and s._active_action=='forward'
