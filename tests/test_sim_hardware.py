import os,sys,subprocess

# §19/§20 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: with WILLY_SIMULATE=1, every
# hardware-backed class should construct and run off the physical rover. This has to run as a
# *subprocess* rather than importing brain.py in-process: config.SIMULATE_HARDWARE gates
# conditional `import board,busio,...` statements at module-import time in motors.py/sensors.py/
# arm.py/brain.py, which only ever run once per process — test_safety.py/test_odometry.py already
# import config (in real-hardware mode) elsewhere in this same pytest run, so flipping the env
# var here wouldn't retroactively change already-imported modules. A subprocess gets a clean
# process where WILLY_SIMULATE is set before anything is imported, matching how this is actually
# meant to be used (`WILLY_SIMULATE=1 python3 main.py` on a dev machine without the rover attached).

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import brain,time
b=brain.RoverBrain()
assert b.motors._motors["lf"].throttle==0.0

b.start()
time.sleep(1.0)
assert b._motion_enabled, f"self-test failed under simulation: {b._init_fail_reason}"

b._tick()
assert b._state=="IDLE", f"expected IDLE after a clean self-test, got {b._state}"

b.safety.forward(0.4)
time.sleep(0.1)
assert b.motors._actual["lf"]>0.0, "sim DriveBase did not respond to a forward command"

pose=b.odometry.update()
assert pose.stale is False, "odometry pose should be fresh once sim Encoders are healthy"

b.stop()
print("SIM_OK")
'''

def test_roverbrain_full_lifecycle_under_simulation():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'SIM_OK' in result.stdout, (
        f'sim-mode RoverBrain lifecycle failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
