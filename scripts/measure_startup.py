#!/usr/bin/env python3
"""Measure real startup time and tick timing, to derive TimeoutStartSec and WatchdogSec.

    ./venv/bin/python scripts/measure_startup.py --runs 5

RUN THIS ON THE ROVER. It produces the two numbers that willy-rover-watchdog.service needs and
that nobody currently has. Do not guess them: the 2026-09-07 outage was caused by a WatchdogSec
value chosen without measurement (500ms, against a startup that loads a 1.7GB Hailo HEF), and
the rover was SIGABRTed four times in twenty seconds, never reaching its own first log line.

WHAT IT MEASURES

  startup   wall time from process launch to the point brain.py sends READY=1. Under Type=notify
            this is also systemd's START deadline, so TimeoutStartSec must exceed the WORST of
            these, not the median -- a cold page cache, a slow HEF load or a retried I2C probe
            all land on the tail.

  tick      the interval between WATCHDOG=1 heartbeats once running. WatchdogSec must exceed the
            worst tick gap with real margin, because systemd kills on the first missed deadline.

HOW IT AVOIDS TOUCHING THE LIVE SERVICE. It launches main.py as a child process with its own
NOTIFY_SOCKET pointing at a socket this script owns, so it observes exactly the messages systemd
would receive, without installing a unit, without systemctl, and without disturbing a running
rover. Stop the real service first if it holds the hardware: `sudo systemctl stop willy-rover`.

The suggested values it prints are a starting point derived from the measurement, not a
recommendation to deploy. Bench-test repeated restarts before arming anything -- see
docs/WildWilly_Bench_Test_Procedures.md, procedure W-1.
"""
import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def one_run(timeout_s, settle_s):
    """Launch main.py with a notify socket we own. Returns (ready_s, [tick_gaps])."""
    tmp = tempfile.mkdtemp(prefix='willy-notify-')
    sock_path = os.path.join(tmp, 'notify.sock')
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.settimeout(timeout_s)

    env = dict(os.environ)
    env['NOTIFY_SOCKET'] = sock_path
    env['PYTHONUNBUFFERED'] = '1'
    env.setdefault('PYTHONPATH', REPO)

    t0 = time.perf_counter()
    proc = subprocess.Popen([sys.executable, os.path.join(REPO, 'main.py')],
                            cwd=REPO, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ready = None
    beats = []
    try:
        while True:
            try:
                msg = srv.recv(64)
            except socket.timeout:
                break
            now = time.perf_counter()
            if msg == b'READY=1' and ready is None:
                ready = now - t0
                srv.settimeout(5.0)          # heartbeats should be frequent once running
            elif msg == b'WATCHDOG=1':
                beats.append(now)
            if ready is not None and now - t0 > ready + settle_s:
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        srv.close()
        try:
            os.unlink(sock_path)
            os.rmdir(tmp)
        except OSError:
            pass

    gaps = [b - a for a, b in zip(beats, beats[1:])]
    return ready, gaps


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--runs', type=int, default=5,
                    help='repeat count; the TAIL is what matters, so do not use 1')
    ap.add_argument('--timeout', type=float, default=180.0,
                    help='give up waiting for READY=1 after this many seconds')
    ap.add_argument('--settle', type=float, default=20.0,
                    help='seconds of heartbeats to record after READY=1')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    print(f'{args.runs} runs. Stop the live service first if it holds the hardware.\n')
    readies, all_gaps, failures = [], [], 0

    for i in range(args.runs):
        ready, gaps = one_run(args.timeout, args.settle)
        if ready is None:
            failures += 1
            print(f'  run {i + 1}: NO READY=1 within {args.timeout}s '
                  f'-- startup failed or never notified')
            continue
        readies.append(ready)
        all_gaps.extend(gaps)
        worst = max(gaps) if gaps else float('nan')
        print(f'  run {i + 1}: ready in {ready:6.2f}s, {len(gaps)} heartbeats, '
              f'worst gap {worst:.3f}s')

    if not readies:
        print('\nNo successful startup measured. Nothing can be derived; do not install a '
              'watchdog unit on this basis.')
        return 1

    worst_ready = max(readies)
    worst_gap = max(all_gaps) if all_gaps else None

    # Deliberately generous multipliers. systemd kills on the FIRST missed deadline, there is no
    # second chance, and the cost of a too-large value is a slower fault detection while the cost
    # of a too-small one is a rover that cannot boot.
    suggested_start = max(60, int(worst_ready * 3 + 30))
    suggested_watchdog = round(worst_gap * 10, 1) if worst_gap else None

    print(f'\n--- measured over {len(readies)} successful run(s) ---')
    print(f'  startup  min {min(readies):6.2f}s  median {statistics.median(readies):6.2f}s  '
          f'WORST {worst_ready:6.2f}s')
    if worst_gap:
        print(f'  tick gap median {statistics.median(all_gaps):.3f}s  WORST {worst_gap:.3f}s  '
              f'(n={len(all_gaps)})')
    if failures:
        print(f'  FAILURES: {failures} run(s) never sent READY=1 -- investigate before '
              f'deriving anything from the rest')

    print('\n--- starting points for willy-rover-watchdog.service, NOT a clearance to deploy ---')
    print(f'  TimeoutStartSec={suggested_start}')
    if suggested_watchdog:
        print(f'  WatchdogSec={suggested_watchdog}s')
        print(f'\n  The watchdog figure is 10x the worst observed tick gap. Check that against')
        print(f'  config.TICK_OVERRUN_THRESHOLD_S before using it: a WatchdogSec BELOW the tick')
        print(f'  overrun threshold means systemd kills the process before the application has')
        print(f'  logged that it was running slow, which destroys the evidence for why.')
    print('\n  Then run procedure W-1 in docs/WildWilly_Bench_Test_Procedures.md: repeated')
    print('  restarts with the unit installed but the rover on blocks, before any live use.')

    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'readies': readies, 'gaps': all_gaps, 'failures': failures,
                       'worst_ready_s': worst_ready, 'worst_gap_s': worst_gap,
                       'suggested_timeout_start_s': suggested_start,
                       'suggested_watchdog_s': suggested_watchdog}, f, indent=2)
        print(f'\nArtifact: {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
