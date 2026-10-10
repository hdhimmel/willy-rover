import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# 2026-10-10 (owner): "Willie needs to straighten his wheels before moving". A drive from rest with
# the wheels not known-straight centres all six, holds STEER_SETTLE_S, then goes.

class _Drive:
    def __init__(self): self.calls=[]; self.commanded={'lf':False}
    def forward(self,s): self.calls.append(('forward',s)); self.commanded={'lf':True}
    def reverse(self,s): self.calls.append(('reverse',s)); self.commanded={'lf':True}
    def turn_left(self,s): self.calls.append(('turn_left',s)); self.commanded={'lf':True}
    def turn_right(self,s): self.calls.append(('turn_right',s)); self.commanded={'lf':True}
    def stop(self): self.calls.append(('stop',None)); self.commanded={'lf':False}
    def brake(self): self.calls.append(('brake',None)); self.commanded={'lf':False}

class _Steer:
    def __init__(self,straight): self.straight=straight; self.centred=0
    def center_all(self): self.centred+=1; self.straight=True

def _sc(straight,monkeypatch,clock):
    import safety
    monkeypatch.setattr(safety.time,'time',lambda: clock[0])
    d=_Drive(); st=_Steer(straight)
    sc=safety.SafetyController(d,steering=st)
    sc.update_context(front_cm=200.0,tilt_deg=0.0,bat_tier='normal',motion_enabled=True)
    return sc,d,st

def test_crooked_wheels_are_centred_and_the_drive_waits(monkeypatch):
    clock=[100.0]; sc,d,st=_sc(False,monkeypatch,clock)
    sc.forward(0.5)
    assert st.centred==1 and ('forward',0.5) not in d.calls      # held back
    clock[0]+=config.STEER_SETTLE_S/2; sc.forward(0.5)
    assert ('forward',0.5) not in d.calls and st.centred==1       # still settling, not re-centred
    clock[0]+=config.STEER_SETTLE_S; sc.forward(0.5)
    assert d.calls[-1]==('forward',0.5)

def test_a_timed_move_starts_from_tick_after_settling(monkeypatch):
    clock=[100.0]; sc,d,st=_sc(False,monkeypatch,clock)
    sc.reverse_for(1.0,0.4)
    assert ('reverse',0.4) not in d.calls
    clock[0]+=config.STEER_SETTLE_S+0.01; sc.tick()
    assert ('reverse',0.4) in d.calls and sc.timed_move_active

def test_straight_wheels_go_at_once(monkeypatch):
    clock=[100.0]; sc,d,st=_sc(True,monkeypatch,clock)
    sc.forward(0.5)
    assert d.calls[-1]==('forward',0.5) and st.centred==0

def test_never_interrupts_a_rover_already_moving(monkeypatch):
    clock=[100.0]; sc,d,st=_sc(True,monkeypatch,clock)
    sc.forward(0.5); st.straight=False          # servos released mid-drive (2 s idle release)
    sc.forward(0.5)
    assert d.calls[-1]==('forward',0.5) and st.centred==0

def test_a_stop_cancels_a_held_back_start(monkeypatch):
    clock=[100.0]; sc,d,st=_sc(False,monkeypatch,clock)
    sc.forward_for(2.0,0.5); sc.emergency_stop('test')
    clock[0]+=1.0; sc.tick()
    assert ('forward',0.5) not in d.calls

def test_steering_straight_tracks_centre_and_release():
    import motors
    s=object.__new__(motors.Steering); s._centred=False; s._asleep=False
    s._pca=types.SimpleNamespace(channels={c:types.SimpleNamespace(duty_cycle=0) for c in range(16)},mode1_reg=0)
    s._idle_since=0.0
    s.center_all(); assert s.straight
    s.set_pulse('lf',1600); assert not s.straight
    s.center_all(); s._sleep(); assert not s.straight

def test_a_held_back_timed_move_counts_as_active(monkeypatch):
    # Voice "back up" -> MANUAL watches timed_move_active; False during the settle sent it to IDLE,
    # whose stop() cancelled the move before it began.
    clock=[100.0]; sc,d,st=_sc(False,monkeypatch,clock)
    sc.reverse_for(1.5,0.4)
    assert sc.timed_move_active and ('reverse',0.4) not in d.calls
    clock[0]+=config.STEER_SETTLE_S+0.01
    assert sc.tick() and ('reverse',0.4) in d.calls
