import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-2200 (built 2026-10-02). Pinned with synthetic history, per the FRD's own verification:
#   001 no evidence -> nothing sent; repeated events -> a request citing them; rate limit
#   002 nothing reaches the repo unapproved; wrong/expired codes refused; on approval exactly
#       one Markdown file is written and committed ALONE (git add <path>, commit --only)
#   003 the only artefact is a .md file

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT=r'''
import os,time,types,tempfile,config
import feature_requests as fr
from feature_requests import collect_evidence,FeatureRequests

now=time.mktime(time.strptime("2026-10-02 12:00:00","%Y-%m-%d %H:%M:%S"))
def line(day,hh,msg,mo=10): return f"2026-{mo:02d}-{day:02d} {hh}:00:00 WARNING brain {msg}\n"
stalls=[line(d,"10","EVENT=MOTOR_STALL subsystem=motors status=stalled wheels=lm",mo=9 if d>1 else 10)
        for d in (26,27,28,29,30,1)]
noise=[line(1,"09","EVENT=TICK_OVERRUN subsystem=brain duration_ms=160 threshold_ms=150")]*3
old=[line(1,"09","EVENT=MOTOR_STALL wheels=rr").replace("2026-10-01","2026-09-01")]*9

ev=collect_evidence(stalls+noise+old,now=now)
assert len(ev)==1 and ev[0]["key"]=="stall:lm" and ev[0]["count"]==6, ev   # old & sparse excluded
assert collect_evidence(noise,now=now)==[]

root=tempfile.mkdtemp(); os.makedirs(os.path.join(root,"logs"))
config.WILLY_LOG_ROOT="logs"
mails=[]; git=[]
class OK: returncode=0; stderr=""
email=types.SimpleNamespace(available=True,send_alert=lambda s,b: mails.append((s,b)))
draft={"title":"Fix the sticky left-middle wheel","problem":"lm stalled 6 times.","proposal":"Check the mount."}
cloud=types.SimpleNamespace(available=True,ask_sync=lambda *a,**k: types.SimpleNamespace(parse_success=True,payload=draft))
clock=[now]
f=FeatureRequests(cloud,email,root=root,run=lambda a:(git.append(a),OK)[1],now=lambda:clock[0])

# no evidence -> nothing sent
assert f.tick()=="no_evidence" and mails==[]
open(os.path.join(root,"logs","willy.log"),"w").writelines(stalls+noise)
assert f.tick()=="proposed" and len(mails)==1
subj,body=mails[0]
assert "machine-generated" in body and "6 x wheel stall (lm)" in body and "Willie: approve" in body
assert not os.path.exists(os.path.join(root,"docs"))                       # nothing in the repo yet
assert f.tick()=="pending"
code=f._load(config.FEATURE_REQUEST_PENDING_PATH,None)["code"]

# wrong code refused; right code writes ONE .md and commits it alone
assert f.approve("ffff" if code!="ffff" else "eeee","email, DKIM verified")[0] is False
ok,msg=f.approve(code,"email, DKIM verified"); assert ok, msg
made=[os.path.join(dp,n) for dp,_,ns in os.walk(os.path.join(root,"docs")) for n in ns]
assert len(made)==1 and made[0].endswith(".md"), made
txt=open(made[0],encoding="utf-8").read()
assert "status:    approved" in txt and "DKIM verified" in txt and "6 x wheel stall (lm)" in txt
rel=os.path.relpath(made[0],root).replace(os.sep,"/")
assert git[0]==["git","add","--",rel]
assert git[1][:3]==["git","commit","--only"] and git[1][-2:]==["--",rel]
assert not any("-A" in a or "." == a[-1] for a in git), git

# rate limit + same problem not re-proposed
clock[0]+=3600; assert f.tick()=="rate_limited"
clock[0]+=2*86400; assert f.tick()=="no_evidence"       # lm already proposed within 30 days

# unapproved request expires and never reaches the repo
root2=tempfile.mkdtemp(); os.makedirs(os.path.join(root2,"logs"))
open(os.path.join(root2,"logs","willy.log"),"w").writelines(stalls)
clock2=[now]; g2=[]
f2=FeatureRequests(cloud,email,root=root2,run=lambda a:(g2.append(a),OK)[1],now=lambda:clock2[0])
assert f2.tick()=="proposed"; code2=f2._load(config.FEATURE_REQUEST_PENDING_PATH,None)["code"]
clock2[0]+=config.FEATURE_REQUEST_EXPIRE_DAYS*86400+1
assert f2.approve(code2,"email, DKIM verified")==(False,"that request has expired")
assert g2==[] and not os.path.exists(os.path.join(root2,"docs"))

# cloud unavailable -> deferred, never composed on-device
root3=tempfile.mkdtemp(); os.makedirs(os.path.join(root3,"logs"))
open(os.path.join(root3,"logs","willy.log"),"w").writelines(stalls)
f3=FeatureRequests(types.SimpleNamespace(available=False),email,root=root3,run=lambda a:OK,now=lambda:now)
assert f3.tick()=="deferred"
print("FR_OK")
'''

def test_feature_requests():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'FR_OK' in r.stdout, r.stdout+r.stderr
