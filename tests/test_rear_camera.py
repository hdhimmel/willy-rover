import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# Rear camera (2026-10-10): on-demand, privacy-gated, used for rotation and to ADD a stop while
# reversing when a person or pet is close behind.

class _Cap:
    def __init__(self,frame): self.frame=frame; self.released=False
    def read(self): return True,self.frame
    def release(self): self.released=True

def _cam(monkeypatch,frame='F',clock=None):
    import vision
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',False)
    caps=[]
    def open_cap(): c=_Cap(frame); caps.append(c); return c
    t=clock or [0.0]
    return vision.RearCamera(open_cap=open_cap,clock=lambda: t[0]),caps,t

def test_opens_on_demand_and_closes_when_idle(monkeypatch):
    cam,caps,t=_cam(monkeypatch)
    assert caps==[]                               # nothing opened until asked
    assert cam.grab()=='F' and len(caps)==1
    t[0]+=config.REAR_CAM_IDLE_CLOSE_S+1; cam.close_if_idle()
    assert caps[0].released

def test_privacy_closes_and_returns_nothing(monkeypatch):
    import privacy
    cam,caps,t=_cam(monkeypatch); cam.grab()
    monkeypatch.setattr(privacy,'camera_enabled',lambda: False)
    assert cam.grab() is None and caps[0].released

def test_a_failed_open_is_not_retried_every_tick(monkeypatch):
    import vision
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',False)
    n=[]; t=[0.0]
    cam=vision.RearCamera(open_cap=lambda: n.append(1),clock=lambda: t[0])
    assert cam.grab() is None and cam.grab() is None and len(n)==1
    t[0]+=config.REAR_CAM_RETRY_S+1; cam.grab(); assert len(n)==2

def test_close_person_behind_is_tall_in_frame():
    from vision import rear_person_close
    far={'class':'person','bbox':(0,300,50,500),'frame_h':800}
    near={'class':'person','bbox':(0,100,300,700),'frame_h':800}
    chair={'class':'chair','bbox':(0,0,800,800),'frame_h':800}
    assert not rear_person_close([far]) and rear_person_close([near]) and not rear_person_close([chair])

def test_detect_without_a_server_reports_nothing(monkeypatch):
    cam,caps,t=_cam(monkeypatch)
    assert cam.detect(client=types.SimpleNamespace(info={'yolo':False}))==[]

def test_brain_camera_only_adds_a_stop_while_reversing(monkeypatch):
    import brain,time
    b=object.__new__(brain.RoverBrain)
    b.sonars=types.SimpleNamespace(rear_cm=lambda: 120.0)
    b.rear_cam=types.SimpleNamespace(close_if_idle=lambda: None)
    b.safety=types.SimpleNamespace(last_action='reverse')
    b._rear_block=True; b._rear_block_t=time.monotonic()
    assert b._rear_cm()==0.0 and b._rear_watch            # person close behind: stop reversing
    b._rear_block=False
    assert b._rear_cm()==120.0                             # clear: the ToF reading stands
    b.safety.last_action='forward'; b._rear_block=True
    assert b._rear_cm()==120.0 and not b._rear_watch       # not reversing: camera not consulted
    b.safety.last_action='reverse'; b._rear_block_t=time.monotonic()-10
    assert b._rear_cm()==120.0                             # stale camera verdict is ignored
