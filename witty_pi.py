import config
if not config.SIMULATE_HARDWARE and config.ENABLE_WITTY_PI:
    import smbus2

# Witty Pi 5 HAT+ (UUGear), added 2026-08-20. Register map per the official user manual (rev
# 1.03) — see docs/WildWilly_Software_Design_v1.0.md SS4.1 item 0's sibling note for the fuller
# integration story. This module deliberately covers only the one thing brain.py's own tick loop
# needs to actively participate in: feeding Witty Pi 5's independent hardware watchdog. Everything
# else (RTC sync, scheduled power on/off, the low-voltage cutoff, and reacting to a shutdown
# request) is handled by the vendor's own `wp5`/`wp5d` software once installed and configured —
# no custom code needed for those, and none is written here.
#
# Heartbeat protocol is best-effort per the manual's own wording ("the software periodically
# polls a register over I2C, which will trigger the firmware to update the heartbeat value") --
# read, not write, per that literal description. This is NOT independently confirmed against the
# real hardware yet (which doesn't exist on this unit as of this commit) -- verify against a real
# unit before trusting it, same as every other "per the datasheet" assumption in this codebase
# until it's been live-tested.
class WittyPi:
    _REG_HEARTBEAT=70
    def __init__(self,bus=1):
        self._enabled=config.ENABLE_WITTY_PI and not config.SIMULATE_HARDWARE
        self._bus=smbus2.SMBus(bus) if self._enabled else None
    def heartbeat(self):
        # Services Witty Pi 5's own independent hardware watchdog (its register #29 configures
        # how many missed heartbeats trigger a forced power cycle -- a stronger, MCU-level
        # recovery path than systemd's WatchdogSec, which can't help if the kernel itself is
        # what's hung, since systemd is part of that same hung kernel).
        if not self._enabled: return
        try: self._bus.read_byte_data(config.WITTY_PI_ADDR,self._REG_HEARTBEAT)
        except OSError: pass
    @property
    def available(self): return self._enabled
