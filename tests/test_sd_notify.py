import os
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import pytest

# SOFTWARE VERIFICATION of the sd_notify path. This is the half of the watchdog work that can be
# proven without the rover, and it is deliberately separated from the bench procedure in
# docs/WildWilly_Bench_Test_Procedures.md, which needs real hardware and real measured timings.
#
# WHAT WENT WRONG BEFORE (FRD v3.1 G-5, 2026-09-07): WatchdogSec=500ms was installed on a unit
# that was Type=simple. NotifyAccess then defaults to `none`, so systemd DISCARDED every message
# the process sent -- WATCHDOG=1 was never received by anything and no heartbeat rate could have
# satisfied the deadline. The rover was killed by SIGABRT ~500ms after every start, four times in
# twenty seconds, never reaching its own first log line.
#
# Nothing here can catch that, because the failure was in the unit file rather than in this code.
# What these tests DO establish is that the sending side is correct and safe, so that when the
# unit is fixed the only remaining unknowns are the measured timings:
#
#   - the messages are exactly the two strings systemd expects
#   - the notifier is inert when NOTIFY_SOCKET is unset (running from a shell, or under pytest)
#   - a broken or absent socket never raises into the tick loop
#   - the abstract-namespace socket form systemd actually uses is handled
#
# That last one matters: systemd passes NOTIFY_SOCKET as "@/org/freedesktop/systemd1/notify" for
# an abstract socket, and the leading '@' must become a NUL byte or the sendto silently targets a
# filesystem path that does not exist.


def _notifier(monkeypatch, addr):
    """Build a _SdNotify with NOTIFY_SOCKET set (or not) at construction time."""
    if addr is None:
        monkeypatch.delenv('NOTIFY_SOCKET', raising=False)
    else:
        monkeypatch.setenv('NOTIFY_SOCKET', addr)
    import brain
    return brain._SdNotify()


def test_it_is_inert_when_not_running_under_systemd(monkeypatch):
    """The normal case for every developer run and this whole test suite. Constructing a socket
    would be wasted; sending would be an error."""
    n = _notifier(monkeypatch, None)
    assert n._sock is None
    n.notify('READY=1')          # must be a silent no-op, not an exception
    n.notify('WATCHDOG=1')


def test_a_filesystem_socket_receives_the_exact_messages(monkeypatch):
    """The wire format is not ours to improvise: systemd matches these strings exactly."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'notify.sock')
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        srv.bind(path)
        srv.settimeout(2.0)
        try:
            n = _notifier(monkeypatch, path)
            assert n._sock is not None, 'no socket created despite NOTIFY_SOCKET being set'
            n.notify('READY=1')
            assert srv.recv(64) == b'READY=1'
            n.notify('WATCHDOG=1')
            assert srv.recv(64) == b'WATCHDOG=1'
        finally:
            srv.close()


def test_the_abstract_namespace_form_is_translated(monkeypatch):
    """systemd hands over "@/org/freedesktop/systemd1/notify" for an abstract socket. The leading
    '@' must become a NUL byte; leaving it would address a filesystem path that does not exist,
    and the failure would be silent -- which is precisely the shape of the 2026-09-07 outage."""
    if not hasattr(socket, 'AF_UNIX'):
        pytest.skip('AF_UNIX unavailable')
    name = '@willy-test-notify-abstract'
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        srv.bind('\0' + name[1:])
    except OSError:
        pytest.skip('abstract unix sockets unavailable on this platform')
    srv.settimeout(2.0)
    try:
        n = _notifier(monkeypatch, name)
        assert n._addr.startswith('\0'), 'abstract socket address was not translated'
        n.notify('READY=1')
        assert srv.recv(64) == b'READY=1'
    finally:
        srv.close()


def test_a_dead_socket_never_raises_into_the_tick_loop(monkeypatch):
    """notify('WATCHDOG=1') is called from _tick() at 20Hz. An OSError escaping here would take
    down the control loop over a failed heartbeat -- strictly worse than having no watchdog, and
    exactly the wrong direction for a mechanism whose whole purpose is surviving faults."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'gone.sock')
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        srv.bind(path)
        n = _notifier(monkeypatch, path)
        srv.close()
        os.unlink(path)          # receiver vanishes, as on a systemd restart
        n.notify('WATCHDOG=1')   # must not raise
        for _ in range(50):
            n.notify('WATCHDOG=1')


def test_ready_is_sent_even_when_the_self_test_fails():
    """Source-level check of an important design choice. brain.py sends READY=1 on BOTH the
    pass and fail branches of the startup self-test.

    Under Type=notify that is what keeps a failed self-test from becoming a failed START: the
    rover comes up degraded with motion disabled and stays up, rather than being restarted in a
    loop by systemd. A future change that moved READY=1 inside the success branch would turn a
    recoverable degraded state into a crash loop on a rover that cannot see its own sensors."""
    import inspect
    import brain
    # start(), not __init__ -- the self-test and the READY=1 that follows it both live there.
    src = inspect.getsource(brain.RoverBrain.start)
    i = src.index("Startup self-test FAILED")
    tail = src[i:]
    assert "READY=1" in tail, (
        'READY=1 is no longer reachable after a failed self-test; under Type=notify that makes a '
        'degraded rover a failed start, and systemd will restart-loop it')


def test_the_heartbeat_is_sent_from_the_tick_loop():
    """WATCHDOG=1 must come from _tick(), not a helper thread. A heartbeat sent from anywhere
    else would keep reassuring systemd while the control loop itself was wedged -- which is the
    one failure the watchdog exists to catch."""
    import inspect
    import brain
    src = inspect.getsource(brain.RoverBrain._tick)
    assert "WATCHDOG=1" in src
