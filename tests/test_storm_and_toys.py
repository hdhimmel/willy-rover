import os,sys,subprocess,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config

# 2026-10-15 (owner): purposeful exploring (find Storm, tidy the toys) and naming what he sees.

def test_naming_what_he_sees_is_stored():
    import voice
    v=object.__new__(voice.VoicePipeline)
    facts={}; said=[]
    v.memory=types.SimpleNamespace(add_fact=lambda k,val: facts.__setitem__(k,val))
    v.speak=said.append
    assert v._maybe_learn("That dog's name is Storm.")
    assert facts=={'name of the dog':'Storm'} and 'Storm' in said[-1]
    assert v._maybe_learn('the cat is called whiskers') and facts['name of the cat']=='Whiskers'

def test_purpose_phrases():
    import voice
    v=object.__new__(voice.VoicePipeline)
    for t,i in (('find Storm','find_storm'),("where's Storm",'find_storm'),('go find storm','find_storm'),
                ('tidy up the toys','tidy_toys'),('put the dog toys away','tidy_toys'),("pick up storm's toys",'tidy_toys'),
                ('this is the toy box','toy_box_here')):
        r=v._fast_path(t); assert r and r['intent']==i, (t,r)

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT='''
import types,time,config,arm_ik
from brain import RoverBrain
from odometry import Pose
DOG={'class':'dog','conf':0.8,'bbox':(500,300,700,500),'frame_w':1280,'frame_h':720}
BALL={'class':'sports ball','conf':0.8,'bbox':(600,500,660,560),'frame_w':1280,'frame_h':720}
def brain(dets):
    b=types.SimpleNamespace(_state='ROAM',said=[],_motion_enabled=True,_roam_ask_pending=False,_roam_permission=False,
        _init_fail_reason='',_idle_t=0.0)
    b._say=b.said.append; b._go=lambda s: setattr(b,'_state',s)
    b.safety=types.SimpleNamespace(stop=lambda: None)
    b.detector=types.SimpleNamespace(detect=lambda classes=None:[d for d in dets if not classes or d['class'] in classes])
    b.odometry=types.SimpleNamespace(pose=Pose(0,0,0))
    b.world_model=types.SimpleNamespace(update_observation=lambda o: None)
    b.memory=types.SimpleNamespace(get_fact=lambda k: 'Storm' if k=='name of the dog' else None)
    started=[]
    b.pursuit=types.SimpleNamespace(start=lambda *a,**k: (started.append(k),(True,'started'))[1])
    for m in ('_start_purpose','_end_purpose','_purpose_tick','_called'): setattr(b,m,types.MethodType(getattr(RoverBrain,m),b))
    return b,started
# find Storm: two looks in a row -> say so, pursue the dog at 1 m
b,started=brain([DOG]); b._state='IDLE'; b._start_purpose('find_storm'); assert b._state=='ROAM' and b._roam_permission
b._purpose_look_t=0; assert not b._purpose_tick()
b._purpose_look_t=0; assert b._purpose_tick() and b._state=='PURSUE'
assert started[0]['target_class']=='dog' and started[0]['standoff_cm']==config.STORM_STANDOFF_CM and 'found Storm' in b.said[-1]
# toys: found, said, not counted twice, summary at the end
b,_=brain([BALL]); b._start_purpose('tidy_toys')
for _ in range(6): b._purpose_look_t=0; b._purpose_tick()
assert len(b._toys_found)==1 and 'found a ball' in b.said[-1]
b._end_purpose('stopped'); assert 'I found 1 toy: 1 ball' in b.said[-1], b.said
# timeout
b,_=brain([]); b._start_purpose('find_storm'); b._roam_purpose=('find_storm',time.time()-config.PURPOSE_MAX_S-1)
assert b._purpose_tick() and b._state=='IDLE' and "couldn't find Storm" in b.said[-1]
# what do you see: names and articles
b,_=brain([]); assert b._called('dog')=='Storm' and b._called('apple')=='an apple' and b._called('cup')=='a cup'
print('STORM_TOYS_OK')
'''

def test_find_storm_and_tidy_toys_flow():
    env=dict(os.environ,WILLY_SIMULATE='1')
    r=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert 'STORM_TOYS_OK' in r.stdout, f'--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr[-3000:]}'
