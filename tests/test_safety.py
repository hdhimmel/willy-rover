import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from safety import approve_motion,ApprovedMotion,Rejected

# Pure-logic tests for approve_motion() — no hardware/mocking needed, per
# docs/WildWilly_Claude_Fix_Implementation_Plan.md §20's testing requirements. This is the
# authoritative gate between any motion source and the physical motors (§3/§25); these tests
# assert what it lets through and what it rejects, independent of DriveBase/GPIO/I2C.

def test_motion_disabled_rejects_everything():
    r=approve_motion('forward',0.5,1.0,motion_enabled=False)
    assert isinstance(r,Rejected)

def test_unknown_action_rejected():
    r=approve_motion('teleport',0.5,1.0,motion_enabled=True)
    assert isinstance(r,Rejected)

def test_tilt_over_limit_rejected():
    r=approve_motion('forward',0.5,1.0,tilt_deg=config.IMU_TILT_LIMIT+0.1,motion_enabled=True)
    assert isinstance(r,Rejected)

def test_tilt_at_limit_not_over_is_allowed():
    r=approve_motion('forward',0.5,1.0,tilt_deg=config.IMU_TILT_LIMIT,front_cm=999,motion_enabled=True)
    assert isinstance(r,ApprovedMotion)

def test_battery_shutdown_tier_rejects_motion():
    r=approve_motion('forward',0.5,1.0,bat_tier='shutdown',motion_enabled=True)
    assert isinstance(r,Rejected)

def test_battery_safe_tier_rejects_motion():
    r=approve_motion('reverse',0.5,1.0,bat_tier='safe',motion_enabled=True)
    assert isinstance(r,Rejected)

def test_battery_warn_tier_still_allows_motion():
    r=approve_motion('forward',0.5,1.0,bat_tier='warn',front_cm=999,motion_enabled=True)
    assert isinstance(r,ApprovedMotion)

def test_forward_blocked_by_close_obstacle():
    r=approve_motion('forward',0.5,1.0,front_cm=config.DIST_STOP-1,motion_enabled=True)
    assert isinstance(r,Rejected)

def test_forward_allowed_when_clear():
    r=approve_motion('forward',0.5,1.0,front_cm=config.DIST_STOP+1,motion_enabled=True)
    assert isinstance(r,ApprovedMotion)

def test_reverse_ignores_front_obstacle():
    # obstacle check only applies to 'forward' — backing away from something in front is exactly
    # what AVOID uses this for.
    r=approve_motion('reverse',0.5,1.0,front_cm=1,motion_enabled=True)
    assert isinstance(r,ApprovedMotion)

def test_speed_clamped_to_max():
    r=approve_motion('forward',speed=99.0,duration=1.0,front_cm=999,motion_enabled=True)
    assert isinstance(r,ApprovedMotion) and r.speed==config.SPEED_MAX

def test_negative_speed_clamped_to_zero():
    r=approve_motion('forward',speed=-5.0,duration=1.0,front_cm=999,motion_enabled=True)
    assert isinstance(r,ApprovedMotion) and r.speed==0.0

def test_duration_clamped_to_max_command_duration():
    # this is the exact gap flagged by the gap analysis: an LLM-proposed duration was previously
    # passed straight to the motors with no clamp at all.
    r=approve_motion('forward',0.5,duration=9999.0,front_cm=999,motion_enabled=True)
    assert isinstance(r,ApprovedMotion) and r.duration==config.MAX_COMMAND_DURATION_S

def test_continuous_command_has_no_duration():
    r=approve_motion('forward',0.5,duration=None,front_cm=999,motion_enabled=True)
    assert isinstance(r,ApprovedMotion) and r.duration is None

def test_stop_rejected_like_any_other_action_but_harmlessly_so():
    # approve_motion('stop',...) is gated the same as every other action here — it can return
    # Rejected too. That's not a safety hole: SafetyController.request() (not tested in this
    # pure-logic module) always calls the underlying drive's stop() in its Rejected branch as
    # the fallback, so a rejected 'stop' request still results in the motors stopping. This test
    # just documents approve_motion()'s own behavior in isolation.
    r=approve_motion('stop',None,None,tilt_deg=999,bat_tier='shutdown',motion_enabled=False)
    assert isinstance(r,Rejected)
