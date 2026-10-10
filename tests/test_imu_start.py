import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
pytest.importorskip('fcntl',reason='sensors.py needs fcntl: Linux only (CI, the rover)')
import config

# 2026-10-10: a wedged BNO085 at start-up must not crash the service (it crash-looped twice on
# 10-09). Try, hardware RST, try again, else start without the driver and let recovery work.

def _imu(make,reset=lambda: True):
    import sensors
    i=object.__new__(sensors.IMU); i._reset=reset; i._settle_s=0.0; i._make_bno=make
    return i

def test_starts_normally():
    assert _imu(lambda: 'bno')._first_bno()=='bno'

def test_a_wedged_chip_gets_a_hardware_reset_then_starts():
    n=[]; resets=[]
    def make():
        n.append(1)
        if len(n)==1: raise RuntimeError('Was not able to enable feature')
        return 'bno'
    assert _imu(make,reset=lambda: resets.append(1) or True)._first_bno()=='bno' and resets==[1]

def test_a_dead_chip_does_not_raise():
    def make(): raise RuntimeError('Was not able to enable feature')
    assert _imu(make)._first_bno() is None
    assert _imu(make,reset=None)._first_bno() is None

def test_no_driver_feeds_the_recovery_path(monkeypatch):
    import sensors
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',False)
    i=_imu(lambda: 'bno'); i._bno=None
    with pytest.raises(RuntimeError): i._update()
