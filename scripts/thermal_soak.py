#!/usr/bin/env python3
"""Sample temperature, clock and throttle state under sustained load.

Why this exists: `vcgencmd get_throttled` was measured at 0x0 and recorded as a PASS in
Master Hardware Design v2.0 s13 -- but at idle. A Pi 5 with an AI HAT+ 2 throttles under
sustained inference, not sitting still, and throttling is the failure mode that makes
everything slower without anything looking broken.

*** READ THIS BEFORE RUNNING WITH --workers 4 ***

Loading all four cores is the exact condition that browned this rover out. config.py's
WHISPER_CPU_THREADS=3 exists because faster-whisper taking all 4 cores dipped EXT5V past the
Witty Pi cutoff and hard-powered-off the Pi mid-utterance, reproducibly. That is a power
fault, not a thermal one, and this script cannot prevent it.

So the default is --workers 3, which matches the real workload. --workers 4 tells you what
the rail does at full tilt and may power the rover off. Do it on the bench, not mid-task,
and watch the 5V INA260 (0x40) while it runs.

    ./venv/bin/python scripts/thermal_soak.py --minutes 10
    ./venv/bin/python scripts/thermal_soak.py --minutes 10 --workers 4   # may power-off

Stop willy-rover.service first unless you are deliberately measuring it under service load.
"""
import argparse, json, multiprocessing as mp, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# get_throttled bit meanings. The low nibble is live state; bits 16+ are sticky since boot,
# which is why a 0x0 reading only means something if you know when it was last cleared.
THROTTLE_BITS = [
    (0,  "under-voltage NOW"),
    (1,  "arm frequency capped NOW"),
    (2,  "currently throttled"),
    (3,  "soft temperature limit NOW"),
    (16, "under-voltage HAS occurred"),
    (17, "arm frequency capping HAS occurred"),
    (18, "throttling HAS occurred"),
    (19, "soft temperature limit HAS occurred"),
]


def vcgencmd(*args):
    try:
        out = subprocess.run(["vcgencmd", *args], capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:
        return ""


def temp_c():
    raw = vcgencmd("measure_temp")
    m = re.search(r"([\d.]+)", raw)
    if m:
        return float(m.group(1))
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as fh:
            return int(fh.read().strip()) / 1000.0
    except Exception:
        return None


def arm_mhz():
    m = re.search(r"=(\d+)", vcgencmd("measure_clock", "arm"))
    return int(m.group(1)) / 1e6 if m else None


def throttled_word():
    m = re.search(r"=0x([0-9a-fA-F]+)", vcgencmd("get_throttled"))
    return int(m.group(1), 16) if m else None


def decode(word):
    if not word:
        return []
    return [name for bit, name in THROTTLE_BITS if word & (1 << bit)]


def burn(stop_at):
    """Integer-heavy spin. Deliberately not numpy -- this is meant to look like CPython
    under faster-whisper, not like a vectorised BLAS kernel with different thermal behaviour."""
    x = 0
    while time.time() < stop_at:
        for i in range(200000):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--workers", type=int, default=3,
                    help="3 matches WHISPER_CPU_THREADS; 4 may brown out the 5V rail")
    ap.add_argument("--interval", type=float, default=5.0, help="sample seconds")
    ap.add_argument("--idle", action="store_true", help="sample without loading anything")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.workers >= 4 and not args.idle:
        print("!! --workers 4: this is the condition that hard-powered-off this rover")
        print("!! (config.py WHISPER_CPU_THREADS=3). Watch INA260 0x40. Ctrl-C to abort.")
        time.sleep(5)

    start = time.time()
    stop_at = start + args.minutes * 60
    baseline = throttled_word()
    print(f"baseline get_throttled = 0x{baseline:x}" if baseline is not None else "baseline unknown")
    for name in decode(baseline):
        print(f"  sticky already set: {name}")

    procs = []
    if not args.idle:
        for _ in range(max(1, args.workers)):
            p = mp.Process(target=burn, args=(stop_at,), daemon=True)
            p.start()
            procs.append(p)
        print(f"loading {len(procs)} worker(s) for {args.minutes:g} min")
    else:
        print(f"idle sampling for {args.minutes:g} min")

    samples, peak_t, worst = [], 0.0, baseline or 0
    try:
        while time.time() < stop_at:
            t, mhz, word = temp_c(), arm_mhz(), throttled_word()
            if t:
                peak_t = max(peak_t, t)
            if word:
                worst |= word
            row = {"t": round(time.time() - start, 1), "temp_c": t,
                   "arm_mhz": mhz, "throttled": f"0x{word:x}" if word is not None else None}
            samples.append(row)
            flags = decode(word)
            print(f"  {row['t']:7.1f}s  {t if t else '?':>5}C  {mhz if mhz else '?':>6} MHz  "
                  f"0x{word:x}{'  <-- ' + ', '.join(flags) if flags else ''}"
                  if word is not None else f"  {row['t']:7.1f}s  (vcgencmd unavailable)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\naborted")
    finally:
        for p in procs:
            p.terminate()

    result = {"minutes": args.minutes, "workers": 0 if args.idle else args.workers,
              "baseline_throttled": f"0x{baseline:x}" if baseline is not None else None,
              "peak_temp_c": peak_t, "accumulated_throttled": f"0x{worst:x}",
              "flags": decode(worst), "samples": samples}
    out = args.out or os.path.join(HERE, "scripts",
                                   f"thermal_soak_{int(start)}_{result['workers']}w.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print(f"\npeak temp            : {peak_t}C")
    print(f"accumulated throttled: 0x{worst:x}")
    for name in decode(worst):
        print(f"  {name}")
    print(f"written              : {out}")

    newly = decode(worst)
    was = set(decode(baseline))
    regressions = [f for f in newly if f not in was]
    if regressions:
        print("\nFAIL -- new during this run:")
        for r in regressions:
            print(f"  {r}")
        return 1
    print("\nPASS -- no new throttle or under-voltage flags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
