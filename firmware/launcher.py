"""Installed on each Pico AS main.py (2026-10-10), once, over USB. Never updated over the UART.

Runs the board's firmware from app.py. Makes a bad UART update recoverable without a USB cable:
  - app.py crashing, failing to import, or hanging (its watchdog) resets the board;
  - a NEW app.py is on trial (file 'trial', written by uartupd COMMIT) until the Pi confirms it;
    each boot on trial counts, and the second failed boot puts app_prev.py back.
Ctrl-C from mpremote is KeyboardInterrupt, not Exception, so USB recovery still works.
"""
import os
import time
import machine


def _trial_count():
    try:
        with open("trial") as f:
            return int(f.read() or "0")
    except (OSError, ValueError):
        return None


n = _trial_count()
if n is not None:
    if n >= 2 and "app_prev.py" in os.listdir():
        # Only with a previous firmware to go back to: renaming app.py away with nothing to
        # replace it would leave the board running nothing at all.
        try:
            os.remove("app_bad.py")
        except OSError:
            pass
        try:
            os.rename("app.py", "app_bad.py")
            os.rename("app_prev.py", "app.py")
        except OSError:
            pass
        try:
            os.remove("trial")
        except OSError:
            pass
    else:
        with open("trial", "w") as f:
            f.write(str(n + 1))

try:
    import app
    app.main()
except Exception as e:
    print("app failed:", e)
    time.sleep(1)
    machine.reset()
