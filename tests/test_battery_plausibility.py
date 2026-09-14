import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config
from sensors import ADC

# Software Design §12 item 13 / Master Hardware Design open item 1.
#
# sensors.py already protects against a FAILED read: the 2026-08-24 change stopped zeroing
# _bat_raw on an exception, because a loose I2C wire had made "the bus hiccupped"
# indistinguishable from "the pack is flat" and Willie powered himself off believing the
# battery was empty.
#
# It does NOT protect against a SUCCESSFUL read of an impossible value. That is the gap this
# covers, and it is not hypothetical: with the battery divider unfed, A0 read 0.0146V, which
# scales to a pack voltage near 0.06V. That read succeeds. It passes straight through the
# guard, walks brain.py's ladder to `shutdown`, and powers the rover off -- from a number that
# is structurally impossible for a connected pack, since the Pi is powered from that same pack
# and would not be executing this code at 0.06V.
#
# The hardware fault was repaired on 2026-09-14. This gap was deliberately left open, because
# the next divider fault would repeat the same silent shutdown.
#
# The fix reuses the machinery that already exists: an implausible reading is treated exactly
# like a failed one -- hold the last good value, mark the reading stale -- so brain.py escalates
# it through SENSOR_FAULT (grace period, visible fault state, operator reset) instead of
# shutting down. No new path, no new state.


@pytest.fixture
def adc(monkeypatch):
    monkeypatch.setattr(config, 'SIMULATE_HARDWARE', False)   # take the real code path
    a = ADC.__new__(ADC)                                      # no bus, no thread
    import threading
    a._bus = None
    a._lock = threading.Lock()
    a._bat_raw = 0
    a._running = False
    a._thread = None
    a._bat_last_ok = 0.0
    a._bat_fail_count = 0
    return a


def _raw_for(volts):
    """The raw ADC count that would produce this pack voltage."""
    return int(volts * config.BATTERY_DIVIDER_SCALE / ADC._LSB)


def test_a_plausible_reading_is_accepted(adc):
    assert adc.accept_battery_raw(_raw_for(11.8)) is True
    assert adc.battery_volts == pytest.approx(11.8, abs=0.05)


def test_a_reading_at_the_shutdown_threshold_is_still_accepted(adc):
    """A genuinely flat pack must still shut the rover down. The floor exists to catch the
    impossible, not the merely bad -- setting it above BAT_SHUTDOWN_V would disable the
    protection this whole ladder exists to provide."""
    assert config.BAT_IMPLAUSIBLE_V < config.BAT_SHUTDOWN_V
    assert adc.accept_battery_raw(_raw_for(config.BAT_SHUTDOWN_V)) is True


def test_the_unfed_divider_reading_is_rejected(adc):
    """The exact number seen on the rover: A0 at 0.0146V, a pack voltage near 0.06V."""
    adc.accept_battery_raw(_raw_for(11.8))          # a good read first
    assert adc.accept_battery_raw(_raw_for(0.06)) is False


def test_a_rejected_reading_holds_the_last_good_value(adc):
    """Same contract as a failed read. Holding beats zeroing: it keeps brain.py's tier ladder
    from seeing a collapse that never happened."""
    adc.accept_battery_raw(_raw_for(11.8))
    adc.accept_battery_raw(_raw_for(0.06))
    assert adc.battery_volts == pytest.approx(11.8, abs=0.05)


def test_sustained_rejection_goes_stale_and_routes_to_sensor_fault(adc):
    """Staleness is what routes this to SENSOR_FAULT instead of the shutdown ladder. Without it
    the rover would hold a stale-but-plausible voltage and carry on as if nothing were wrong --
    a different silent failure, not a fix.

    Note it goes stale rather than becoming stale INSTANTLY, which is deliberate and matches the
    failed-read contract exactly: BAT_ADC_STALE_S exists so a single glitchy reading does not
    raise a fault. What rejection does is stop refreshing the timestamp, so continued rejection
    ages out.
    """
    import time
    adc.accept_battery_raw(_raw_for(11.8))
    assert adc.is_healthy is True

    adc.accept_battery_raw(_raw_for(0.06))
    assert adc.is_healthy is True, 'one rejected read must not fault immediately'

    # age the last-good timestamp past the staleness window, then keep rejecting
    adc._bat_last_ok = time.perf_counter() - config.BAT_ADC_STALE_S - 0.1
    adc.accept_battery_raw(_raw_for(0.06))
    assert adc.is_healthy is False, 'sustained rejection must go stale'
    assert adc.battery_volts == pytest.approx(11.8, abs=0.05), 'and still hold the last good value'


def test_rejection_does_not_refresh_the_last_good_timestamp(adc):
    import time
    adc.accept_battery_raw(_raw_for(11.8))
    adc._bat_last_ok = time.perf_counter()
    before = adc._bat_last_ok
    adc.accept_battery_raw(_raw_for(0.06))
    assert adc._bat_last_ok == before


def test_an_implausible_first_ever_reading_never_becomes_the_value(adc):
    """Boot-time case, and the one that actually bit: there is no last good value to hold, so
    the reading must simply not be adopted. is_healthy is already False at that point, which is
    what keeps brain.py on its held tier rather than acting on a zero."""
    assert adc.accept_battery_raw(_raw_for(0.06)) is False
    assert adc.is_healthy is False
