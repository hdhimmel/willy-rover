import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config
from tof import FloorProfile, ToFSensor, OBSTACLE, FLOOR, DROP, NO_DATA

# FR-1000-002 / FR-1200-005. Master Hardware Design §6.5, Software Design §6.5/§6.6.
#
# The SEN0628 returns 64 distances. Turning those into "obstacle" / "floor" / "drop" is the
# whole job, and it is pure arithmetic over a frame -- so the frame source is injected and every
# rule here is tested without a sensor, a UART, or a rover.
#
# THE CENTRAL DESIGN POINT, and the thing most likely to be "simplified" later: the floor is
# ALWAYS in view, and it is SUBTRACTED, not masked.
#
# Masking the bottom rows is the obvious fix and the wrong one. Mounted around 20cm the floor
# first appears about 34cm out (60 degrees vertical -> ~1.7x mount height), which is inside
# DIST_SLOW -- so the rows a mask would discard are exactly where a shoe or a cable at close
# range shows up. A per-zone floor profile keeps those zones useful: a zone counts as an
# obstacle only when it returns MEANINGFULLY SHORTER than its own stored floor distance.
#
# And the inverse gives cliff detection for free, which matters because dedicated cliff sensors
# were dropped on 2026-09-12 -- the chassis extends past the body, so nothing can be mounted
# ahead of the front wheels. A zone returning nothing where the profile expects floor is a drop.


def _frame(value=1000.0, n=64):
    """A flat frame of millimetre readings."""
    return [float(value)] * n


@pytest.fixture
def profile():
    # floor at 1000mm in every zone -- a deliberately simple baseline so each test's deviation
    # from it is the only thing in play
    return FloorProfile(_frame(1000.0))


@pytest.fixture
def tof(profile):
    s = ToFSensor(source=lambda: _frame(1000.0))
    s.profile = profile
    return s


# --- classification -----------------------------------------------------------------

def test_a_zone_matching_its_floor_profile_is_floor(profile):
    assert profile.classify(0, 1000.0) == FLOOR


def test_a_zone_well_short_of_its_floor_is_an_obstacle(profile):
    assert profile.classify(0, 400.0) == OBSTACLE


def test_a_zone_returning_nothing_where_floor_is_expected_is_a_drop(profile):
    """Cliff detection. The SEN0628 reports no target as an out-of-range value; open space past
    a stair nosing produces exactly that where the profile says floor should be."""
    assert profile.classify(0, None) == DROP


def test_a_zone_much_further_than_its_floor_is_a_drop(profile):
    assert profile.classify(0, 3000.0) == DROP


def test_a_small_deviation_is_still_floor(profile):
    """Carpet pile, a rug edge, a few mm of ride height. Without a margin every surface change
    reads as an obstacle and he never moves."""
    assert profile.classify(0, 1000.0 - config.TOF_FLOOR_MARGIN_MM * 0.5) == FLOOR
    assert profile.classify(0, 1000.0 + config.TOF_FLOOR_MARGIN_MM * 0.5) == FLOOR


# --- uncalibrated must report nothing ------------------------------------------------

def test_an_uncalibrated_sensor_reports_no_data_not_raw_ranges():
    """Software Design §6.5. Defaulting to raw would make the floor a permanent obstacle and
    immobilise the rover on the first boot after a rebuild -- the exact failure the profile
    exists to prevent, reintroduced through the default."""
    s = ToFSensor(source=lambda: _frame(1000.0))
    assert s.profile is None
    assert s.nearest_obstacle_cm() is None
    assert s.classify_frame() == []


def test_an_uncalibrated_sensor_reports_no_drop_either():
    s = ToFSensor(source=lambda: _frame(1000.0))
    assert s.drop_detected() is False


# --- nearest obstacle, which is what fuses into distances() ---------------------------

def test_nearest_obstacle_ignores_zones_reading_as_floor(tof):
    assert tof.nearest_obstacle_cm() is None, 'a clear floor is not an obstacle'


def test_nearest_obstacle_returns_the_closest_obstacle_zone(tof):
    f = _frame(1000.0)
    f[10] = 600.0
    f[20] = 300.0          # the nearest real obstacle
    tof.source = lambda: f
    assert tof.nearest_obstacle_cm() == pytest.approx(30.0, abs=0.5)


def test_a_drop_zone_is_not_reported_as_an_obstacle(tof):
    """A drop is further away, not closer. Reporting it as an obstacle would make him stop at
    the top of the stairs for the right reason by pure accident, and drive into a wall for the
    wrong one."""
    f = _frame(1000.0)
    f[5] = None
    tof.source = lambda: f
    assert tof.nearest_obstacle_cm() is None
    assert tof.drop_detected() is True


# --- availability ---------------------------------------------------------------------

def test_a_failing_source_reports_unavailable_rather_than_raising(tof):
    """§6.5: adding a sensor must never lower the rover's availability floor. sensors.py falls
    back to sonar alone when this returns None, so a raise here would take out the tick."""
    def boom(): raise IOError('uart dropped')
    tof.source = boom
    assert tof.nearest_obstacle_cm() is None
    assert tof.available is False


def test_availability_recovers_when_the_source_does(tof):
    def boom(): raise IOError('uart dropped')
    tof.source = boom
    tof.nearest_obstacle_cm()
    assert tof.available is False
    tof.source = lambda: _frame(1000.0)
    tof.nearest_obstacle_cm()
    assert tof.available is True


def test_a_wrong_sized_frame_is_refused(tof):
    """A short frame means a desynchronised UART, not a very close obstacle. Zone N in a
    63-value frame is not zone N."""
    tof.source = lambda: _frame(1000.0, n=32)
    assert tof.nearest_obstacle_cm() is None
    assert tof.available is False


# --- profile persistence ----------------------------------------------------------------

def test_a_profile_round_trips_through_disk(tmp_path):
    p = FloorProfile(_frame(1234.0))
    path = tmp_path / 'floor.json'
    p.save(str(path))
    again = FloorProfile.load(str(path))
    assert again is not None
    assert again.classify(0, 1234.0) == FLOOR


def test_loading_a_missing_profile_returns_none_rather_than_raising(tmp_path):
    assert FloorProfile.load(str(tmp_path / 'nope.json')) is None


def test_a_profile_of_the_wrong_size_is_refused(tmp_path):
    """A profile captured against a different zone count cannot be mapped onto this frame, and
    silently using it would mean every zone compared against the wrong baseline."""
    path = tmp_path / 'floor.json'
    path.write_text(json.dumps({'zones': [1000.0] * 16}))
    assert FloorProfile.load(str(path)) is None


def test_capturing_a_profile_averages_several_frames(tmp_path):
    """One frame carries per-zone noise straight into the baseline, and the baseline is what
    every later comparison is measured against."""
    frames = [_frame(1000.0), _frame(1010.0), _frame(990.0)]
    it = iter(frames)
    s = ToFSensor(source=lambda: next(it))
    p = s.capture_profile(samples=3)
    assert p is not None
    assert p.classify(0, 1000.0) == FLOOR
