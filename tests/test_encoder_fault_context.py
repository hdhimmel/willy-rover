import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config

# Feature request 2938 (approved 2026-10-10, narrowed): an ENCODERS_FAULT names the power state.
# 23 such faults 10-07..09 were all the base being off at start-up, indistinguishable in the log
# from a real link failure.

def _b(frame,age,bus):
    import brain
    b=object.__new__(brain.RoverBrain)
    b.encoders=types.SimpleNamespace(_link=types.SimpleNamespace(latest=lambda k:(frame,age)))
    b.current=types.SimpleNamespace(rail=lambda n:{'voltage_v':bus})
    return b

def test_base_off_is_named_as_the_cause():
    v=_b(['E','1','2','0','0','0','0','0','0','3295','1'],12.3,0.0)._encoder_fault_value()
    assert 'last 12.3s ago' in v and 'last R5 3295mV' in v and '12V bus 0.0V' in v
    assert 'base power off' in v

def test_bus_live_points_at_pico_a_or_the_link():
    v=_b(None,None,12.0)._encoder_fault_value()
    assert 'never received' in v and 'bus live' in v and 'base power off' not in v
