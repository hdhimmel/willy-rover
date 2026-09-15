import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest
import config

# P2 audit. There are TWO places that decide what should be on the I2C bus:
#
#   brain.py::_EXPECTED_I2C    -- the startup self-test, which GATES MOTION
#   diagnostics.py::_EXPECTED_I2C -- the read-only FR-1100-004 report
#
# On 2026-09-14 they disagreed. brain.py added 0x51 (Witty Pi 5) conditionally on
# ENABLE_WITTY_PI, which has been True since the HAT was fitted; diagnostics.py never learned
# about it and expected ten. So `python3 diagnostics.py` reported a clean bus while the self-test
# expected an eleventh device -- and the failure direction is the bad one: diagnostics would say
# "all present" on a rover whose Witty Pi had fallen off the bus.
#
# This is the same ten-versus-eleven drift that had to be removed from three documents the day
# before. In code it is worse, because the two sets are a copy-paste apart and nothing was
# comparing them.
#
# So compare them here, rather than hoping the next person updates both.


def _brain_expected():
    import brain
    return set(brain._EXPECTED_I2C)


def _diagnostics_expected():
    import diagnostics
    return set(diagnostics._EXPECTED_I2C)


def test_the_two_expected_sets_agree():
    """Neither is authoritative over the other -- they must simply never diverge. A device
    missing from diagnostics is one it will never report as absent."""
    brain_set, diag_set = _brain_expected(), _diagnostics_expected()
    only_brain = brain_set - diag_set
    only_diag = diag_set - brain_set
    assert not only_brain, (
        f'brain.py expects {[hex(a) for a in sorted(only_brain)]} and diagnostics.py does not — '
        f'diagnostics would report a clean bus with those devices missing')
    assert not only_diag, (
        f'diagnostics.py expects {[hex(a) for a in sorted(only_diag)]} and brain.py does not')


def test_witty_pi_is_expected_when_enabled():
    """The specific instance that was wrong. ENABLE_WITTY_PI has been True since the HAT was
    fitted, and brain.py:71 keys off it -- diagnostics must follow the same flag, not a
    hard-coded list."""
    if not config.ENABLE_WITTY_PI:
        pytest.skip('ENABLE_WITTY_PI is False; 0x51 is correctly absent from both sets')
    assert config.WITTY_PI_ADDR in _brain_expected()
    assert config.WITTY_PI_ADDR in _diagnostics_expected()


def test_the_all_call_broadcast_is_in_neither():
    """0x70 is the PCA9685 all-call broadcast, not a device. PCA9685.reset() clears MODE1's
    ALLCALL bit during construction, so it legitimately stops answering before either scan runs.
    Expecting it would make every healthy rover fail its own self-test."""
    assert 0x70 not in _brain_expected()
    assert 0x70 not in _diagnostics_expected()


def test_every_expected_address_comes_from_config():
    """No literals. An address written as a number in one file and a config name in the other is
    how these two drifted apart in the first place."""
    from_config = {config.ENCODER_ADDR, config.INA260_5V_ADDR, config.STEER_PCA_ADDR,
                   config.ARM_PCA_ADDR, config.INA260_BUS_12V_ADDR, config.INA260_ARM_6V_ADDR,
                   config.ADS_ADDR, config.IMU_ADDR, config.MOTORKIT_LEFT_ADDR,
                   config.MOTORKIT_RIGHT_ADDR, config.WITTY_PI_ADDR}
    assert _brain_expected() <= from_config
    assert _diagnostics_expected() <= from_config


def test_the_pi_rail_monitor_is_0x45_not_0x44():
    """Pinned because it has been wrong in documentation repeatedly, most recently in the FRD's
    own verification register on 2026-09-13. 0x44 is the +12V main input; 0x45 is the Pi feed.
    They were transposed in the docs until 2026-08-24 and 0x44 moved upstream on 2026-08-28."""
    assert config.INA260_BUS_12V_ADDR == 0x45
    assert config.INA260_ARM_6V_ADDR == 0x44
    assert config.INA260_5V_ADDR == 0x40
