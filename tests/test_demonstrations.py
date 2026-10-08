import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-1900-001/002/003 (built 2026-10-02): record a path by voice, save it as a demonstration and
# a route, replay it only from near where it started, and say so when it can't.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT=r'''
import os,types,tempfile,config
import voice
from brain import RoverBrain
from memory_store import MemoryStore

v=voice.VoicePipeline.__new__(voice.VoicePipeline)
assert v._fast_path("Watch me, learn the way to the kitchen")["args"]=={"name":"kitchen"}
assert v._fast_path("learn the route to the back door")["intent"]=="demo_start"
assert v._fast_path("that's it")["intent"]=="demo_stop"
assert v._fast_path("do the way to the kitchen")=={"intent":"demo_replay","args":{"name":"kitchen"},"reply":""}

mem=MemoryStore(os.path.join(tempfile.mkdtemp(),"m.db"))
pose=types.SimpleNamespace(x=0.0,y=0.0,heading=0.0,stale=False)
routes={}; said=[]; started=[]
wm=types.SimpleNamespace(get_robot_pose=lambda: pose,get_room=lambda x,y: None,
    add_route=lambda n,p: routes.__setitem__(n,p),get_route=lambda n: routes.get(n),save=lambda: None)
ns=types.SimpleNamespace(_demo=None,memory=mem,world_model=wm,
    pursuit=types.SimpleNamespace(active=False,abort=lambda r: None),
    navigator=types.SimpleNamespace(start=lambda m: (started.append(m.route),(True,"ok"))[1]),
    _go=lambda s: None,_say=lambda t: said.append(t))
for m in ("_demo_sample","_finish_demo"): setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))

# recording: one point per DEMO_POINT_SPACING_M, nothing from stale odometry
ns._demo={"name":"kitchen","points":[(0.0,0.0)],"started":0,"context":{"start_x":0.0,"start_y":0.0,"start_room":""}}
for i in range(1,21):
    pose.x=i*0.1; ns._demo_sample(pose)
pose.stale=True; pose.x=5.0; ns._demo_sample(pose); pose.stale=False; pose.x=2.0
assert len(ns._demo["points"])==7, ns._demo["points"]     # 0,0.3,..,1.8
ns._finish_demo()
assert "learned the way to the kitchen" in said[-1] and routes["kitchen"][-1]==(2.0,0.0)

# a demonstration that barely moved is not saved
ns._demo={"name":"nowhere","points":[(2.0,0.0)],"started":0,"context":{"start_x":2.0,"start_y":0.0}}
ns._finish_demo(); assert "nothing to learn" in said[-1] and "nowhere" not in routes

# replay: near the start -> all of it; near the path -> joins at the nearest point (FR-1900-002,
# 2026-10-08); far from the whole path -> refused (below the floor); unknown -> None
w,s,i=mem.replay_demonstration("kitchen",{"start_x":0.2,"start_y":0.1}); assert w and s==1.0 and i==0
w,s,i=mem.replay_demonstration("kitchen",{"start_x":1.2,"start_y":0.6}); assert w and i==4 and s>=config.MEMORY_REPLAY_SIMILARITY_FLOOR
assert tuple(w[0])==(0.0,0.0) and abs(w[i][0]-1.3)<1e-6   # the FULL path comes back; the index says where to join (points 0,.3,.6,1.0,1.3..)
w,s,i=mem.replay_demonstration("kitchen",{"start_x":1.0,"start_y":3.0}); assert w is None and i is None and s<config.MEMORY_REPLAY_SIMILARITY_FLOOR
assert mem.replay_demonstration("garage",{})==(None,None,None)
print("DEMO_OK")
'''

def test_demonstrations():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'DEMO_OK' in r.stdout, r.stdout+r.stderr
