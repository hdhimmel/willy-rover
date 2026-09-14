import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config
from sensors import SonarArray

# Master Hardware Design §6.5 / Software Design §6.5. The ToF fuses in at ONE point --
# SonarArray.distances() -- and 'front' becomes the minimum of the sonar reading and the nearest
# ToF zone reporting an obstacle.
#
# min() is the whole design. Whichever sensor sees something closer wins, which is fail-safe by
# construction: no arbitration logic, no new FSM state, no threshold changes. DIST_STOP,
# DIST_SLOW, DIST_CLEAR, _roam(), _slow() and _avoid() all keep working against the same dict
# key and never learn the ToF exists.
#
# ALONGSIDE THE SONAR, NEVER REPLACING IT. The two are blind to different things: sonar misses
# chair legs, soft furnishings and angled surfaces; ToF looks straight THROUGH glass, which
# sonar reflects off perfectly well. A test below pins that, because "the ToF is better, drop
# the sonar" is the plausible-sounding change that would quietly remove glass detection.


class _FakeSonar:
    def __init__(self, d): self.distance = d
    def update(self): pass


class _FakeToF:
    def __init__(self, cm=None, available=True):
        self._cm = cm; self.available = available
    def nearest_obstacle_cm(self): return self._cm
    def drop_detected(self): return False


@pytest.fixture
def array():
    a = SonarArray.__new__(SonarArray)
    a.front = _FakeSonar(100.0)
    a.left = _FakeSonar(100.0)
    a.right = _FakeSonar(100.0)
    a._sensors = [a.front, a.left, a.right]
    a._running = False
    a._thread = None
    a.tof = None
    return a


def test_without_a_tof_front_is_the_sonar_reading(array):
    assert array.distances['front'] == pytest.approx(100.0)


def test_the_tof_wins_when_it_sees_something_closer(array):
    array.tof = _FakeToF(cm=30.0)
    assert array.distances['front'] == pytest.approx(30.0)


def test_the_sonar_wins_when_it_sees_something_closer(array):
    """The case that matters for glass: ToF looks straight through a patio door, sonar does not.
    If the ToF's 'nothing there' could override a real sonar return, adding this sensor would
    have made him blind to glass."""
    array.front.distance = 25.0
    array.tof = _FakeToF(cm=90.0)
    assert array.distances['front'] == pytest.approx(25.0)


def test_a_tof_reporting_no_obstacle_never_raises_the_front_distance(array):
    """None means 'nothing to report', not 'the way is clear'. Treating it as a distance would
    let an uncalibrated or unavailable sensor mask a real sonar obstacle."""
    array.front.distance = 15.0
    array.tof = _FakeToF(cm=None)
    assert array.distances['front'] == pytest.approx(15.0)


def test_an_unavailable_tof_degrades_to_sonar_alone(array):
    """§6.5: adding a sensor must never lower the rover's availability floor."""
    array.tof = _FakeToF(cm=None, available=False)
    assert array.distances['front'] == pytest.approx(100.0)


def test_a_raising_tof_does_not_take_out_the_tick(array):
    """distances() is called from the 20Hz tick. An exception here would stop obstacle checks
    entirely -- strictly worse than having no ToF at all."""
    class _Exploding:
        available = True
        def nearest_obstacle_cm(self): raise IOError('uart dropped')
        def drop_detected(self): raise IOError('uart dropped')
    array.tof = _Exploding()
    assert array.distances['front'] == pytest.approx(100.0)


def test_the_tof_never_affects_the_side_distances(array):
    """It is a FRONT sensor. The left/right sonars are the only side coverage there is."""
    array.tof = _FakeToF(cm=10.0)
    d = array.distances
    assert d['left'] == pytest.approx(100.0)
    assert d['right'] == pytest.approx(100.0)
