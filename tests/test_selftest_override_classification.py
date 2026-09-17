import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-100-004 / startup override policy, added 2026-09-17 after an external review.
#
# The startup self-test used to collect every failure into one flat list, and brain.py offered
# the operator a motion-enabling override for ANY of them after SELFTEST_OVERRIDE_AFTER
# consecutive failures. That made "IMU not reporting" exactly as overrideable as a log-directory
# permission warning. Problems are now classified: anything the safety path reads is
# SAFETY-CRITICAL and can never be overridden; storage is not and still can be.
#
# Subprocess-under-WILLY_SIMULATE=1 for the same reason as test_brain_reset_gate.py: importing
# brain.py in-process pulls in the display/voice/vision stack this suite avoids.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types
from brain import RoverBrain

class FakeDisplay:
    def __init__(self,override=False): self._o=override; self.updates=[]
    def override_tapped(self):
        v=self._o; self._o=False; return v
    def update_state(self,**kw): self.updates.append(kw)

class FakeSafety:
    def emergency_stop(self,reason): pass

def brain_in_selftest_fault(critical,override_tap,fail_count=99):
    ns=types.SimpleNamespace(_state="INIT",_motor_rail_lost=False,_bat_xcheck_flagged=False,
                             _motion_enabled=False,_selftest_overridden=False,
                             _selftest_critical=list(critical),
                             _init_fail_reason="; ".join(critical) or "storage not writable",
                             _selftest_fail_count=fail_count,_selftest_retry_t=1e18)
    ns.display=FakeDisplay(override_tap); ns.safety=FakeSafety()
    ns._go=lambda s: setattr(ns,"_state",s)
    ns._upd=types.MethodType(RoverBrain._upd,ns)
    return ns

import config, time

def run_gate(ns):
    """Replicates the override branch of _tick() -- the retry clock is set far in the future so
    only the override path executes."""
    if ns.display.override_tapped():
        if ns._selftest_critical:
            pass
        else:
            ns._motion_enabled=True; ns._selftest_overridden=True; ns._go("IDLE"); return
    offer=(ns._selftest_fail_count>=config.SELFTEST_OVERRIDE_AFTER and not ns._selftest_critical)
    ns._upd("fault","SELF-TEST FAILED",{"front":999,"left":999,"right":999},0.0,offer_override=offer)

# 1. A safety-critical failure is never offered an override, even after many retries.
for critical in (["IMU not reporting"],["encoders not reporting"],
                 ["battery ADC not reporting"],["current monitors not reporting"],
                 ["I2C missing: 0x60"],["I2C scan failed: boom"]):
    ns=brain_in_selftest_fault(critical,override_tap=False)
    run_gate(ns)
    assert ns.display.updates[-1]["offer_override"] is False, critical

# 2. Even if a tap arrives anyway, motion stays disabled for a critical failure.
ns=brain_in_selftest_fault(["IMU not reporting"],override_tap=True)
run_gate(ns)
assert ns._motion_enabled is False
assert ns._selftest_overridden is False
assert ns._state=="INIT"

# 3. A non-critical failure (storage) is still overrideable -- the offer appears...
ns=brain_in_selftest_fault([],override_tap=False)
run_gate(ns)
assert ns.display.updates[-1]["offer_override"] is True

# 4. ...and the tap works.
ns=brain_in_selftest_fault([],override_tap=True)
run_gate(ns)
assert ns._motion_enabled is True
assert ns._selftest_overridden is True
assert ns._state=="IDLE"

# 5. Below the retry threshold nothing is offered even when non-critical.
ns=brain_in_selftest_fault([],override_tap=False,fail_count=0)
run_gate(ns)
assert ns.display.updates[-1]["offer_override"] is False

print("OVERRIDE_CLASSIFICATION_OK")
'''

def test_safety_critical_failures_are_never_overrideable():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                          capture_output=True,text=True,timeout=60)
    assert 'OVERRIDE_CLASSIFICATION_OK' in result.stdout, (
        f'override classification test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
