import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config
import sensors
from sensors import IMU, SonarArray

# BNO085 hardware reset, wired in 2026-10-01. Proven on the rover that day: RST over uart2-pi5
# -> Pico B pulses GP15 -> the chip reboots (SHTP advertisement, then EXE reset-complete). The
# driver object that was live across the reset does NOT recover by itself: two reads raised
# (KeyError, then RuntimeError 'Unprocessable Batch bytes') and then it quietly returned the
# last cached quaternion forever. So recovery is always reset AND rebuild, never reset alone.
#
# Fixtures force SIMULATE_HARDWARE off so the real code path runs whichever order the suite
# imports config in -- see test_sonar_tof_fusion.py for why that matters.


class _Bno:
    def __init__(self, fail=False):
        self.fail = fail
    @property
    def quaternion(self):
        if self.fail: raise OSError('wedged')
        return (0.0, 0.0, 0.0, 1.0)


@pytest.fixture
def imu():
    i = IMU.__new__(IMU)
    import threading
    i._pitch = 0.0; i._roll = 0.0; i._lock = threading.Lock(); i._last_ok = 0.0
    i._running = False; i._thread = None
    i._fails = 0; i._last_recover = float('-inf'); i.recoveries = 0
    i._last_q = None; i._last_change = 0.0
    i.resets = []
    i._reset = lambda: i.resets.append(1) or True
    i.built = 0
    def make():
        i.built += 1
        return _Bno()
    i._make_bno = make
    i._bno = _Bno(fail=True)
    i._settle_s = 0.0
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, 'SIMULATE_HARDWARE', False)
        yield i


def test_a_single_failed_read_does_not_reset(imu):
    imu._poll_once()
    assert imu.resets == [] and imu.built == 0


def test_consecutive_failures_reset_and_rebuild(imu):
    for _ in range(config.IMU_RESET_AFTER_FAILS):
        imu._poll_once()
    assert imu.resets == [1]
    assert imu.built == 1
    imu._poll_once()                       # the rebuilt driver reads
    assert imu._fails == 0 and imu.is_healthy


def test_recovery_is_rate_limited(imu):
    for _ in range(config.IMU_RESET_AFTER_FAILS):
        imu._poll_once()
    imu._bno = _Bno(fail=True)             # wedges again straight away
    for _ in range(config.IMU_RESET_AFTER_FAILS * 3):
        imu._poll_once()
    assert imu.resets == [1], 'must not hammer RST'


def test_no_reset_line_still_rebuilds(imu):
    """Without Pico B the soft path is all there is: rebuilding re-runs the library's
    I2C soft reset. Better than leaving a dead driver in place."""
    imu._reset = None
    for _ in range(config.IMU_RESET_AFTER_FAILS):
        imu._poll_once()
    assert imu.built == 1


def test_a_failed_rebuild_does_not_kill_the_loop(imu):
    def boom(): raise OSError('no device at 0x4A')
    imu._make_bno = boom
    for _ in range(config.IMU_RESET_AFTER_FAILS):
        imu._poll_once()                   # must not raise
    assert imu.resets == [1]


# --- the Pico B side: RST is only "done" when the board acknowledges it --------------

class _Link:
    def __init__(self, ack=True):
        self.sent = []; self.ack = ack; self._r = (['R', 'ok', '3'], 5.0)
    def send(self, cmd):
        self.sent.append(cmd)
        if cmd == 'RST' and self.ack:
            self._r = (['R', 'ok', '4'], 0.0)
        return True
    def latest(self, kind):
        return self._r if kind == 'R' else (None, None)


@pytest.fixture
def sonar():
    a = SonarArray.__new__(SonarArray)
    a._owns_link = False; a.tof = None
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, 'SIMULATE_HARDWARE', False)
        yield a


def test_reset_imu_clears_the_line_then_waits_for_the_ack(sonar):
    sonar._link = _Link()
    assert sonar.reset_imu(timeout_s=0.2) is True
    # The bare newline first: on 2026-10-01 the first RST after opening the port was lost,
    # most likely to a stray byte in front of it.
    assert sonar._link.sent == ['', 'RST']


def test_reset_imu_without_an_ack_reports_failure(sonar):
    sonar._link = _Link(ack=False)
    assert sonar.reset_imu(timeout_s=0.1) is False


class _FrozenBno:
    """What the live driver did after a reset it did not cause: no error, same answer forever."""
    quaternion = (0.0, 0.0, 0.0, 1.0)


def test_a_frozen_quaternion_counts_as_failure_and_recovers(imu, monkeypatch):
    t = [100.0]
    monkeypatch.setattr(sensors.time, 'monotonic', lambda: t[0])
    imu._bno = _FrozenBno()
    imu._poll_once()                       # first sight of this value: fine
    assert imu._fails == 0
    t[0] += config.IMU_STALE_S * 0.9
    imu._poll_once()
    assert imu._fails == 0, 'unchanged for less than IMU_STALE_S is normal at ~10 Hz reports'
    t[0] += config.IMU_STALE_S * 0.2
    for _ in range(config.IMU_RESET_AFTER_FAILS):
        imu._poll_once()
    assert imu.resets == [1] and imu.built == 1
