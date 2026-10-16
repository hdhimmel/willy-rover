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
import threading,engage_words
said=[]; prompts=[]; rot=[]; cancelled=[]
def b2(state='ROAM',rotate_ok=True):
    b=brain()
    b._state=state; b._engage_topic=None; b._engage_prev_state=None
    b.voice=types.SimpleNamespace(available=True,busy=False,speak=said.append,
        prompt_listen=lambda cb,t: prompts.append(cb),set_current_person=lambda n: None,
        stop_requested=threading.Event(),cancel_prompt=cancelled.append)
    b.cloud_ai=None
    b.safety=types.SimpleNamespace(stop=lambda: None,emergency_stop=lambda why: None)
    def start_rotation(deg,then='IDLE'):
        rot.append((deg,then)); return (rotate_ok,'' if rotate_ok else 'blocked')
    b.start_rotation=start_rotation
    went=[]; b._go=lambda s: (went.append(s),setattr(b,'_state',s)); b.went=went
    b._upd=lambda *a,**k: None
    for n in ('_start_engage','_engage_tick','_engage_say','_engage_answer','_engage_store','_engage_end',
              '_engage_lock','_engage_apply_pending','_engage_act'):
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
assert cancelled==[prompts[0]], cancelled                # our open listen withdrawn
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

def test_stop_said_as_the_answer_stops_him():
    _run(_ENGAGE+r'''
b=b2('ROAM')
b._start_engage(Topic('ask_thing','sports ball@kitchen',{'thing':'sports ball','room':'kitchen'},True,None))
b._engage_tick({},0.0); wait(b)
prompts[0]('Willie, stop'); wait(b)
assert b.voice.stop_requested.is_set()
assert not b.memory.things('sports ball','kitchen') or not b.memory.things('sports ball','kitchen')[0].get('label')
assert b._engage_phase!='done' and b.went[-1]=='ENGAGE', (b._engage_phase,b.went)   # no resume
print('OK')
''')

def test_topic_ended_while_line_runs_says_nothing():
    _run(_ENGAGE+r'''
gate=threading.Event(); real=engage_words.line
engage_words.line=lambda t,c,timeout_s=None: (gate.wait(5),real(t,None))[1]
b=b2('IDLE')
b._start_engage(Topic('ask_room','0,0',{},True,None))
b._engage_tick({},0.0)                                  # worker now blocked in line()
b._engage_end('voice stop'); gate.set(); wait(b)
assert said==[] and prompts==[], (said,prompts)
print('OK')
''')

def test_old_answer_worker_does_not_touch_new_topic():
    _run(_ENGAGE+r'''
gate=threading.Event(); real=engage_words.extract
engage_words.extract=lambda t,x,c,timeout_s=None: (gate.wait(5),real(t,x,None))[1]
b=b2('IDLE')
a=Topic('ask_thing','sports ball@kitchen',{'thing':'sports ball','room':'kitchen'},True,None)
b._start_engage(a); b._engage_tick({},0.0); wait(b)
prompts[0]("It's Storm's")                              # answer worker blocked in extract()
old=b._engage_thread
b._engage_end('timed out')
b._start_engage(Topic('greet_known','Howard',{'name':'Howard'},False,None))
assert b._engage_phase=='say'
gate.set(); old.join(5)
assert b._engage_phase=='say', b._engage_phase          # old 'done' did not clobber it
assert not any(r.get('label') for r in b.memory.things('sports ball','kitchen'))
print('OK')
''')

# --- final fix wave (2026-10-15) ---
def test_stop_after_the_topic_ended_still_stops():
    _run(_ENGAGE+r'''
b=b2('ROAM')
t=Topic('ask_thing','sports ball@kitchen',{'thing':'sports ball','room':'kitchen'},True,None)
b._start_engage(t); b._engage_tick({},0.0); wait(b)
b._engage_end('timed out'); assert b.went[-1]=='ROAM'   # back to driving, capture already running
prompts[0]('Willie, stop')
assert b.voice.stop_requested.is_set()
print('OK')
''')

def test_engage_busy_during_tasks():
    _run(_ENGAGE+r'''
b=b2('IDLE'); b._engage_busy=types.MethodType(RoverBrain._engage_busy,b)
off=types.SimpleNamespace(active=False)
for n in ('teacher','mapping','routine','steer_override'): setattr(b,n,off)
b._roam_purpose=None; b._holding=False; b._bat_tier='normal'
assert b._engage_busy() is False
for n,v in (('_roam_purpose',('storm',0.0)),('_holding',True)):
    setattr(b,n,v); assert b._engage_busy() is True, n; setattr(b,n,None if n=='_roam_purpose' else False)
for n in ('teacher','mapping','routine','steer_override'):
    setattr(b,n,types.SimpleNamespace(active=True)); assert b._engage_busy() is True, n; setattr(b,n,off)
assert b._engage_busy() is False
print('OK')
''')

_FACE=_COMMON+r'''
import numpy as np
from identity import IdentityStore
from engage import Engagement
store=IdentityStore(os.path.join(tempfile.mkdtemp(),'id.db'))
base=np.ones(128,dtype=np.float32)/np.sqrt(128)
store.enrol('Carolyn',[base]); store.approve('Carolyn')
def seen_ago(s):
    store.note_seen('Carolyn'); store._c().execute('UPDATE presence SET at=?',(time.time()-s,)); store._c().commit()
def face_ns():
    ns=types.SimpleNamespace(identity=store,_engage_prev={},
        faces=types.SimpleNamespace(available=True,set_scanning=lambda on:None,frame_w=1280,
                                    latest=lambda: (time.time(),[((600,300,80,80),store.vector_at_distance(base,0.1))])),
        voice=types.SimpleNamespace(set_current_person=lambda n:None),
        world_model=types.SimpleNamespace(get_robot_pose=lambda: types.SimpleNamespace(x=0,y=0),get_room=lambda x,y:None))
    ns._face_tick=types.MethodType(RoverBrain._face_tick,ns); return ns
def first_tick(ago):
    seen_ago(ago); ns=face_ns(); f=ns._face_tick()
    return Engagement(MemoryStore('f.db')).tick('IDLE',[],f,types.SimpleNamespace(x=0,y=0),'den',False,ns._engage_prev)
'''

def test_face_back_after_hours_and_restart_mid_visit():
    _run(_FACE.replace('import types,','import os,types,')+r'''
t=first_tick(3*3600)
assert t.kind=='greet_known' and t.facts.get('about')=='back', t
assert first_tick(5*60) is None                          # restart mid-visit: already greeted
print('OK')
''')

def test_real_tick_voice_stop_ends_engagement():
    _run(r'''
import time,brain
from engage import Topic
b=brain.RoverBrain(); b.start(); time.sleep(1.0)
b._start_engage(Topic('greet_known','Howard',{'name':'Howard'},False,None))
assert b._state=='ENGAGE', b._state
b.voice.stop_requested.set(); b._tick()
assert b._state=='IDLE' and b._engage_topic is None, (b._state,b._engage_topic)
b.stop()
print('OK')
''')


def test_stop_between_the_check_and_the_action_stores_and_says_nothing():
    # 2026-10-16 (outside review): a stop landing after the answer was extracted but before it is
    # stored/acknowledged. Deterministic: the test holds the engage lock (as _engage_end does), the
    # answer worker blocks on it, the topic is ended, the lock released.
    _run(_ENGAGE+r'''
import threading
b=b2('IDLE')
t=Topic('ask_thing','sports ball@kitchen',{'thing':'sports ball','room':'kitchen'},True,None)
b._engage_topic=t
lock=b._engage_lock(); lock.acquire()
w=threading.Thread(target=b._engage_store,args=(t,"It's Storm's")); w.start()
time.sleep(0.3)
assert w.is_alive(), 'the store did not wait for the lock'
b._engage_topic=None                       # what _engage_end does under the lock
lock.release(); w.join(2)
assert not b.memory.things('sports ball','kitchen'), 'stored after stop'
assert not said, said
print('OK')
''')
