import os,sys,time,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')

import config
from tof import FramePoller

# Two defects found 2026-09-20, both pinned here.
#
# 1. THE ToF WAS NEVER WIRED IN. sensors.py's SonarArray said "Set by brain.py when ENABLE_TOF"
#    and brain.py contained no such assignment, so SonarArray.tof was None for the life of the
#    process and the fusion branch in distances() was dead code.
# 2. WIRING IT NAIVELY WOULD HAVE BLOCKED THE TICK. distances() is read on the tick thread and
#    read_frame is a ~0.13s polled round trip -- 2.6 ticks of a 20Hz loop, against
#    TICK_OVERRUN_THRESHOLD_S=0.15, every tick. FramePoller moves the wait off the tick.
#
# The staleness rule below is the ToF's and NOT the sonar's. Nothing sits underneath the sonar,
# so a stale sonar reading must stop the rover; a stale ToF frame must simply stop being used.

_FRAME=[100]*config.TOF_ZONES


def _settled(poller,want_none,tries=50,gap=0.01):
    """Poll the poller until it agrees, so the tests never race its thread."""
    for _ in range(tries):
        got=poller()
        if (got is None)==want_none: return got
        time.sleep(gap)
    return poller()


def test_returns_none_before_any_successful_read():
    # A poller that has never had a frame must report None, not an empty or guessed frame --
    # ToFSensor turns that into "unavailable", i.e. sonar alone.
    p=FramePoller(lambda:None,interval=0.01,stale_after=10.0)
    assert p() is None
    p.start()
    try: assert _settled(p,want_none=True) is None
    finally: p.stop()


def test_serves_the_cached_frame_without_blocking():
    p=FramePoller(lambda:list(_FRAME),interval=0.01,stale_after=10.0)
    p.start()
    try:
        assert _settled(p,want_none=False)==_FRAME
        # The whole point: reading it is cheap and does not wait on the sensor.
        t0=time.perf_counter()
        for _ in range(1000): p()
        assert time.perf_counter()-t0<0.5
    finally: p.stop()


def test_a_frame_older_than_stale_after_is_reported_as_no_frame():
    # Holding the last good frame forward is worse than having no sensor: a dead ToF would go on
    # reporting clear floor, or an obstacle, for ever.
    p=FramePoller(lambda:list(_FRAME),interval=0.01,stale_after=0.05)
    p.start()
    try: assert _settled(p,want_none=False)==_FRAME
    finally: p.stop()
    time.sleep(0.15)
    assert p() is None


def test_a_source_returning_none_does_not_refresh_freshness():
    # A failed read is not a fresh "nothing there". If None refreshed the timestamp a
    # permanently failing sensor would look healthy for ever.
    state={'ok':True}
    p=FramePoller(lambda:(list(_FRAME) if state['ok'] else None),interval=0.01,stale_after=0.05)
    p.start()
    try:
        assert _settled(p,want_none=False)==_FRAME
        state['ok']=False
        assert _settled(p,want_none=True) is None
    finally: p.stop()


def test_a_raising_source_does_not_kill_the_thread():
    # An unplugged cable must not permanently disable the ToF -- it must recover when replugged.
    state={'boom':True}
    def src():
        if state['boom']: raise OSError('cable out')
        return list(_FRAME)
    p=FramePoller(src,interval=0.01,stale_after=10.0)
    p.start()
    try:
        assert _settled(p,want_none=True) is None
        state['boom']=False
        assert _settled(p,want_none=False)==_FRAME
    finally: p.stop()


def test_stop_is_idempotent_and_safe_before_start():
    p=FramePoller(lambda:list(_FRAME),interval=0.01)
    p.stop(); p.start(); p.stop(); p.stop()


_WIRING_SCRIPT='''
import config
config.ENABLE_TOF=False
import brain
b=brain.RoverBrain.__new__(brain.RoverBrain)
# The names brain.py must import for the wiring to exist at all.
assert hasattr(brain,'ToFSensor') and hasattr(brain,'FramePoller') and hasattr(brain,'read_frame')
src=open(brain.__file__.replace('.pyc','.py')).read()
assert 'self.sonars.tof=ToFSensor(source=self._tof_poller)' in src, 'ToF never wired into SonarArray'
assert 'FramePoller(read_frame)' in src, 'ToF wired to the blocking transport, not the poller'
print('OK')
'''


def test_brain_wires_the_tof_into_the_sonar_array():
    # Subprocess for the same reason as tests/test_brain_stall.py: importing brain.py in-process
    # needs the full display/audio stack this suite deliberately does not depend on.
    root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=root)
    r=subprocess.run([sys.executable,'-c',_WIRING_SCRIPT],capture_output=True,text=True,
                     cwd=root,env=env)
    assert r.returncode==0,(r.stdout,r.stderr)
    assert 'OK' in r.stdout
