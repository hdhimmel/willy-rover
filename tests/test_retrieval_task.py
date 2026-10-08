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
    def __init__(self): self.pulses=[]; self._p={}
    def set_pulse(self,joint,us): self.pulses.append((joint,us)); self._p[joint]=us
    def pulse(self,joint): return self._p.get(joint,1500)
    def was_driven(self,joint): return joint in self._p

class _FakeDetector:
    def __init__(self,dets=None): self._dets=dets or []
    def detect(self,classes=None): return self._dets
    def localize(self,det): return (0.0,0.0)

import pytest
_REACH={'shoulder':1210,'elbow':1300,'wrist_pitch':1500}   # a stand-in; the real one is unmeasured

@pytest.fixture(autouse=True)
def _reach(monkeypatch): monkeypatch.setattr(config,'ARM_POSE_REACH',dict(_REACH))

def _grasp_task():
    rt=RetrievalTask(_FakeSafety(),_FakeArm(),_FakeDetector())
    rt.state='GRASP'; rt._bearing_deg=0.0
    return rt

def _run(rt,limit=200):
    n=0
    while rt.state=='GRASP' and n<limit:
        rt.tick({'front':999},0.0); n+=1
        if rt._grasp_deadline is not None: rt._grasp_deadline=0   # fast-forward each wait
    return n

# --- non-blocking (the 2026-08-18 safety fix, kept through the 2026-10-08 rebuild) ---

def test_grasp_tick_returns_immediately_not_blocking():
    rt=_grasp_task()
    t0=time.perf_counter()
    rt.tick({'front':999},0.0)
    assert time.perf_counter()-t0<0.05

def test_grasp_first_tick_only_opens_the_gripper_to_its_measured_open():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    assert rt.arm.pulses==[('gripper',config.GRIP_OPEN_US)]
    assert rt.state=='GRASP'

def test_grasp_retick_before_deadline_is_a_noop():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    before=list(rt.arm.pulses)
    rt.tick({'front':999},0.0)
    assert rt.arm.pulses==before

def test_full_grasp_obeys_the_arm_rules_and_reaches_verify():
    rt=_grasp_task(); _run(rt)
    assert rt.state=='VERIFY' and rt._grip_result=='unsensed'      # no feedback in this fake
    P=rt.arm.pulses; joints=[j for j,_ in P]
    assert joints.index('elbow')<joints.index('shoulder')            # elbow opens first
    assert ('elbow',config.ARM_SERVO_CENTER_US) not in P              # never the 1500 us elbow
    sh=[u for j,u in P if j=='shoulder']
    assert max(abs(b-a) for a,b in zip([config.ARM_POSE_REST['shoulder']]+sh,sh))<=config.ARM_WAVE_APPROACH_STEP_US
    g=[u for j,u in P if j=='gripper']
    assert all(config.GRIP_OPEN_US<=u<=config.GRIP_CLOSED_US for u in g)

# --- abort() can land mid-grasp ---

def test_abort_mid_grasp_stops_before_later_steps_run():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    n=len(rt.arm.pulses)
    rt.abort('simulated tilt fault')
    assert rt.state=='ABORTED' and ('stop',) in rt.safety.calls
    for _ in range(5): rt.tick({'front':999},0.0)
    assert len(rt.arm.pulses)==n

def test_abort_resets_grasp_state():
    rt=_grasp_task()
    rt.tick({'front':999},0.0)
    rt.abort('reason')
    assert rt._phase is None and rt._plan==[] and rt._grasp_deadline is None

def test_abort_when_not_active_still_resets_grasp_state():
    rt=RetrievalTask(_FakeSafety(),_FakeArm(),_FakeDetector())
    rt.abort('reason')
    assert rt.state=='ABORTED'
    assert rt._grasp_step==0 and rt._grasp_deadline is None
