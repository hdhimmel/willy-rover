import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-200-004/005 (2026-10-02). A battery-tier halt now powers the Pi off through the FR-900-005
# graceful sequence. Because that is irreversible, it is gated three ways, all pinned here:
#   - the reading must stay under the tier threshold for BAT_HALT_CONFIRM_S (sag recovery resets it)
#   - a live +12V bus monitor that disagrees with the ADC blocks it (the 2026-10-01 8.53V incident)
#   - a dead bus (motor cut / base off) leaves the ADC as the authority -- unless the cross-check
#     last caught the divider disagreeing with the bus (2026-10-07)

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import types,config
import brain
from brain import RoverBrain

clock=[1000.0]
brain.time.time=lambda: clock[0]

def fb(adc_v,bus_v):
    halts=[]; shown=[]
    ns=types.SimpleNamespace(_bat_halt_since=None,_shutdown_after_stop=False,
        adc=types.SimpleNamespace(battery_volts=adc_v),
        current=types.SimpleNamespace(rail=lambda name:{"voltage_v":bus_v}))
    ns._upd=lambda fs,st,d,tilt,*a,**k: shown.append(st)
    ns._begin_shutdown=lambda reason: (halts.append(reason),setattr(ns,"_shutdown_after_stop",True))
    for m in ("_battery_reading_disputed","_battery_halt"):
        setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
    ns.halts=halts; ns.shown=shown
    return ns

T=config.BAT_RTH_V; C=config.BAT_HALT_CONFIRM_S

# 1. Halts only after the reading has stayed low for the whole confirm window.
f=fb(10.6,10.5)
f._battery_halt("low battery",10.6,T,{},0.0); assert f.halts==[]
clock[0]+=C-1; f._battery_halt("low battery",10.6,T,{},0.0); assert f.halts==[]
clock[0]+=2;   f._battery_halt("low battery",10.6,T,{},0.0); assert f.halts==["low battery"], f.halts

# 2. Sag recovery (reading back above the threshold) restarts the clock.
f=fb(10.6,10.5)
f._battery_halt("low battery",10.6,T,{},0.0)
clock[0]+=C-1; f._battery_halt("low battery",T+0.05,T,{},0.0)
clock[0]+=2;   f._battery_halt("low battery",10.6,T,{},0.0)
assert f.halts==[], "a recovered sag must restart the confirm window"

# 3. A live bus that disagrees blocks the halt entirely (2026-10-01: ADC 8.53V, bus 11.26V).
f=fb(8.53,11.26)
for _ in range(5):
    f._battery_halt("critical battery",8.53,config.BAT_SHUTDOWN_V,{},0.0); clock[0]+=C
assert f.halts==[] and "disputed" in f.shown[-1], f.shown[-1]

# 4. Bus down (motor cut / base off): the ADC is the authority and the halt proceeds.
f=fb(10.0,0.0)
f._battery_halt("critical battery",10.0,config.BAT_SHUTDOWN_V,{},0.0); clock[0]+=C+1
f._battery_halt("critical battery",10.0,config.BAT_SHUTDOWN_V,{},0.0)
assert f.halts==["critical battery"], f.halts

# 6. Bus down AND the divider was last caught disagreeing with the bus (2026-10-06/07: it read
#    7.2V then 15.4V on a 12V pack): the divider is the only reading left and is known bad, so
#    no halt acts on it.
f=fb(10.0,0.0); f._bat_xcheck_flagged=True
for _ in range(3):
    f._battery_halt("critical battery",10.0,config.BAT_SHUTDOWN_V,{},0.0); clock[0]+=C+1
assert f.halts==[] and "disputed" in f.shown[-1], f.shown[-1]

# 5. Docking is deferred, so the rth tier must never select DOCK.
assert config.ENABLE_DOCKING is False
print("HALT_OK")
'''

def test_battery_halt_is_confirmed_and_crosschecked():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'HALT_OK' in r.stdout, r.stdout+r.stderr
