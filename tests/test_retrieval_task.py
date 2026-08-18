import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from retrieval_task import RetrievalTask

# retrieval_task.py had zero test coverage before this file, despite being called out in the
# gap analysis as the best-covered subsystem *architecturally* -- that referred to
# LOCALIZE/APPROACH/GRASP/VERIFY/DELIVER/AWAIT_CONFIRM matching the FRD's requested state list,
# not to any actual test file. These tests target the 2026-08-18 fix: _grasp() used to run its
# whole pulse sequence through blocking time.sleep() calls inside a single tick() call (~1.1s
# total), which meant a tilt/battery/sensor-fault abort() (called from brain.py's tick thread --
# the same thread _grasp() was blocking) had no way to run until the arm had already finished
# moving. That defeated the same non-blocking-control-loop guarantee Phase 1 (§2) established for
# drive motion. _grasp() is now a 4-step, deadline-serviced state machine polled from tick().

class _FakeSafety:
    def __init__(self): self.calls=[]; self._timed=False
    def stop(self): self.calls.append(('stop',))
    def forward(self,speed=None): self.calls.append(('forward',speed))
    def turn_left_for(self,duration,speed=None): self.calls.append(('turn_left_for',duration,speed))
    def turn_right_for(self,duration,speed=None): self.calls.append(('turn_right_for',duration,speed))
    @property
    def timed_move_active(self): return self._timed

class _FakeArm:
    def __init__(self): self.pulses=[]
    def set_pulse(self,joint,us): self.pulses.append((joint,us))

class _FakeDetector:
    def __init__(self,dets=None): self._dets=dets or []
    def detect(self,classes=None): return self._dets
    def localize(self,det): return (0.0,0.0)

def _grasp_task():
    rt=RetrievalTask(_FakeSafety(),_FakeArm(),_FakeDetector())
    rt.state='GRASP'; rt._bearing_deg=0.0
    return rt

# --- non-blocking (the actual safety fix) ---

def test_grasp_tick_returns_immediately_not_blocking():
    rt=_grasp_task()
    t0=time.perf_counter()
    rt.tick({'front':999},0.0)
    assert time.perf_counter()-t0<0.05  # old code blocked here for up to 0.5s per step

def test_grasp_first_tick_only_issues_open_step_pulses():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    assert rt.arm.pulses==[('base',config.ARM_SERVO_CENTER_US),('gripper',config.ARM_SERVO_MIN_US)]
    assert rt.state=='GRASP'  # not yet complete

def test_grasp_retick_before_deadline_is_a_noop():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    before=list(rt.arm.pulses)
    rt.tick({'front':999},0.0)  # deadline (0.3s) has not elapsed
    assert rt.arm.pulses==before

def test_grasp_full_sequence_completes_in_exactly_four_ticks():
    rt=_grasp_task()
    steps=0
    while rt.state=='GRASP' and steps<10:
        rt.tick({'front':999},0.0); steps+=1
        if rt._grasp_deadline is not None: rt._grasp_deadline=0  # fast-forward past the wait
    assert steps==4
    assert rt.state=='VERIFY'
    assert rt.arm.pulses==[
        ('base',config.ARM_SERVO_CENTER_US),('gripper',config.ARM_SERVO_MIN_US),
        ('shoulder_a',config.ARM_SERVO_CENTER_US-300),('elbow',config.ARM_SERVO_CENTER_US-300),
        ('gripper',config.ARM_SERVO_MAX_US),
        ('shoulder_a',config.ARM_SERVO_CENTER_US),('elbow',config.ARM_SERVO_CENTER_US),
    ]

# --- abort() can now land mid-grasp (this is the point of the fix) ---

def test_abort_mid_grasp_stops_before_later_steps_run():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)  # only the OPEN step has run
    pulses_before_abort=len(rt.arm.pulses)
    rt.abort('simulated tilt fault')
    assert rt.state=='ABORTED'
    assert ('stop',) in rt.safety.calls
    # the LOWER/CLOSE/RAISE steps must never run once aborted
    for _ in range(5): rt.tick({'front':999},0.0)
    assert len(rt.arm.pulses)==pulses_before_abort

def test_abort_resets_grasp_step_and_deadline():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    assert rt._grasp_step!=0 or rt._grasp_deadline is not None
    rt.abort('reason')
    assert rt._grasp_step==0 and rt._grasp_deadline is None

def test_abort_when_not_active_still_resets_grasp_state():
    rt=RetrievalTask(_FakeSafety(),_FakeArm(),_FakeDetector())
    rt.abort('reason')  # never started -- state is IDLE, not one of _MOTION_STATES
    assert rt.state=='ABORTED'
    assert rt._grasp_step==0 and rt._grasp_deadline is None
