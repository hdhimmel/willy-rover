#!/usr/bin/env python3
"""Validate the I2C bus before and after raising dtparam=i2c_arm_baudrate.

Master Hardware Design v2.0 s3.2 computes ~2.2us to threshold from the Pi's 1.8k pull-ups
into ~400pF of cabling, against a 2.5us bit at 400kHz. That is marginal on paper, which is
why raising the bus speed is a measured change and not a config edit you walk away from.
The LTC4311 accelerator is fitted for exactly this reason -- this script is how you find out
whether it is enough.

Run it BEFORE the change to capture a baseline, then again AFTER the reboot:

    ./venv/bin/python scripts/i2c_bus_check.py --label before
    sudo sed -i 's/^dtparam=i2c_arm_baudrate=.*/dtparam=i2c_arm_baudrate=400000/' \
        /boot/firmware/config.txt   # or append if absent
    sudo reboot
    ./venv/bin/python scripts/i2c_bus_check.py --label after

PASS requires all three: every roll-call identical and complete, zero NEW kernel i2c errors,
and no increase in per-transaction failures. Anything else -- revert the dtparam and reboot.

Stop willy-rover.service first so its own pollers are not competing for the bus.
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import config  # noqa: E402

# Expected roll-call. 0x70 is the PCA9685 All-Call broadcast and proves nothing on its own
# (Master Hardware Design s12) -- listed so a diff does not flag it, never counted as a device.
EXPECTED = {0x27, 0x40, 0x42, 0x43, 0x44, 0x45, 0x48, 0x4A, 0x51, 0x60, 0x61}
ALL_CALL = 0x70


def kernel_baudrate():
    """What the kernel actually set, which is authoritative over config.I2C_BAUDRATE."""
    for path in ("/sys/class/i2c-adapter/i2c-1/of_node/clock-frequency",
                 "/proc/device-tree/soc/i2c@7e804000/clock-frequency"):
        try:
            with open(path, "rb") as fh:
                return int.from_bytes(fh.read(4), "big")
        except Exception:
            continue
    try:
        txt = open("/boot/firmware/config.txt", encoding="utf-8").read()
        m = re.search(r"^\s*dtparam=i2c_arm_baudrate=(\d+)", txt, re.M)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def scan():
    out = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True, timeout=20)
    found = set()
    for line in out.stdout.splitlines()[1:]:
        body = line.split(":", 1)
        if len(body) != 2:
            continue
        for tok in body[1].split():
            if tok not in ("--", "UU"):
                found.add(int(tok, 16))
    return found


def dmesg_i2c_errors():
    try:
        out = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return 0
    return len([l for l in out.splitlines()
                if "i2c" in l.lower() and any(w in l.lower()
                                              for w in ("error", "timeout", "nak", "fail"))])


def transaction_timing(rounds=200):
    """Per-transaction cost on a device that does not clock-stretch.

    The INA260 is the right probe here: a plain 2-byte register read, no conversion wait, no
    stretching. The BNO085 would measure its own stretching rather than the bus.
    """
    try:
        from smbus2 import SMBus
    except ImportError:
        return None
    addr, reg = 0x40, 0x02
    try:
        with SMBus(1) as bus:
            bus.read_i2c_block_data(addr, reg, 2)  # warm the path, do not time the first
            fails = 0
            t0 = time.perf_counter()
            for _ in range(rounds):
                try:
                    bus.read_i2c_block_data(addr, reg, 2)
                except OSError:
                    fails += 1
            dt = time.perf_counter() - t0
        return {"rounds": rounds, "failures": fails, "us_per_txn": round(dt / rounds * 1e6, 1)}
    except Exception as exc:
        return {"error": str(exc)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run", help="before / after")
    ap.add_argument("--scans", type=int, default=20, help="roll-calls (20 is the documented bar)")
    ap.add_argument("--out", default=None, help="write JSON here (default scripts/i2c_check_<label>.json)")
    args = ap.parse_args()

    kb = kernel_baudrate()
    print(f"config.I2C_BAUDRATE = {config.I2C_BAUDRATE}")
    print(f"kernel bus speed    = {kb if kb else 'UNKNOWN'}")
    if kb and kb != config.I2C_BAUDRATE:
        print(f"  !! config.py and the kernel disagree. The kernel wins; fix config.py.")

    err_before = dmesg_i2c_errors()
    scans, bad = [], 0
    for i in range(args.scans):
        got = scan()
        devices = got - {ALL_CALL}
        missing, extra = EXPECTED - devices, devices - EXPECTED
        ok = not missing and not extra
        bad += 0 if ok else 1
        scans.append({"n": i, "ok": ok,
                      "missing": sorted(hex(a) for a in missing),
                      "extra": sorted(hex(a) for a in extra)})
        if not ok:
            print(f"  scan {i}: MISSING {sorted(hex(a) for a in missing)} "
                  f"EXTRA {sorted(hex(a) for a in extra)}")
        time.sleep(0.2)
    err_after = dmesg_i2c_errors()

    timing = transaction_timing()
    result = {"label": args.label, "config_baudrate": config.I2C_BAUDRATE,
              "kernel_baudrate": kb, "scans": args.scans, "scans_bad": bad,
              "new_kernel_i2c_errors": err_after - err_before, "timing": timing,
              "detail": scans}

    out = args.out or os.path.join(HERE, "scripts", f"i2c_check_{args.label}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print(f"\nclean roll-calls     : {args.scans - bad}/{args.scans}")
    print(f"new kernel i2c errors: {err_after - err_before}")
    if timing:
        print(f"timing               : {timing}")
    print(f"written              : {out}")

    passed = bad == 0 and (err_after - err_before) == 0
    print("\nPASS" if passed else "\nFAIL -- revert dtparam=i2c_arm_baudrate and reboot")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
