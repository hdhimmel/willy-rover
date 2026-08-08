import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# §20 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: RoverBrain._bat_tier_for/
# _update_bat_tier's hysteresis logic has never been directly unit tested -- only ever exercised
# indirectly through full sim construction. Runs as a subprocess under WILLY_SIMULATE=1, same
# reasoning as tests/test_sim_hardware.py: importing brain.py directly (in-process, without
# SIMULATE_HARDWARE) only happens to work when run ON the real Pi with Adafruit Blinka installed
# -- the rest of this suite deliberately avoids relying on that, and this test shouldn't either.
# _bat_tier_for/_update_bat_tier only read/write self._bat_tier and compare against config's
# threshold constants, so a lightweight types.SimpleNamespace stand-in is used as `self` instead
# of constructing a full RoverBrain (which pulls in the entire hardware/subsystem stack).

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types,config
from brain import RoverBrain

def fb(bat_tier="normal"):
    ns=types.SimpleNamespace(_bat_tier=bat_tier)
    ns._bat_tier_for=types.MethodType(RoverBrain._bat_tier_for,ns)  # _update_bat_tier calls this on self
    return ns

# 1. Worsening reacts immediately, no hysteresis.
f=fb("normal")
tier=RoverBrain._update_bat_tier(f,10.0)  # deep in shutdown range
assert tier=="shutdown" and f._bat_tier=="shutdown", tier

# 2. Recovery requires climbing BAT_HYSTERESIS_V past the tier\\'s own threshold, not just
#    crossing the raw boundary -- the exact behavior config.py\\'s own comment calls out as the
#    point of this design.
f=fb("shutdown")
tier=RoverBrain._update_bat_tier(f,config.BAT_SHUTDOWN_V+0.1)  # crossed the raw threshold...
assert tier=="shutdown", tier  # ...but not past +hysteresis yet, so no recovery
tier=RoverBrain._update_bat_tier(f,config.BAT_SHUTDOWN_V+config.BAT_HYSTERESIS_V)
assert tier=="safe", tier  # now recovered

# 3. Hovering near a boundary doesn\\'t flap.
f=fb("rth")
RoverBrain._update_bat_tier(f,config.BAT_RTH_V-0.05)
assert f._bat_tier=="rth"
RoverBrain._update_bat_tier(f,config.BAT_RTH_V+0.05)  # crossed the raw threshold, not +hysteresis
assert f._bat_tier=="rth"
RoverBrain._update_bat_tier(f,config.BAT_RTH_V-0.05)
assert f._bat_tier=="rth"

print("BATTERY_TIER_OK")
'''

def test_battery_tier_hysteresis_under_simulation():
    env=dict(os.environ,WILLY_SIMULATE='1')
    result=subprocess.run([sys.executable,'-c',_SCRIPT],cwd=_REPO_ROOT,env=env,
                           capture_output=True,text=True,timeout=30)
    assert 'BATTERY_TIER_OK' in result.stdout, (
        f'battery tier hysteresis test failed\n--- stdout ---\n{result.stdout}\n'
        f'--- stderr ---\n{result.stderr}')
