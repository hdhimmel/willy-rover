import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config
import pico_link
import sensors

# pico_link carries every sonar and encoder reading on this rover, and it sits in the
# safety path: SonarArray decides whether forward motion is allowed from what this module
# says arrived and when. It had NO tests until 2026-09-30.
#
# What is worth testing here is not "does it parse a line". It is the handful of ways a
# serial link fails that a naive reader turns into confident wrong data:
#
#   * a frame corrupted in transit, which must be dropped, not half-believed
#   * a link that goes quiet, which must NOT keep serving its last good reading
#   * a link that drops one frame in ten, which still LOOKS fresh -- the frames that do
#     arrive are recent -- and is only visible in the sequence numbers
#   * a Pico that reboots under us, losing any ZERO or RST state it held
#   * a counter that wraps at 16 bits, which must not read as a gap
#   * a sonar that hears no echo (clear) versus a sonar we cannot hear (stop)
#
# That last pair is Software Design S-9 and it is the reason this module exists.


class FakePort:
    """The subset of pyserial PicoLink actually uses. Feed it bytes; it hands them over
    in whatever chunks the test asks for, because real serial reads split frames at
    arbitrary points and a reader that only works on whole lines is broken."""

    def __init__(self, chunks=(), raise_after=None):
        self._pending = list(chunks)
        self._raise_after = raise_after
        self._reads = 0
        self.written = b''
        self.closed = False

    def feed(self, data):
        self._pending.append(data)

    @property
    def in_waiting(self):
        if self._raise_after is not None and self._reads >= self._raise_after:
            raise OSError('device disconnected')
        return len(self._pending[0]) if self._pending else 0

    def read(self, n):
        self._reads += 1
        return self._pending.pop(0) if self._pending else b''

    def write(self, b):
        self.written += b
        return len(b)

    def flush(self):
        pass

    def close(self):
        self.closed = True


def _frame(body):
    return pico_link.frame(body).encode()


def _e(seq, counts=(0,) * 6, ms=0, r5=3392, flags=0):
    return _frame('E,%d,%d,%s,%d,%d' % (seq, ms, ','.join(str(c) for c in counts), r5, flags))


def _s(seq, ch=((-1, -1), (-1, -1), (-1, -1)), ms=0, flags=0):
    parts = []
    for mm, age in ch:
        parts += [str(mm), str(age)]
    return _frame('S,%d,%d,%s,%d' % (seq, ms, ','.join(parts), flags))


def _drain(link, timeout=1.0):
    """Wait until the reader has consumed what it was given."""
    end = time.time() + timeout
    while time.time() < end and link._serial._pending:
        time.sleep(0.005)
    time.sleep(0.02)


@pytest.fixture
def link():
    l = pico_link.PicoLink('/dev/fake', 'test')
    yield l
    l.stop()


# --- framing ---------------------------------------------------------------------

def test_a_good_frame_is_accepted_and_split_into_fields(link):
    link._accept(pico_link.frame('E,7,120,1,2,3,4,5,6,3300,0').strip())
    fields, age = link.latest('E')
    assert fields[0] == 'E' and fields[1] == '7'
    assert fields[3:9] == ['1', '2', '3', '4', '5', '6']
    assert age < 1.0


def test_a_corrupted_frame_is_dropped_not_half_believed(link):
    link._accept(pico_link.frame('E,7,120,1,2,3,4,5,6,3300,0').strip())
    good, _ = link.latest('E')
    # one character changed in transit; the checksum no longer matches
    link._accept('$E,9,120,99,99,99,99,99,99,3300,0*00')
    still, _ = link.latest('E')
    assert still == good, 'a bad checksum overwrote the last good frame'
    assert link.bad_checksums == 1


def test_noise_and_partial_lines_do_not_raise(link):
    for junk in ('', 'garbage', '$no-star', '$E,1,2*', '*$', '$*ZZ'):
        link._accept(junk)
    assert link.latest('E') == (None, None)


def test_frames_split_across_reads_are_reassembled(link):
    whole = _e(1, (10, 20, 30, 40, 50, 60))
    port = FakePort([whole[:5], whole[5:12], whole[12:]])
    link.start(port=port)
    _drain(link)
    fields = link.fresh('E', 5.0)
    assert fields is not None, 'a frame delivered in three chunks was lost'
    assert fields[3:9] == ['10', '20', '30', '40', '50', '60']


# --- freshness: the S-9 guarantee ------------------------------------------------

def test_fresh_refuses_a_frame_older_than_the_deadline(link):
    link._accept(pico_link.frame('S,1,0,100,0,200,0,300,0,0').strip())
    assert link.fresh('S', 5.0) is not None
    assert link.fresh('S', 0.0) is None, 'a stale frame was served as fresh'


def test_there_is_no_accessor_that_serves_stale_data_as_current():
    """latest() returns the age alongside, so a caller cannot use it without seeing how
    old it is. fresh() is the only thing that hands over bare fields, and it refuses past
    the deadline. If a `last_value` property ever appears here, S-9 is back."""
    api = [n for n in dir(pico_link.PicoLink) if not n.startswith('_')]
    for name in ('last', 'last_value', 'value', 'current'):
        assert name not in api, 'a bare last-value accessor is the S-9 fail-open'


def test_a_link_that_never_opened_reports_stale_rather_than_raising():
    l = pico_link.PicoLink('/dev/does-not-exist', 'missing')
    l.start(port=None)          # SIMULATE_HARDWARE path: opens nothing
    assert l.fresh('E', 5.0) is None
    assert l.is_healthy('E', 5.0) is False
    l.stop()


def test_a_disconnect_mid_stream_leaves_the_link_stale_not_crashed(link):
    port = FakePort([_e(1)], raise_after=1)
    link.start(port=port)
    _drain(link)
    time.sleep(0.1)             # the loop keeps raising on in_waiting
    assert link._thread.is_alive(), 'the reader thread died on a disconnect'
    assert link.fresh('E', 0.01) is None


# --- sequence: the failure a freshness check cannot see --------------------------

def test_a_dropped_frame_is_counted_even_though_the_link_looks_fresh(link):
    for seq in (10, 11, 13, 14):        # 12 never arrived
        link._accept(pico_link.frame('E,%d,0,0,0,0,0,0,0,3300,0' % seq).strip())
    assert link.seq_gaps == 1
    assert link.fresh('E', 5.0) is not None, 'the link is fresh -- that is the point'


def test_the_16_bit_counter_wrapping_is_not_a_gap(link):
    for seq in (0xFFFE, 0xFFFF, 0, 1):
        link._accept(pico_link.frame('E,%d,0,0,0,0,0,0,0,3300,0' % seq).strip())
    assert link.seq_gaps == 0, 'a normal wrap was reported as lost frames'


def test_a_pico_reboot_is_counted_separately_from_a_dropped_frame(link):
    for seq in (500, 501, 0, 1, 2):     # the board restarted its numbering
        link._accept(pico_link.frame('E,%d,0,0,0,0,0,0,0,3300,0' % seq).strip())
    assert link.reboots >= 1, 'a reboot looked like an ordinary gap'


# --- commands --------------------------------------------------------------------

def test_commands_are_sent_bare_and_newline_terminated(link):
    port = FakePort()
    link.start(port=port)
    link.send('PING')
    assert port.written == b'PING\n', 'commands are bare lines, never framed'


def test_send_on_a_dead_link_reports_failure_rather_than_raising():
    l = pico_link.PicoLink('/dev/fake', 'test')
    assert l.send('PING') is False      # never started, no port
    l.stop()


# --- what the consumers do with it: S-9 in practice ------------------------------

def _sonar_with(port):
    link = pico_link.PicoLink('/dev/fake', 'pico_b')
    link.start(port=port)
    array = sensors.SonarArray(link=link)
    return array, link


def test_a_fresh_minus_one_means_clear_not_broken(monkeypatch):
    """The Pico pinged and heard nothing back. For a sensor facing an open room that is
    the truth, and it must not read as an obstacle -- the rover would refuse to move in
    an empty corridor."""
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    array, link = _sonar_with(FakePort([_s(1, ((-1, -1), (-1, -1), (-1, -1)))]))
    _drain(link)
    d = array.distances
    assert d['front'] == config.SONAR_MAX_CM
    assert not array.obstacle_ahead()
    link.stop()


def test_a_stale_link_means_stop_not_clear(monkeypatch):
    """The whole point of S-9. No fresh frame is not a distance -- it is the absence of
    one, and the rover must not drive through it."""
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    monkeypatch.setattr(config, 'SONAR_STALE_S', 0.0)      # everything is stale
    array, link = _sonar_with(FakePort([_s(1, ((1500, 0), (1500, 0), (1500, 0)))]))
    _drain(link)
    d = array.distances
    assert d == {'front': 0.0, 'left': 0.0, 'right': 0.0}
    assert array.obstacle_ahead(), 'a dead link was treated as clear path'
    link.stop()


def test_a_real_distance_is_converted_from_mm_to_cm(monkeypatch):
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    array, link = _sonar_with(FakePort([_s(1, ((1234, 0), (500, 0), (-1, -1)))]))
    _drain(link)
    d = array.distances
    assert d['front'] == pytest.approx(123.4)
    assert d['left'] == pytest.approx(50.0)
    assert d['right'] == config.SONAR_MAX_CM
    link.stop()


def test_one_stale_channel_inside_a_fresh_frame_still_means_stop(monkeypatch):
    """Per-channel ages exist because a frame can be current while one sensor inside it
    has not been updated for a second. A stuck channel must not ride along on its
    neighbours' freshness."""
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    stale_ms = int(config.SONAR_STALE_S * 1000) + 500
    array, link = _sonar_with(FakePort([_s(1, ((1000, 0), (1000, stale_ms), (1000, 0)))]))
    _drain(link)
    d = array.distances
    assert d['front'] == pytest.approx(100.0)
    assert d['left'] == 0.0, 'a channel stale inside a fresh frame read as a distance'
    link.stop()


def test_the_stuck_echo_flag_survives_the_trip(monkeypatch):
    """Bit 2 is the right channel's ECHO stuck high -- the signature of a DESTROYED
    sensor rather than a timeout. Four have died on this rover."""
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    array, link = _sonar_with(FakePort([_s(1, ((1000, 0), (1000, 0), (-1, -1)), flags=4)]))
    _drain(link)
    assert array.flags == 4
    link.stop()


def test_encoder_counts_arrive_against_the_right_wheels(monkeypatch):
    """The $E field order is the as-built J3 landing: lf, lm, rf, rm, lr, rr. Three
    left/right transpositions are on this rover's record."""
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    link = pico_link.PicoLink('/dev/fake', 'pico_a')
    link.start(port=FakePort([_e(1, (11, 22, 33, 44, 55, 66))]))
    enc = sensors.Encoders(link=link)
    _drain(link)
    enc._update()
    assert enc.counts == {'lf': 11, 'lm': 22, 'rf': 33, 'rm': 44, 'lr': 55, 'rr': 66}
    link.stop()


def test_an_encoder_counter_rollover_is_not_a_huge_negative_jump(monkeypatch):
    """The PIO counter is unsigned 32-bit and wraps. Odometry must not see -4 billion."""
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    link = pico_link.PicoLink('/dev/fake', 'pico_a')
    port = FakePort([_e(1, (0xFFFFFFFE,) * 6)])
    link.start(port=port)
    enc = sensors.Encoders(link=link)
    _drain(link); enc._update()
    before = enc.counts['lf']
    port.feed(_e(2, (2,) * 6))              # wrapped past zero
    _drain(link); enc._update()
    after = enc.counts['lf']
    assert (after - before) & 0xFFFFFFFF == 4, 'the wrap was not handled as a wrap'
    link.stop()


def test_a_stale_encoder_link_makes_every_wheel_read_stalled(monkeypatch):
    """The safe direction: stop a rover that has lost sight of its wheels rather than
    drive one blind."""
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)
    monkeypatch.setattr(config, 'ENCODER_STALE_S', 0.0)
    link = pico_link.PicoLink('/dev/fake', 'pico_a')
    link.start(port=FakePort([_e(1, (100,) * 6)]))
    enc = sensors.Encoders(link=link)
    _drain(link)
    assert enc.is_healthy is False
    assert enc.stalled('lf', commanded=True) is True
    link.stop()
