import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
pytest.importorskip('fcntl',reason='sensors.py needs fcntl: Linux only (CI, the rover)')
import config

# End-to-end regression asked for by the 2026-10-08 outside review: a BAD ADS1115 divider with a
# HEALTHY +12V bus must leave the battery reading on the bus and must never halt the rover.
# test_battery_halt.py stubs adc.battery_volts; this goes through the REAL sensors.ADC property
# (bus vs divider selection), the real cross-check and the real halt path. The 2026-10-01 incident
# (stale divider scale read 11.37 V as 8.53 V, rover walked to SHUTDOWN) is the case it locks out.

def _adc(divider_v,bus_v):
    import sensors
    a=object.__new__(sensors.ADC)
    a._bat_raw=divider_v*config.BATTERY_DIVIDER_SCALE/sensors.ADC._LSB
    a.bus_source=lambda: bus_v
    return a

def _brain(adc,bus_v,clock,monkeypatch):
    import brain
    from brain import RoverBrain
    monkeypatch.setattr(brain.time,'time',lambda: clock[0])
    halts=[]; shown=[]
    ns=types.SimpleNamespace(_bat_halt_since=None,_shutdown_after_stop=False,adc=adc,
        current=types.SimpleNamespace(rail=lambda name:{'voltage_v':bus_v}))
    ns._upd=lambda fs,st,d,tilt,*a,**k: shown.append(st)
    ns._begin_shutdown=lambda reason: (halts.append(reason),setattr(ns,'_shutdown_after_stop',True))
    for m in ('_battery_reading_disputed','_battery_halt'):
        setattr(ns,m,types.MethodType(getattr(RoverBrain,m),ns))
    return ns,halts

@pytest.mark.parametrize('divider_v',[7.2,0.09,15.4])     # readings the real divider has given
def test_bad_divider_healthy_bus_reads_the_bus_and_never_halts(divider_v,monkeypatch):
    bus=11.9; clock=[1000.0]
    adc=_adc(divider_v,bus)
    assert adc.battery_volts==pytest.approx(bus+config.BUS_TO_PACK_DROP_V)
    assert adc.divider_volts==pytest.approx(divider_v,abs=0.01)
    b,halts=_brain(adc,bus,clock,monkeypatch)
    assert not b._battery_reading_disputed()
    for _ in range(5):
        for tier in (config.BAT_RTH_V,config.BAT_SHUTDOWN_V):
            b._battery_halt('battery',adc.battery_volts,tier,{},0.0)
        clock[0]+=config.BAT_HALT_CONFIRM_S+1
    assert halts==[]

def test_same_divider_with_the_bus_down_is_the_reading_and_can_halt(monkeypatch):
    # The other half of the contract: bus dead (motor cut, base off) -> the divider is all
    # there is, and a genuinely low pack still halts (unless the divider was flagged suspect).
    clock=[1000.0]
    adc=_adc(9.0,0.0)
    assert adc.battery_volts==pytest.approx(9.0,abs=0.01)
    b,halts=_brain(adc,0.0,clock,monkeypatch)
    for _ in range(3):
        b._battery_halt('battery',adc.battery_volts,config.BAT_SHUTDOWN_V,{},0.0)
        clock[0]+=config.BAT_HALT_CONFIRM_S+1
    assert len(halts)==1
