import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# diagnostics.py computed its PASS/FAIL verdict AFTER stopping every sensor thread, then asked
# each sensor whether it was healthy. `is_healthy` is a STALENESS flag -- (perf_counter() -
# last_ok) < window, where the window is 0.5s for the IMU and 1.0s for encoders and the current
# monitor -- and it is kept fresh by each sensor's own thread. Once those threads are stopped,
# nothing refreshes it.
#
# Measured on the rover 2026-09-16: the stop sequence takes 1.147s against the IMU's 0.5s window.
#
#     BEFORE stop():  imu=True   encoders=True  current=True
#     AFTER  stop():  imu=False  encoders=True  current=True
#
# So `ok` read imu.is_healthy as False every time, and diagnostics.py COULD NOT PRINT PASS on any
# hardware in any state -- while printing "IMU healthy=True" four lines above, from that same
# property. It returns exit 1 on FAIL, so anything gating on this tool saw a permanent failure.
#
# This is the second bug of its kind in this file (2026-09-14: it expected ten I2C devices where
# brain.py expected eleven, so it reported a clean bus on a rover that had lost one). Both share
# a shape worth naming: THE TOOL WAS WRONG, NOT THE ROVER. A diagnostic that cries wolf is worse
# than no diagnostic, because the next real fault is the one nobody believes -- and on 2026-09-16
# there WAS a real fault sitting underneath this one (all three sonars dead) that the FAIL told
# nobody anything about.
#
# Static inspection rather than execution: diagnostics.py imports `board` and `busio` at module
# scope with no simulate branch, so it cannot be imported on a machine without Blinka, and
# scan_i2c() talks to a real bus even under WILLY_SIMULATE. The property being pinned is
# structural anyway -- WHERE the flags are read, not what they return.

_DIAG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "diagnostics.py")


def _source():
    with open(_DIAG, encoding="utf-8") as f:
        return f.read()


def _lines():
    return _source().split("\n")


def _index_of(pred, what):
    for i, line in enumerate(_lines()):
        if pred(line):
            return i
    raise AssertionError("could not find %s in diagnostics.py" % what)


def test_no_health_flag_is_read_after_the_threads_are_stopped():
    """The core defect: reading .is_healthy after stop() measures the shutdown, not the rover."""
    stop_i = _index_of(lambda l: ".stop();" in l and "sonars.stop()" in l, "the stop() line")
    after = _lines()[stop_i + 1:]
    offenders = [(stop_i + 2 + n, l) for n, l in enumerate(after)
                 if ".is_healthy" in l and not l.strip().startswith("#")]
    assert not offenders, (
        "diagnostics.py reads .is_healthy AFTER stopping the sensor threads, which is the bug "
        "this test exists for -- the value reflects how long shutdown took, not the hardware. "
        "Capture the flag into a local BEFORE the stop() line and use that. Offending lines: %r"
        % offenders)


def test_the_verdict_is_built_from_captured_locals():
    """`ok` must be composed of the pre-stop captures, not live property reads."""
    src = _source()
    m = re.search(r"\n\s*ok=\((.*?)\)\n", src, re.S)
    assert m, "could not find the ok=(...) verdict expression"
    expr = m.group(1)
    for name in ("imu_healthy", "adc_healthy", "encoders_healthy", "current_healthy"):
        assert name in expr, "verdict must use the captured %s local; got: %r" % (name, expr)
    assert ".is_healthy" not in expr, (
        "verdict still reads a live .is_healthy property: %r" % expr)


def test_every_captured_flag_is_read_before_the_stop_line():
    """Guards the other direction -- a capture that drifts below stop() is the same bug again."""
    lines = _lines()
    stop_i = _index_of(lambda l: ".stop();" in l and "sonars.stop()" in l, "the stop() line")
    for name, expected in (("imu_healthy", "imu.is_healthy"),
                           ("encoders_healthy", "encoders.is_healthy"),
                           ("current_healthy", "current.is_healthy"),
                           ("adc_healthy", "adc.battery_volts")):
        cap = _index_of(lambda l, n=name, e=expected: l.strip().startswith(n + "=") and e in l,
                        "the %s capture" % name)
        assert cap < stop_i, (
            "%s is captured at line %d, AFTER the stop() line at %d -- that reintroduces the bug"
            % (name, cap + 1, stop_i + 1))


def test_printed_health_and_verdict_health_are_the_same_values():
    """The symptom that made this so confusing: it printed healthy=True and then failed on it.

    Whatever the verdict uses must be what the operator was shown. If these ever diverge again,
    the tool is lying to the person reading it, which is worse than being wrong quietly."""
    src = _source()
    assert "healthy={imu_healthy}" in src, "the IMU line must print the captured local"
    assert "healthy={encoders_healthy}" in src, "the encoder line must print the captured local"
    assert "healthy={current_healthy}" in src, "the current line must print the captured local"
    assert "healthy={imu.is_healthy}" not in src, "IMU line still prints a live property read"
