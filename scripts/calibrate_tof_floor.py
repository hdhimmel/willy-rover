#!/usr/bin/env python3
"""Capture the per-zone floor profile for the SEN0628 (Master Hardware Design §6.5).

Run this ON CLEAR, LEVEL FLOOR, on the surface Willie actually roams. Every later obstacle and
drop decision is measured against what this records, so a capture taken over a rug when he lives
on boards will be wrong in every zone at once.

RE-RUN IT AFTER ANY MECHANICAL CHANGE. The profile is tied to the sensor's exact pose; a bracket
that shifts invalidates it. That failure is loud rather than silent -- a moved sensor produces
phantom obstacles, so he stops for nothing rather than driving into something -- but it is still
a failure, and this is the fix.

    python3 scripts/calibrate_tof_floor.py            # capture, show, ask before saving
    python3 scripts/calibrate_tof_floor.py --show     # show the stored profile, change nothing
"""
import os, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from tof import ToFSensor, FloorProfile, read_frame


def _grid(zones, width=8):
    out = []
    for r in range(0, len(zones), width):
        row = zones[r:r + width]
        out.append(' '.join('  ----' if z is None else f'{z:6.0f}' for z in row))
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--show', action='store_true', help='print the stored profile and exit')
    ap.add_argument('--samples', type=int, default=config.TOF_PROFILE_SAMPLES)
    ap.add_argument('--yes', action='store_true', help='save without asking')
    args = ap.parse_args()

    path = os.path.join(config.WILLY_MEMORY_ROOT, config.TOF_FLOOR_PROFILE_PATH)

    if args.show:
        p = FloorProfile.load(path)
        if p is None:
            print(f'No usable profile at {path}')
            return 1
        print(f'Stored profile ({len(p)} zones), mm:\n{_grid(p.zones)}')
        return 0

    print(f'Capturing {args.samples} frames from {config.TOF_PORT} at {config.TOF_BAUD}.')
    print('The rover must be on CLEAR, LEVEL floor — the surface it actually roams.\n')

    sensor = ToFSensor(source=read_frame, profile_path=path)
    profile = sensor.capture_profile(samples=args.samples)
    if profile is None:
        print('Capture failed: no usable frames. Check the DIP switch is set to UART, the '
              'protective film is off the optics, and the port above is right.')
        return 1

    print(f'Captured, mm:\n{_grid(profile.zones)}\n')
    missing = sum(1 for z in profile.zones if z is None)
    if missing:
        print(f'WARNING: {missing} zone(s) never returned a reading. Those will report NO_DATA '
              f'rather than a guessed baseline — fine if they point past the floor, a problem '
              f'if they should see it.\n')

    # Deliberately not saved by capture_profile(): a bad capture must not overwrite a good
    # profile just because the command ran.
    if not args.yes:
        if input(f'Save to {path}? [y/N] ').strip().lower() not in ('y', 'yes'):
            print('Not saved.')
            return 0
    profile.save(path)
    print(f'Saved. Set ENABLE_TOF=True in config.py once this looks right.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
