import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config

# M-009 thermal monitoring: levels with hysteresis, fan-stopped check, and the brain saying it
# once -- never touching motion.

def _mon(temps,fan=5700):
    import thermal
    it=iter(temps)
    return thermal.ThermalMonitor(read_temp=lambda: next(it),read_fan=lambda: fan)

def _run(m,n):
    return [m.poll(i*config.THERMAL_POLL_S) for i in range(n)]

def test_levels_rise_and_clear_with_hysteresis():
    w,h,hy=config.THERMAL_WARM_C,config.THERMAL_HOT_C,config.THERMAL_HYSTERESIS_C
    temps=[50,w,h,h-1,h-hy-0.5,w-1,w-hy-0.5]
    m=_mon(temps)
    assert _run(m,len(temps))==[None,'warm','hot',None,'warm',None,'ok']

def test_poll_is_rate_limited():
    m=_mon([50,90])
    assert m.poll(0.0) is None and m.poll(0.1) is None
    assert m.temp_c==50

def test_unreadable_sensor_is_silent():
    import thermal
    m=thermal.ThermalMonitor(read_temp=lambda: None,read_fan=lambda: None)
    assert m.poll(0.0) is None and m.level=='ok'

def test_fan_stopped_only_counts_when_warm_enough():
    m=_mon([config.THERMAL_FAN_CHECK_C-5],fan=0); m.poll(0.0)
    assert not m.fan_stopped
    m=_mon([config.THERMAL_FAN_CHECK_C+1],fan=0); m.poll(0.0)
    assert m.fan_stopped
    m=_mon([90],fan=None); m.poll(0.0)       # no fan fitted: not a fault
    assert not m.fan_stopped

def test_brain_says_hot_and_fan_once():
    import brain
    said=[]
    b=object.__new__(brain.RoverBrain); b._say=said.append; b._fan_warned=False
    b.thermal=_mon([85,85,85],fan=0)
    for i in range(3):
        b.thermal._next_poll=0.0; b._thermal_tick()
    assert said==["My processor is running hot, 85 degrees.","My cooling fan has stopped."]
