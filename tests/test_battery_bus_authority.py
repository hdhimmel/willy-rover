import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
pytest.importorskip('fcntl',reason='sensors.py needs fcntl: Linux only (CI, the rover)')
import config

# End-to-end regression asked for by the 2026-10-08 outside review: a BAD ADS1115 divider with a
# HEALTHY +12V bus must leave the battery reading on the bus and must never halt the rover.
# test_battery_halt.py stubs adc.battery_volts; this goes through the REAL sensors.ADC property
# (bus vs divider selection), the real _check_battery_crosscheck() (last two tests) and the real
# halt path. The 2026-10-01 incident
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


# The full sequence (outside review 2026-10-08: the tests above never ran the cross-check, and
# their no-halt assertion is trivially true at 11.98 V). Bus and divider are live values here so
# the bus can be switched off mid-test, as the motor cut does.

def _full(divider_v,monkeypatch):
    import sensors
    from brain import RoverBrain
    clock=[1000.0]; bus=[11.9]
    adc=_adc(divider_v,0.0); adc.bus_source=lambda: bus[0]
    monkeypatch.setattr(sensors.ADC,'is_healthy',property(lambda self: True),raising=False)
    b,halts=_brain(adc,0.0,clock,monkeypatch)
    b.current=types.SimpleNamespace(rail=lambda name:{'voltage_v':bus[0]})
    b._bat_xcheck_since=None; b._bat_xcheck_flagged=False
    b._check_battery_crosscheck=types.MethodType(RoverBrain._check_battery_crosscheck,b)
    return b,adc,halts,clock,bus

def _hold(b,v_fn,clock,threshold,windows=3):
    for _ in range(windows):
        b._battery_halt('battery',v_fn(),threshold,{},0.0); clock[0]+=config.BAT_HALT_CONFIRM_S+1

def test_crosscheck_flags_a_bad_divider_and_the_flag_vetoes_it_once_the_bus_is_gone(monkeypatch):
    b,adc,halts,clock,bus=_full(7.2,monkeypatch)
    # 1. Bus live: the cross-check sees divider 7.2 V vs bus 11.9 V and, after the grace period,
    #    flags the divider. The tiers read the bus meanwhile.
    assert b._check_battery_crosscheck()==''                      # first sighting: grace starts
    clock[0]+=config.BAT_CROSSCHECK_GRACE_S+1
    assert 'SUSPECT' in b._check_battery_crosscheck() and b._bat_xcheck_flagged
    assert adc.battery_volts==pytest.approx(11.9+config.BUS_TO_PACK_DROP_V)
    # Non-trivial contrast: the SAME halt path fed the divider's 7.2 V with no flag WOULD halt.
    # The protection while the bus is live is the selection above, not luck in the thresholds.
    b2,adc2,halts2,clock2,bus2=_full(7.2,monkeypatch); bus2[0]=0.0
    _hold(b2,lambda: adc2.battery_volts,clock2,config.BAT_SHUTDOWN_V)
    assert len(halts2)==1
    # 2. Bus goes down (motor cut): the divider is now the only reading, 7.2 V, far below every
    #    tier. The cross-check goes silent but KEEPS the flag, so the reading is disputed...
    bus[0]=0.0
    assert b._check_battery_crosscheck()=='' and b._bat_xcheck_flagged
    assert adc.battery_volts==pytest.approx(7.2,abs=0.01)
    assert b._battery_reading_disputed()
    # 3. ...and it cannot halt the rover, however long it stays low.
    _hold(b,lambda: adc.battery_volts,clock,config.BAT_SHUTDOWN_V,windows=5)
    assert halts==[]

def test_a_divider_that_agrees_again_is_trusted_and_a_real_low_pack_still_halts(monkeypatch):
    b,adc,halts,clock,bus=_full(7.2,monkeypatch)
    b._check_battery_crosscheck(); clock[0]+=config.BAT_CROSSCHECK_GRACE_S+1
    assert 'SUSPECT' in b._check_battery_crosscheck()
    # The divider is repaired / the pack really has sagged: divider and bus agree at 10.0 V.
    import sensors
    adc._bat_raw=10.0*config.BATTERY_DIVIDER_SCALE/sensors.ADC._LSB; bus[0]=10.0
    assert b._check_battery_crosscheck()=='' and not b._bat_xcheck_flagged
    # Bus drops out; the trusted divider reads 10.0 V, under BAT_SHUTDOWN_V: he halts.
    bus[0]=0.0
    assert not b._battery_reading_disputed()
    _hold(b,lambda: adc.battery_volts,clock,config.BAT_SHUTDOWN_V)
    assert len(halts)==1
