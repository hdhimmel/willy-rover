# tests/test_engage_brain.py
import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _run(script):
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',script],cwd=_REPO_ROOT,env=env,capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'OK' in r.stdout

_COMMON=r'''
import types,time,tempfile,config
config.WILLY_MEMORY_ROOT=tempfile.mkdtemp()
from brain import RoverBrain
from memory_store import MemoryStore
def det(cls): return {'class':cls,'bbox':(600,300,680,400),'frame_w':1280,'frame_h':720}
def brain():
    b=types.SimpleNamespace(memory=MemoryStore('b.db'),_engage_prev={},
        world_model=types.SimpleNamespace(get_robot_pose=lambda: types.SimpleNamespace(x=0.0,y=0.0),
                                          get_room=lambda x,y: types.SimpleNamespace(name='kitchen')),
        _experience=lambda kind,what: b.memory.add_experience(kind,what),
        _called=lambda c: 'Storm' if c=='dog' else c)
    for n in ('_note_sightings',):
        setattr(b,n,types.MethodType(getattr(RoverBrain,n),b))
    return b
'''

def test_sightings_record_things_and_previous_times():
    _run(_COMMON+r'''
b=brain()
b._note_sightings([det('sports ball'),det('chair')])
assert b._engage_prev=={'thing:sports ball@kitchen':None}, b._engage_prev
assert b.memory.things('sports ball','kitchen')
assert not b.memory.things('chair','kitchen')
b._engage_prev.clear(); b.__dict__['_sighted']={}
b._note_sightings([det('sports ball')])
assert b._engage_prev['thing:sports ball@kitchen'] is not None
b._engage_prev.clear(); b.__dict__['_sighted']={}
b._note_sightings([det('dog')])
assert 'saw:Storm' in b._engage_prev
print('OK')
''')

_ENGAGE=_COMMON+r'''
from engage import Topic
said=[]; prompts=[]; rot=[]
def b2(state='ROAM',rotate_ok=True):
    b=brain()
    b._state=state; b._engage_topic=None; b._engage_prev_state=None
    b.voice=types.SimpleNamespace(available=True,busy=False,speak=said.append,
        prompt_listen=lambda cb,t: prompts.append(cb),set_current_person=lambda n: None)
    b.cloud_ai=None
    b.safety=types.SimpleNamespace(stop=lambda: None,emergency_stop=lambda why: None)
    def start_rotation(deg,then='IDLE'):
        rot.append((deg,then)); return (rotate_ok,'' if rotate_ok else 'blocked')
    b.start_rotation=start_rotation
    went=[]; b._go=lambda s: (went.append(s),setattr(b,'_state',s)); b.went=went
    b._upd=lambda *a,**k: None
    for n in ('_start_engage','_engage_tick','_engage_say','_engage_answer','_engage_store','_engage_end'):
        setattr(b,n,types.MethodType(getattr(RoverBrain,n),b))
    return b
def wait(b):
    for _ in range(100):
        if getattr(b,'_engage_thread',None) is None or not b._engage_thread.is_alive(): return
        time.sleep(0.02)
'''

def test_roam_stops_turns_speaks_and_resumes():
    _run(_ENGAGE+r'''
b=b2('ROAM')
b._start_engage(Topic('ask_thing','sports ball@kitchen',{'thing':'sports ball','room':'kitchen'},True,30.0))
assert rot==[(30.0,'ENGAGE')], rot                      # turned toward it via Rotation
b._state='ENGAGE'; b._engage_tick({},0.0); wait(b)
assert said[0] in [s.format(thing='sports ball') for s in config.ENGAGE_TEMPLATES['ask_thing']], said
assert len(prompts)==1
prompts[0]("It's Storm's"); wait(b)
assert b.memory.things('sports ball','kitchen')[0]['label']=="Storm's sports ball"
b._engage_tick({},0.0)
assert b.went[-1]=='ROAM', b.went
print('OK')
''')

def test_refused_turn_still_speaks():
    _run(_ENGAGE+r'''
b=b2('IDLE',rotate_ok=False)
b._start_engage(Topic('greet_known','Howard',{'name':'Howard'},False,40.0))
assert b._state=='ENGAGE'
b._engage_tick({},0.0); wait(b)
assert said and said[0].startswith(('Hi','Hello','Hey'))
b._engage_tick({},0.0); assert b.went[-1]=='IDLE'
print('OK')
''')

def test_answer_after_stop_is_ignored():
    _run(_ENGAGE+r'''
b=b2('IDLE')
b._start_engage(Topic('ask_room','0,0',{},True,None))
b._engage_tick({},0.0); wait(b)
b._engage_end('voice stop')
prompts[0]('This is the kitchen'); wait(b)
assert not hasattr(b.world_model,'added'), 'stored after stop'
assert said==['What room is this?'] or said==["Can you tell me what room I'm in?"]
print('OK')
''')

def test_engage_times_out():
    _run(_ENGAGE+r'''
b=b2('IDLE')
b._start_engage(Topic('ask_room','0,0',{},True,None))
b._engage_tick({},0.0); wait(b)
b._engage_t0-=config.ENGAGE_MAX_S+1
b._engage_tick({},0.0)
assert b.went[-1]=='IDLE'
print('OK')
''')

def test_stranger_danger_is_gone():
    src=open(os.path.join(_REPO_ROOT,'brain.py'),encoding='utf8').read()
    assert 'Stranger danger' not in src
