import os,sys,subprocess,types,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# 2026-10-15 (owner): persistent memory -- more phrasings, no half-heard facts, an experience log.

@pytest.fixture
def mem(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    from memory_store import MemoryStore
    m=MemoryStore(); yield m
    try: m.close()
    except Exception: pass

def _voice(mem):
    import voice
    v=object.__new__(voice.VoicePipeline); v.memory=mem; v.said=[]; v.speak=v.said.append
    v.current_person=lambda: None
    return v

def test_name_with_remember_last_and_on_its_own(mem):
    v=_voice(mem)
    assert v._maybe_learn('My name is Howard. Remember that.') and mem.get_fact('my name')=='Howard'
    mem.delete_fact('my name')
    assert v._maybe_learn('my name is Howard') and mem.get_fact('my name')=='Howard'

def test_a_half_heard_fact_is_not_stored(mem):
    v=_voice(mem)
    assert v._maybe_learn('Remember that my name is...')
    assert mem.all_facts()=={} and 'say it again' in v.said[-1]
    assert v._maybe_learn('remember that the toy box is in the den') and len(mem.all_facts())==1

def test_experiences_are_stored_and_survive_reopening(mem,tmp_path):
    mem.add_experience('saw','Storm',1.0,2.0,'living room',at=time.time()-60)
    mem.add_experience('found','a ball')
    from memory_store import MemoryStore
    mem.close(); m2=MemoryStore()
    e=m2.last_experience('storm','saw')
    assert e and e['what']=='Storm' and e['room']=='living room'
    assert len(m2.experiences_since(time.time()-3600))==2
    m2.close()

def test_question_phrases():
    import voice
    v=object.__new__(voice.VoicePipeline)
    assert v._fast_path('when did you last see Storm')=={'intent':'last_seen','args':{'what':'Storm'},'reply':''}
    assert v._fast_path('when did you see the dog')['args']['what']=='dog'
    assert v._fast_path('what did you do today')['intent']=='my_day'

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT='''
import types,time,tempfile,config
config.WILLY_MEMORY_ROOT=tempfile.mkdtemp()
from memory_store import MemoryStore
from brain import RoverBrain
from odometry import Pose
b=types.SimpleNamespace(memory=MemoryStore(),odometry=types.SimpleNamespace(pose=Pose(0,0,0)),
                        world_model=types.SimpleNamespace(get_room=lambda x,y: types.SimpleNamespace(name='living room')))
b.memory.add_fact('name of the dog','Storm')
for m in ('_experience','_note_sightings','_last_seen_reply','_my_day_reply','_called'): setattr(b,m,types.MethodType(getattr(RoverBrain,m),b))
b._when=RoverBrain._when
assert "don't remember seeing Storm" in b._last_seen_reply('Storm')
b._note_sightings([{'class':'dog','conf':0.9},{'class':'chair','conf':0.9}])
b._note_sightings([{'class':'dog','conf':0.9}])                  # within the gap: not twice
assert len(b.memory.experiences_since(0))==1
r=b._last_seen_reply('storm'); assert r.startswith('I last saw Storm today at') and 'living room' in r, r
assert 'I last saw Storm' in b._last_seen_reply('dog')
b._experience('found','a ball'); b._experience('learned','where the toy box is')
d=b._my_day_reply(); assert 'I saw Storm' in d and '1 toy' in d and 'toy box' in d, d
print('EXPERIENCES_OK')
'''

def test_brain_records_sightings_and_answers():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert 'EXPERIENCES_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr[-3000:]}'
