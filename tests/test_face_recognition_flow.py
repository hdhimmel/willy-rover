import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-2100 behaviour (built 2026-10-02), with the camera/model replaced by fixed vectors:
#   recognised -> greeted once per session; uncertain -> silent; confidently unknown -> asked
#   only after N in a row, only once per session, never with nobody enrolled; a claimed name
#   resolves only an ACTIVE identity; enrolment approval only flips a pending identity;
#   per-person facts; the voice intents.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT=r'''
import os,time,types,tempfile,json
import numpy as np, config
from identity import IdentityStore,UNKNOWN,UNCERTAIN
from brain import RoverBrain
import voice
from memory_store import MemoryStore

store=IdentityStore(os.path.join(tempfile.mkdtemp(),"id.db"))
base=np.ones(128,dtype=np.float32)/np.sqrt(128)
said=[]; prompts=[]; slot=[None]
ns=types.SimpleNamespace(identity=store,_face_unknown_run=0,_face_asked_t=0.0,_face_asking=False,
    faces=types.SimpleNamespace(available=True,set_scanning=lambda on:None,latest=lambda: slot[0]),
    voice=types.SimpleNamespace(available=True,speak=lambda t,**k:said.append(t),set_current_person=lambda n:None,
                                prompt_listen=lambda cb,t: prompts.append(cb)),
    world_model=types.SimpleNamespace(get_robot_pose=lambda: types.SimpleNamespace(x=0,y=0),get_room=lambda x,y:None))
for m in ("_face_tick","_stranger_answer"): setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
def show(v): slot[0]=(time.time(),[((0,0,1,1),v)])

# nobody enrolled: a stranger is never asked about
for _ in range(5): show(store.vector_at_distance(base,0.95)); ns._face_tick()
assert said==[] and prompts==[]

store.enrol("Carolyn",[base]); store.approve("Carolyn")
show(store.vector_at_distance(base,0.1)); ns._face_tick(); ns._face_tick()
assert said==["Hi, Carolyn!"], said                                   # once per session
said.clear()
show(store.vector_at_distance(base,0.65)); ns._face_tick()           # uncertain band: silent
assert said==[] and prompts==[]
for i in range(config.FACE_STRANGER_CONFIRM_N-1):
    show(store.vector_at_distance(base,0.95)); ns._face_tick()
assert prompts==[]                                                     # not yet N in a row
show(store.vector_at_distance(base,0.95)); ns._face_tick()
assert said==["Hello! Who are you?"] and len(prompts)==1
n_before=store.vector_count("Carolyn")
prompts[0]("I'm Carolyn")                                             # asked from UNKNOWN band:
assert "Oh, hi Carolyn" in said[-1] and store.vector_count("Carolyn")==n_before   # no vector added
ns._face_asking=True; ns._stranger_answer("I'm Bob",base,UNKNOWN); assert said[-1]=="Stranger danger!"
ns._stranger_answer(None,base,UNKNOWN); assert said[-1]=="Stranger danger!"

# enrolment approval: only flips a PENDING identity, codes are single-use
store.enrol("Dave",[store.vector_at_distance(base,0.9)])
tmp=tempfile.mkdtemp(); config.FACE_PENDING_ENROL_PATH=os.path.join(tmp,"pend.json")
json.dump({"ab12":{"name":"Dave","expires":time.time()+60}},open(config.FACE_PENDING_ENROL_PATH,"w"))
ns2=types.SimpleNamespace(identity=store)
for m in ("_approve_enrolment","_load_pending_enrol","_save_pending_enrol"): setattr(ns2,m,types.MethodType(getattr(RoverBrain,m),ns2))
assert ns2._approve_enrolment("ffff","x") is None                     # not ours -> next handler
assert store.is_pending("Dave")
assert ns2._approve_enrolment("AB12","x")[0] is True and store.is_pending("Dave") is False
assert ns2._approve_enrolment("ab12","x") is None                     # single use

# voice intents
v=voice.VoicePipeline.__new__(voice.VoicePipeline)
assert v._fast_path("Willie, this is Carolyn")=={"intent":"enrol","args":{"name":"Carolyn"},"reply":""}
assert v._fast_path("this is the kitchen")["intent"]=="name_room"
assert v._fast_path("this is it") is None or v._fast_path("this is it")["intent"]!="enrol"
assert v._fast_path("forget everyone")["intent"]=="forget_everyone"

# per-person facts; instructions are never scoped
mem=MemoryStore(os.path.join(tempfile.mkdtemp(),"m.db"))
mem.add_fact("[Carolyn] tea","Carolyn takes her tea black"); mem.add_fact("door","the back door sticks")
mem.add_instruction("good night","shut down")
c=mem.get_context_for("tea door good night",person="Howard")
assert "[Carolyn] tea" not in c["facts"] and "door" in c["facts"] and c["instructions"]
assert "[Carolyn] tea" in mem.get_context_for("tea",person="Carolyn")["facts"]
print("FACES_OK")
'''

def test_face_recognition_flow():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'FACES_OK' in r.stdout, r.stdout+r.stderr
