import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config
from sensors import SonarArray

# FRD gap audit, 2026-10-01 (FR-800-004). SonarArray.is_healthy existed but brain.py never called it: a stale Pico B link read
# 0.0 on every channel with no fault raised, and ROAM -> AVOID reversed blind on a loop.


class _Link:
    def __init__(self, ok): self.ok = ok; self.asked = None
    def is_healthy(self, kind, max_age_s):
        self.asked = (kind, max_age_s); return self.ok


@pytest.fixture
def sonar():
    a = SonarArray.__new__(SonarArray)
    a._owns_link = False; a.tof = None
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, 'SIMULATE_HARDWARE', False)
        yield a


def test_a_fresh_s_frame_is_healthy(sonar):
    sonar._link = _Link(True)
    assert sonar.is_healthy is True
    assert sonar._link.asked == ('S', config.SONAR_STALE_S)


def test_a_stale_link_is_unhealthy(sonar):
    sonar._link = _Link(False)
    assert sonar.is_healthy is False
