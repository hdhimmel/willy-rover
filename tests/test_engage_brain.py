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
