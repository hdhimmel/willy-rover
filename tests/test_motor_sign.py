import os,sys,subprocess

# 2026-10-01: the motors are mounted harness-end outward, so left and right face opposite
# ways and the same throttle turns the sides opposite ways at the ground. Before
# config.MOTOR_SIGN, forward() pivoted the rover in place. Subprocess for the same reason as
# test_sim_hardware.py: WILLY_SIMULATE must be set before motors.py is imported.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import time,motors
d=motors.DriveBase()
d.forward(0.6); time.sleep(0.6)
t={w:d._motors[w].throttle for w in d._WHEELS}
assert all(t[w]>0 for w in ("lf","lm","lr")), t
assert all(t[w]<0 for w in ("rf","rm","rr")), t
assert d.current_speed>0, d.current_speed     # rover terms, not pin terms
d.turn_left(0.6); time.sleep(1.2)
t={w:d._motors[w].throttle for w in d._WHEELS}
assert all(v<0 for v in t.values()), t        # left back + right forward = same pin sign
d.cleanup()
print("SIGN_OK")
'''

def test_forward_drives_the_mirrored_sides_with_opposite_throttle():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'SIGN_OK' in result.stdout, (
        f'--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}')
