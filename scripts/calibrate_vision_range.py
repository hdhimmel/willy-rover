#!/usr/bin/env python3
"""Calibrate vision distance/bearing against known physical distances.

    sudo systemctl stop willy-rover
    ./venv/bin/python scripts/calibrate_vision_range.py --object person
    ./venv/bin/python scripts/calibrate_vision_range.py --show

RUN THIS ON THE ROVER, with a tape measure. It collects paired (true distance, reported
distance) samples and fits the one constant that matters, then tells you what to put in
vision.py. It does NOT write to vision.py itself -- a calibration run with a mis-set object
width would otherwise silently corrupt every later estimate.

WHY THIS EXISTS. vision.py's range and bearing are ESTIMATES from two constants that have never
been measured on this unit (vision.py:19-20):

    _ASSUMED_HFOV_DEG = 70.0     "typical USB webcam-class FOV, not bench-measured"
    _FOCAL_PX_ESTIMATE = 600.0   "rough: focal_px = (frame_w/2) / tan(HFOV/2) at 640px width"

Everything that approaches an object physically -- come_here, follow, retrieve, and the grasp
standoff -- is built on those two numbers. Conservative stopping behaviour does not make them
correct; it only makes the error land in a safer direction most of the time.

CHECK THE CAMERA FIRST. This script refuses to run until you confirm which camera is feeding
detection, because there is a known conflict in the repo: vision.py's constants are commented as
being for the OV9281, while config.CAMERA_DEVICE is /dev/video8, the Arducam, which
config.py:587 records as REAR-facing. Calibrating range for a camera that is not the one looking
where the rover drives is a wasted afternoon, and worse, a confident wrong number.

METHOD. Place a known object at several measured distances across the working range. At each
distance the script records what vision reports. Distance from apparent size is linear in
1/pixel-height, so reported and true distance should be proportional; the fitted ratio is the
correction factor for _FOCAL_PX_ESTIMATE. Bearing is checked separately by placing the object
left and right of centre at a measured offset.
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'experiments', 'results')


def _confirm_camera():
    print('CAMERA CHECK -- answer from what is physically on the rover, not from the config.\n')
    print(f'  config.CAMERA_DEVICE = {config.CAMERA_DEVICE}')
    print('  config.py:587 records /dev/video8 (Arducam) as REAR-facing.')
    print('  vision.py:19-20 constants are commented as being for the OV9281.\n')
    ans = input('Is the camera feeding detection the one pointing where the rover DRIVES? [y/N] ')
    if ans.strip().lower() not in ('y', 'yes'):
        print('\nStop. Fix which camera feeds detection first -- calibrating the wrong one '
              'produces a confident wrong number, which is worse than the current honest '
              'estimate. See config.py CAMERA_DEVICE and vision.py _CAMERA_ID.')
        return False
    return True


def _sample(detector, want_cls, n, settle_s=0.4):
    """Take n detections of want_cls, return (median_distance_cm, median_bearing_deg, count)."""
    dists, bearings = [], []
    for _ in range(n):
        time.sleep(settle_s)
        try:
            dets = detector.detect()
        except Exception as e:
            print(f'    detect() failed: {type(e).__name__}: {e}')
            continue
        hit = next((d for d in dets if getattr(d, 'cls', None) == want_cls), None)
        if hit is None:
            print('    (no detection this frame)')
            continue
        dists.append(getattr(hit, 'distance_cm', None))
        bearings.append(getattr(hit, 'bearing_deg', None))
    dists = [d for d in dists if d is not None]
    bearings = [b for b in bearings if b is not None]
    if not dists:
        return None, None, 0
    return (statistics.median(dists),
            statistics.median(bearings) if bearings else None,
            len(dists))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--object', default='person', help='detector class to place and measure')
    ap.add_argument('--samples', type=int, default=8, help='frames averaged per station')
    ap.add_argument('--show', action='store_true', help='print the last saved calibration')
    args = ap.parse_args()

    path = os.path.join(OUT, 'vision-range-calibration.json')

    if args.show:
        if not os.path.exists(path):
            print('No calibration recorded yet.')
            return 1
        print(json.dumps(json.load(open(path)), indent=2))
        return 0

    if not _confirm_camera():
        return 1

    from vision import ObjectDetector
    detector = ObjectDetector()
    if not getattr(detector, 'available', False):
        print('Detector unavailable -- is the service still running and holding the camera?')
        return 1

    print(f'\nPlace a {args.object} at each distance, centred, then press Enter.')
    print('Blank input finishes. Use a tape measure to the FRONT FACE of the rover.\n')

    samples = []
    while True:
        raw = input('True distance in cm (blank to finish): ').strip()
        if not raw:
            break
        try:
            true_cm = float(raw)
        except ValueError:
            print('  not a number')
            continue
        rep, bearing, n = _sample(detector, args.object, args.samples)
        if rep is None:
            print(f'  no {args.object} detected -- reposition and retry')
            continue
        print(f'  true {true_cm:6.1f} cm  ->  reported {rep:6.1f} cm  '
              f'(bearing {bearing}, n={n})')
        samples.append({'true_cm': true_cm, 'reported_cm': rep, 'bearing_deg': bearing,
                        'frames': n})

    if len(samples) < 3:
        print('\nFewer than 3 stations. Not enough to fit anything; nothing saved.')
        return 1

    ratios = [s['true_cm'] / s['reported_cm'] for s in samples if s['reported_cm']]
    factor = statistics.median(ratios)
    spread = max(ratios) - min(ratios)

    print(f'\n--- {len(samples)} stations ---')
    print(f'  true/reported ratio: median {factor:.3f}, spread {spread:.3f}')
    print(f'  suggested _FOCAL_PX_ESTIMATE = {config and ""}'
          f'{round(600.0 * factor, 1)}   (current 600.0)')
    if spread > 0.25:
        print('\n  WARNING: the ratio is not constant across distance. That is not a focal-length'
              '\n  error -- a wrong focal length scales every reading by the SAME factor. A'
              '\n  varying ratio means the assumed object width is wrong, the detector box is'
              '\n  unstable, or the object was not square to the camera. Do not apply a'
              '\n  correction from this run.')

    os.makedirs(OUT, exist_ok=True)
    payload = {'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'object': args.object, 'samples': samples,
               'ratio_median': factor, 'ratio_spread': spread,
               'suggested_focal_px': round(600.0 * factor, 1),
               'current_focal_px': 600.0,
               'current_assumed_hfov_deg': 70.0,
               'applied': False}
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)
    print(f'\nSaved {path} (applied=false -- edit vision.py by hand after reviewing).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
