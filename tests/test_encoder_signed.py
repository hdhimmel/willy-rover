import os, sys, math, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config
import sensors
import odometry

# Signed encoder counts, 2026-10-01. Phase B turned out to be alive on all six new motors, so
# Pico A firmware a-0.3 decodes direction (x2: both edges of A, B sampled at each) and sends
# SIGNED counts. Measured that day, each wheel alone on the block: +throttle -> +counts on all
# six. The motors are mirrored, so rover-forward is +throttle on the left and -throttle on the
# right (config.MOTOR_SIGN) -- and therefore +counts left, -counts right. Odometry applies
# config.ENCODER_SIGN; Encoders keeps the board's raw sign.


class _Link:
    def __init__(self): self.f = None
    def fresh(self, kind, max_age_s): return self.f
    def frame(self, vals): self.f = ['E', '1', '0'] + [str(v) for v in vals] + ['3400', '1']


@pytest.fixture
def enc():
    e = sensors.Encoders.__new__(sensors.Encoders)
    e._link = _Link(); e._owns_link = False
    e._counts = dict.fromkeys(e._ORDER, 0); e._prev_raw = dict.fromkeys(e._ORDER)
    e._lock = threading.Lock(); e._last_ok = 0.0
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, 'SIMULATE_HARDWARE', False)
        yield e


def test_negative_counts_are_read_as_negative(enc):
    enc._link.frame((-5, 0, 7, 0, 0, -300))
    enc._update()
    assert enc.counts['lf'] == -5 and enc.counts['rf'] == 7 and enc.counts['rr'] == -300


def test_backwards_motion_counts_down(enc):
    enc._link.frame((100,) * 6); enc._update()
    enc._link.frame((40,) * 6); enc._update()
    assert enc.counts['lf'] == 40


def test_the_signed_32_bit_boundary_is_unwrapped(enc):
    """Pico A sends a signed 32-bit delta. Crossing +2^31 must read as +4, not -4 billion."""
    enc._link.frame((2147483646,) * 6); enc._update()
    before = enc.counts['lf']
    enc._link.frame((-2147483646,) * 6); enc._update()
    assert enc.counts['lf'] - before == 4


def test_the_unsigned_boundary_still_unwraps(enc):
    """a-0.2 and earlier sent unsigned. The same unwrap covers both."""
    enc._link.frame((0xFFFFFFFE,) * 6); enc._update()
    before = enc.counts['lf']
    enc._link.frame((2,) * 6); enc._update()
    assert enc.counts['lf'] - before == 4


class _FakeEnc:
    is_healthy = True
    def __init__(self): self.counts = dict.fromkeys(('lf', 'lm', 'rf', 'rm', 'lr', 'rr'), 0)


def test_rover_forward_is_straight_ahead_in_odometry():
    """Forward on a mirrored rover: left wheels count up, right wheels count DOWN. Without
    ENCODER_SIGN odometry would read that as spinning on the spot."""
    e = _FakeEnc(); o = odometry.Odometry(e)
    time.sleep(0.01)
    n = config.ENCODER_COUNTS_PER_REV
    for w in ('lf', 'lm', 'lr'): e.counts[w] = n
    for w in ('rf', 'rm', 'rr'): e.counts[w] = -n
    p = o.update()
    assert p.x == pytest.approx(math.pi * config.WHEEL_DIAMETER_M, rel=1e-6)
    assert abs(p.heading) < 1e-9


def test_rover_reverse_goes_backwards():
    e = _FakeEnc(); o = odometry.Odometry(e)
    time.sleep(0.01)
    for w in ('lf', 'lm', 'lr'): e.counts[w] = -100
    for w in ('rf', 'rm', 'rr'): e.counts[w] = 100
    assert o.update().x < 0


def test_a_pico_reboot_rebases_instead_of_jumping(enc):
    """A rebooted Pico A starts counting from zero again. Read as a delta, that is a huge
    backwards move into odometry; the link counts reboots, so re-base on one instead."""
    enc._link.reboots = 0
    enc._link.frame((5000,) * 6); enc._update()
    enc._link.frame((5100,) * 6); enc._update()
    assert enc.counts['lf'] == 5100
    enc._link.reboots = 1
    enc._link.frame((3,) * 6); enc._update()
    assert enc.counts['lf'] == 5100, 'the reboot was read as motion'
    enc._link.frame((10,) * 6); enc._update()
    assert enc.counts['lf'] == 5107
