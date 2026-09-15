#!/usr/bin/env python3
"""Talk to the SEN0628 over UART and print what comes back (Master Hardware Design §6.5, T-1).

This exists because the SEN0628's wire format was unknown, and finding it out cost most of
2026-09-15. Everything learned that day is encoded here so the next person -- or the next
sensor -- does not repeat it.

    ./venv/bin/python scripts/tof_probe.py            # SETMODE 8x8, then poll 15 frames
    ./venv/bin/python scripts/tof_probe.py --listen   # passive only; proves it does NOT stream
    ./venv/bin/python scripts/tof_probe.py -n 60      # longer run, for the stability bar

THE FOUR THINGS THAT WASTED A DAY, so they are not re-derived:

1. THE SENSOR DOES NOT STREAM. It is strictly request/response. 30 seconds of passive
   listening on a powered, correctly-wired sensor returns zero bytes -- which looks exactly
   like dead hardware and is not. `--listen` reproduces that on purpose.

2. BOTH UART WIRES ARE REQUIRED. CLAUDE.md said "only RX is strictly needed; the sensor
   transmits and the Pi listens." That was written assuming it streams. With only the Pi's
   RX wired, commands never reach the sensor and it is silent forever.
       sensor TX -> GP9 = physical pin 21   (Pi RX)
       sensor RX -> GP8 = physical pin 24   (Pi TX)  <-- the one that gets forgotten

3. THE REQUEST LENGTH FIELD IS len+1, NOT len. From DFRobot_MatrixLidar.cpp verbatim:
       sendpkt->argsNumL = (length + 1) & 0xFF;
   so getAllData (no args) sends argsNum=1 and setRangingMode (4 args) sends argsNum=5.
   Sending the un-incremented value gets a STATUS_FAILED back, which is easy to misread as
   a hardware fault.

4. THE REPLY IS [status][cmd][lenL][lenH][payload] -- status FIRST, and lenL BEFORE lenH.
   0x53 is STATUS_SUCCESS (not a header byte). 0x63 is STATUS_FAILED. 0xFF is filler that
   the vendor library explicitly skips while hunting for the status byte, so a raw hex dump
   looks like corruption when it is nothing of the sort.

Also worth knowing: the DIP switch selects UART vs I2C, the factory default is I2C, and a
POWER DISCONNECT is required for a change to latch -- a Pi reboot does not do it, because the
3.3V header rail stays up. A sensor left in I2C mode is silent on UART with both lines idling
high, which is indistinguishable from every other failure here without checking the switch.
"""
import os, sys, time, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

STATUS_SUCCESS = 0x53
STATUS_FAILED = 0x63
FILLER = 0xFF

CMD_SETMODE = 1
CMD_ALLDATA = 2
MATRIX_8X8 = 8          # eMatrix_8X8 = 8, eMatrix_4x4 = 4 (DFRobot_MatrixLidar.h)
INVALID_MM = 4000       # firmware >=1.3 sets every invalid zone to exactly this


def _frame(cmd, args=b""):
    """Build a request. argsNum counts the cmd byte plus its args -- hence len(args)+1."""
    n = len(args) + 1
    return bytes([0x55, (n >> 8) & 0xFF, n & 0xFF, cmd]) + args


def recv(ser, timeout=8.0):
    """Read one reply. Skips 0xFF filler exactly as the vendor library does.

    8s is not arbitrary: DFRobot_MatrixLidar.cpp polls until its own DEBUG_TIMEOUT_MS of 8000.
    Anything shorter risks scoring a slow-but-valid reply as silence."""
    t0 = time.time()
    skipped = 0
    while time.time() - t0 < timeout:
        b = ser.read(1)
        if not b:
            continue
        s = b[0]
        if s == FILLER:
            skipped += 1
            continue
        if s in (STATUS_SUCCESS, STATUS_FAILED):
            hdr = b""
            while len(hdr) < 3 and time.time() - t0 < timeout:
                hdr += ser.read(3 - len(hdr))
            if len(hdr) < 3:
                return None
            cmd, lenL, lenH = hdr[0], hdr[1], hdr[2]
            n = (lenH << 8) | lenL
            pay = b""
            while len(pay) < n and time.time() - t0 < timeout + 5:
                chunk = ser.read(n - len(pay))
                if not chunk:
                    break
                pay += chunk
            return dict(status=s, cmd=cmd, n=n, pay=pay, skipped=skipped,
                        t=round(time.time() - t0, 2))
        skipped += 1
    return None


def request(ser, frame, timeout=8.0):
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    return recv(ser, timeout)


def show_grid(pay):
    if len(pay) < 128:
        print("   payload is %d bytes, need 128 for an 8x8 grid" % len(pay))
        print("   hex: %s" % pay.hex())
        return
    v = [pay[i] | (pay[i + 1] << 8) for i in range(0, 128, 2)]
    live = sum(1 for x in v if x != INVALID_MM)
    print("   8x8 grid (mm), %d = invalid/no-return, %d/64 zones live:" % (INVALID_MM, live))
    for row in range(8):
        print("     " + " ".join("%5d" % x for x in v[row * 8:row * 8 + 8]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=config.TOF_PORT)
    ap.add_argument("--baud", type=int, default=config.TOF_BAUD)
    ap.add_argument("-n", "--frames", type=int, default=15)
    ap.add_argument("--listen", action="store_true",
                    help="passive only -- transmit nothing. Expect ZERO bytes; it is polled.")
    a = ap.parse_args()

    try:
        import serial
    except ImportError:
        sys.exit("pyserial not installed -- run this on the rover, in its venv")

    if not os.path.exists(a.port):
        sys.exit("%s does not exist. Is 'dtoverlay=uart3-pi5' in /boot/firmware/config.txt?\n"
                 "NOT 'uart3' -- that overlay is BCM2711/Pi 4 and lands UART3 on GPIOs 4-7,\n"
                 "which boots cleanly and reads as dead hardware." % a.port)

    ser = serial.Serial(a.port, a.baud, timeout=0.2)
    print("%s @ %d" % (a.port, a.baud))

    if a.listen:
        ser.reset_input_buffer()
        print("PASSIVE listen 30s, transmitting nothing...")
        t0 = time.time()
        total = 0
        while time.time() - t0 < 30:
            total += len(ser.read(4096))
        print("passive bytes: %d   (0 is CORRECT -- the sensor is polled, not streaming)" % total)
        ser.close()
        return

    r = request(ser, _frame(CMD_SETMODE, bytes([0, 0, 0, MATRIX_8X8])))
    if r is None:
        print("SETMODE_8x8 -> TIMEOUT")
    else:
        print("SETMODE_8x8 -> %s cmd=%d len=%d t=%ss" % (
            "SUCCESS" if r["status"] == STATUS_SUCCESS else "FAILED", r["cmd"], r["n"], r["t"]))
    # setRangingMode() ends in delay(5000) in the vendor library -- the sensor needs it.
    print("settling 5s (the vendor library does delay(5000) here)...")
    time.sleep(5.5)

    good = 0
    grid = None
    for i in range(1, a.frames + 1):
        r = request(ser, _frame(CMD_ALLDATA))
        if r is None:
            print("  %3d: TIMEOUT" % i)
            continue
        ok = (r["status"] == STATUS_SUCCESS and r["cmd"] == CMD_ALLDATA
              and len(r["pay"]) == r["n"])
        if ok:
            good += 1
            if grid is None:
                grid = r["pay"]
        print("  %3d: %s cmd=%d len=%d got=%d ff=%d t=%ss %s" % (
            i, "SUCCESS" if r["status"] == STATUS_SUCCESS else "FAILED",
            r["cmd"], r["n"], len(r["pay"]), r["skipped"], r["t"], "OK" if ok else "MISMATCH"))
        time.sleep(0.4)

    print("\nRESULT: %d/%d clean frames" % (good, a.frames))
    if grid:
        show_grid(grid)
    if good and good < a.frames:
        print("PARTIAL. §6.5 wants a stable multi-minute stream before this goes near the\n"
              "reflex path -- intermittent is a fail, not a pass. Re-run with -n 200.")
    ser.close()


if __name__ == "__main__":
    main()
