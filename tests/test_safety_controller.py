import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from safety import SafetyController

# §20 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: tests/test_safety.py only covers the
# pure approve_motion() function -- SafetyController itself (tick()'s deadline enforcement,
# request()'s cancellation, emergency_stop()) has never had its own tests. A _FakeDriveBase
# (mirrors hw_sim.SimMotor's role) stands in for motors.DriveBase so these run with no hardware.

class _FakeDriveBase:
    def __init__(self): self.calls=[]
    def forward(self,speed=None): self.calls.append(('forward',speed))
    def reverse(self,speed=None): self.calls.append(('reverse',speed))
    def turn_left(self,speed=None): self.calls.append(('turn_left',speed))
    def turn_right(self,speed=None): self.calls.append(('turn_right',speed))
    def stop(self): self.calls.append(('stop',))
    def brake(self): self.calls.append(('brake',))

def _sc():
    drive=_FakeDriveBase()
    sc=SafetyController(drive)
    sc.update_context(front_cm=999.0,tilt_deg=0.0,bat_tier='normal',motion_enabled=True)
    return sc,drive

# --- command timeout (§20) ---

def test_tick_stops_drive_once_deadline_passes():
    sc,drive=_sc()
    sc.request('forward',0.5,0.05)  # 50ms timed move
    assert sc.timed_move_active is True
    time.sleep(0.06)
    still_active=sc.tick()
    assert still_active is False
    assert sc.timed_move_active is False
    assert ('stop',) in drive.calls

def test_tick_keeps_move_active_before_deadline():
    sc,drive=_sc()
    sc.request('forward',0.5,5.0)
    still_active=sc.tick()
    assert still_active is True and sc.timed_move_active is True

def test_tick_noop_when_no_move_in_flight():
    sc,drive=_sc()
    assert sc.tick() is False

# --- command cancellation (§20) ---

def test_new_request_overrides_in_flight_move():
    sc,drive=_sc()
    sc.request('forward',0.5,5.0)
    assert sc.timed_move_active is True
    sc.request('stop',None,None)  # continuous stop cancels the timed forward
    assert sc.timed_move_active is False
    assert drive.calls[-1]==('stop',)

def test_continuous_request_after_timed_move_clears_deadline():
    sc,drive=_sc()
    sc.request('forward',0.5,5.0)
    sc.request('forward',0.3,None)  # re-issued as continuous (e.g. ROAM resuming)
    assert sc.timed_move_active is False

# --- mid-flight obstacle re-check (tick()) ---

def test_tick_aborts_forward_move_if_obstacle_appears():
    sc,drive=_sc()
    sc.request('forward',0.5,5.0)
    sc.update_context(front_cm=config.DIST_STOP-1)  # obstacle appears mid-flight
    still_active=sc.tick()
    assert still_active is False and sc.timed_move_active is False
    assert ('stop',) in drive.calls

def test_tick_does_not_abort_non_forward_move_on_obstacle():
    sc,drive=_sc()
    sc.request('reverse',0.5,5.0)
    sc.update_context(front_cm=1.0)  # obstacle ahead is irrelevant while reversing
    still_active=sc.tick()
    assert still_active is True

# --- emergency_stop ---

def test_emergency_stop_calls_brake_not_stop():
    sc,drive=_sc()
    sc.request('forward',0.5,5.0)
    sc.emergency_stop('tilt fault')
    assert ('brake',) in drive.calls
    assert sc.timed_move_active is False

def test_emergency_stop_clears_pending_deadline():
    sc,drive=_sc()
    sc.request('forward',0.5,0.01)
    sc.emergency_stop('test')
    time.sleep(0.02)
    assert sc.tick() is False  # nothing left to time out -- already cleared

# --- request() respects cached context (update_context) ---

def test_request_rejected_uses_cached_context_not_stale_defaults():
    sc,drive=_sc()
    sc.update_context(tilt_deg=config.IMU_TILT_LIMIT+5)
    result=sc.request('forward',0.5,1.0)
    from safety import Rejected
    assert isinstance(result,Rejected)
    assert drive.calls[-1]==('stop',)  # Rejected branch always stops, per safety.py's own contract
