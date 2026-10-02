import os,sys,subprocess,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2026-10-02 gap closures, pinned:
#   FR-1000-001  "this is the kitchen" labels a room at the current pose
#   FR-1200-006  stairs stored as an edge (position, heading, width) and persisted
#   FR-1200-005  a mapped stair edge ahead becomes a virtual front obstacle at the standoff
#   FR-1900-007  a "when I say X" instruction is applied (one substitution)
#   FR-1900-008  "forget X" deletes matching facts/instructions
#   FR-1400-001  an unknown intent from the local model counts as not understood

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT=r'''
import math,types,tempfile,os,config
from world_model import WorldModel,ray_to_segment,Stair
from brain import RoverBrain
import voice

# ray/segment geometry
assert abs(ray_to_segment(0,0,0.0,(1,-1),(1,1))-1.0)<1e-9
assert ray_to_segment(0,0,math.pi,(1,-1),(1,1)) is None          # facing away
assert ray_to_segment(0,0,0.0,(1,0.5),(1,1)) is None             # misses the segment

# stairs persist across a reload
d=tempfile.mkdtemp(); path=os.path.join(d,"wm.db")
odo=types.SimpleNamespace(pose=types.SimpleNamespace(x=0,y=0,heading=0.0))
wm=WorldModel(odo,db_path=path); wm.add_stair("s1",1.0,0.0,0.0); wm.add_room("kitchen",0,0); wm.save()
wm2=WorldModel(odo,db_path=path)
assert [s.name for s in wm2.all_stairs()]==["s1"] and wm2.all_stairs()[0].width_m==config.STAIR_DEFAULT_WIDTH_M
assert wm2.get_room(0,0).name=="kitchen"

# standoff (SWD 6.6): planning-only, never alters d, fails closed
wm2.get_robot_pose=lambda: pose
ns=types.SimpleNamespace(world_model=wm2)
f=lambda d: RoverBrain._stair_planning_front(ns,d)
pose=types.SimpleNamespace(x=0,y=0,heading=0.0,stale=False)
d={"front":400.0,"left":400,"right":400}
pf,ok=f(d)
assert ok and abs(pf-((1.0-config.STAIR_STANDOFF_M)*100+config.DIST_STOP))<1e-6, pf
assert d["front"]==400.0                                            # the reflex reading is untouched
pose.x=1.0-config.STAIR_STANDOFF_M+0.01
assert f({"front":400.0})[0]<config.DIST_STOP                       # inside the standoff -> ROAM turns away
pose.x=0; pose.heading=math.pi
assert f({"front":400.0})==(400.0,True)                            # facing away
pose.stale=True
assert f({"front":400.0})[1] is False                              # stale pose with stairs mapped -> refuse
def boom(): raise RuntimeError("db")
ns2=types.SimpleNamespace(world_model=types.SimpleNamespace(all_stairs=boom))
assert RoverBrain._stair_planning_front(ns2,{"front":400.0})[1] is False   # error -> fail closed
ns3=types.SimpleNamespace(world_model=types.SimpleNamespace(all_stairs=lambda: []))
assert RoverBrain._stair_planning_front(ns3,{"front":400.0})==(400.0,True)  # no stairs -> no effect

# voice fast path
v=voice.VoicePipeline.__new__(voice.VoicePipeline)
assert v._fast_path("Hey Willie, this is the kitchen")=={"intent":"name_room","args":{"room":"kitchen"},"reply":""}
assert v._fast_path("we're in the living room.")["args"]["room"]=="living room"
assert v._fast_path("stairs ahead")["intent"]=="mark_stairs"
assert v._fast_path("the stairs are here")["intent"]=="mark_stairs"

# forget / recall
said=[]
class Mem:
    def __init__(s): s.f={"cup":"the blue cup is mine"}; s.i=[{"id":1,"trigger_phrase":"good night","action_text":"shut down"}]
    def all_facts(s): return dict(s.f)
    def all_instructions(s): return list(s.i)
    def delete_fact(s,k): s.f.pop(k)
    def delete_instruction(s,i): s.i=[x for x in s.i if x["id"]!=i]
    def add_fact(s,*a): pass
    def add_instruction(s,*a): pass
    def get_context_for(s,t): return {}
v.memory=Mem(); v.speak=lambda t,**k: said.append(t)
assert v._maybe_learn("what do you remember about cup") and "blue cup" in said[-1]
v.memory=Mem(); assert v._maybe_learn("forget about cup") and v.memory.f=={} and "forgotten 1" in said[-1]
v.memory=Mem(); assert v._maybe_learn("forget it") and v.memory.f!={} and "Tell me what" in said[-1]
v.memory=Mem(); assert v._maybe_learn("forget the bl") and v.memory.f!={}     # too short, nothing deleted
assert v._maybe_learn("forget about bananas") and "don't have anything" in said[-1]

# instruction applied + unknown-intent gate
acted=[]
v.memory=Mem(); v.display=None; v._utterance_timing=None
v._act_on_intent=lambda intent,text: acted.append(intent["intent"])
import time as _t
v._whisper=types.SimpleNamespace(transcribe=lambda *a,**k:([types.SimpleNamespace(text="good night")],None))
v._process_utterance(None,_t.time())
assert acted==["shutdown"], acted              # "good night" -> "shut down" -> fast path
v._local_ai=types.SimpleNamespace(ask_sync=lambda *a,**k: types.SimpleNamespace(
    parse_success=True,payload={"intent":"launch_rockets","args":{},"reply":"ok"},intent_confidence=0.99,reason=""))
payload,conf=v._interpret_local("do the thing")
assert conf==0.0, conf
print("RSM_OK")
'''

def test_rooms_stairs_and_memory():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'RSM_OK' in r.stdout, r.stdout+r.stderr

def test_routines_are_noted_and_reported():
    # FR-1900-005: repeated requests build up per hour; top_routines() reports them.
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    code=('import tempfile,os\n'
          'from memory_store import MemoryStore\n'
          'm=MemoryStore(os.path.join(tempfile.mkdtemp(),"m.db"))\n'
          'for _ in range(4): m.note_routine("status around 07:00")\n'
          'm.note_routine("battery around 09:00")\n'
          'assert m.top_routines()==[{"pattern":"status around 07:00","count":4}], m.top_routines()\n'
          'print("ROUTINE_OK")\n')
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'ROUTINE_OK' in r.stdout, r.stdout+r.stderr
