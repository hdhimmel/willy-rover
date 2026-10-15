import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config,grip,startup_check

# 2026-10-14 (owner): at start-up, check every sensor is DELIVERING readings and report failures.
# On that day the boot self-test passed while both ToF gave no frames and the rear sonar was dead.

def _brain(**over):
    ok=types.SimpleNamespace(is_healthy=True)
    tof=types.SimpleNamespace(available=True,profile=object())
    b=types.SimpleNamespace(
        sonars=types.SimpleNamespace(is_healthy=True,failed_channels={},tof=tof,tof_rear=tof),
        imu=ok,encoders=ok,adc=types.SimpleNamespace(battery_volts=11.8),
        current=types.SimpleNamespace(is_healthy=True,rail=lambda n: {'voltage_v':6.04,'current_a':0.1}),
        detector=types.SimpleNamespace(available=True,_hailo_backend=True,capture_frame=lambda: 'frame'),
        rear_cam=types.SimpleNamespace(grab=lambda: 'frame'),
        said=[],display=types.SimpleNamespace(update_state=lambda *a: None))
    b._say=b.said.append
    for k,v in over.items(): setattr(b,k,v)
    return b

@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(config,'ENABLE_TOF',True); monkeypatch.setattr(config,'ENABLE_TOF_REAR',True)
    monkeypatch.setattr(grip,'read_feedback',lambda adc,cur: 0.19)

def test_all_good_reports_nothing():
    assert startup_check.failures(_brain())==[]

def test_the_morning_of_2026_10_14_is_reported():
    dead=types.SimpleNamespace(available=False,profile=object())
    b=_brain(sonars=types.SimpleNamespace(is_healthy=True,failed_channels={'rear':'not updated'},
                                          tof=dead,tof_rear=dead))
    f=dict(startup_check.failures(b))
    assert 'front ToF' in f and 'rear ToF' in f and 'rear' in f['sonar']
    startup_check.report(b,startup_check.failures(b))
    assert b.said and 'front ToF' in b.said[0] and 'not working' in b.said[0]

def test_cameras_and_gripper_feedback(monkeypatch):
    monkeypatch.setattr(grip,'read_feedback',lambda adc,cur: None)
    b=_brain(rear_cam=types.SimpleNamespace(grab=lambda: None),
             detector=types.SimpleNamespace(available=True,_hailo_backend=True,capture_frame=lambda: None))
    f=dict(startup_check.failures(b))
    assert set(f)=={'front camera','rear camera','gripper'}

def test_a_check_that_raises_is_reported_not_fatal():
    def boom(): raise RuntimeError('i2c')
    b=_brain(rear_cam=types.SimpleNamespace(grab=boom))
    assert dict(startup_check.failures(b))['rear camera'].startswith('check failed')

def test_runs_once_after_the_delay(monkeypatch):
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',False)
    t=[0.0]; b=_brain(sonars=types.SimpleNamespace(is_healthy=False,failed_channels={},tof=None,tof_rear=None))
    sc=startup_check.StartupCheck(b,clock=lambda: t[0],background=False)
    sc.tick(); assert not sc.done
    t[0]=config.STARTUP_SENSOR_CHECK_S; sc.tick(); assert sc.done and sc.result
    n=len(b.said); sc.tick(); assert len(b.said)==n          # reported once


def test_runs_off_the_tick_thread(monkeypatch):
    # 2026-10-15: on the tick it stalled the loop 914 ms
    import threading
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',False)
    seen=[]; b=_brain()
    monkeypatch.setattr(startup_check,'failures',lambda b: seen.append(threading.current_thread().name) or [])
    t=[0.0]; sc=startup_check.StartupCheck(b,clock=lambda: t[0])
    t[0]=config.STARTUP_SENSOR_CHECK_S; sc.tick()
    for th in threading.enumerate():
        if th.name=='startup-check': th.join(2)
    assert seen==['startup-check']


def test_a_rear_camera_that_is_still_opening_is_not_a_failure(monkeypatch):
    # 2026-10-15 09:40: it had just closed itself; the next grab reopens in the background
    frames=iter([None,None,'frame'])
    monkeypatch.setattr(config,'STARTUP_CAM_WAIT_S',2.0)
    monkeypatch.setattr(startup_check.time,'sleep',lambda s: None)
    b=_brain(rear_cam=types.SimpleNamespace(grab=lambda: next(frames)))
    assert 'rear camera' not in dict(startup_check.failures(b))
