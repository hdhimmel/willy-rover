"""Pico B firmware -- three HC-SR04 sonars and the BNO085 reset, over uart2-pi5.

NOT YET RUN ON HARDWARE. Written 2026-09-24. Master Hardware Design section 4.7
is the wiring authority; this file must not disagree with it.

THERE IS NO 999 SENTINEL HERE, AND THERE MUST NEVER BE ONE.
`sensors.py:43,46` return 999.0 on timeout and `safety.py:22,38` default to it,
which makes "I got no reading" and "nothing is in front of me" the same value.
Behind a serial link that is a fail-open: a dropped frame asserts clear path.
This firmware reports an unmeasurable channel as **-1** and never as a distance,
stamps every channel with its own age in milliseconds, and numbers every frame.
The Pi enforces the deadline and stale must mean STOP -- Software Design S-9.

ECHO STUCK HIGH IS A DESTROYED SENSOR, NOT A TIMEOUT. Two HC-SR04s were killed
by reverse polarity on 2026-09-17: 19 ohms across VCC-GND and ECHO held high
instead of idling low (section 16.12). So this firmware checks ECHO is low
BEFORE it triggers, and reports a stuck line as its own flag rather than letting
it masquerade as no-echo. A stuck line also never lets a measurement start, so
without this check the channel would simply read invalid forever with no clue
why.

THE RADIO IS NOT INITIALISED. Do not import `network`. Section 12 item 17.
"""

import sys
import time
import machine
from machine import Pin, UART, time_pulse_us

VERSION = "b-0.1"
BOARD = "B"

# --- wiring, section 4.7 -----------------------------------------------------
# ECHO arrives already divided to 3.33V on the signal conditioning board; the
# divider never moves downstream of the Pico (its GPIO is not 5V tolerant).
SONARS = (
    # name,   TRIG, ECHO, P1 trig, P1 echo
    ("front", 0, 1, "P1-1", "P1-4"),
    ("left",  2, 3, "P1-5", "P1-8"),
    ("right", 4, 5, "P1-9", "P1-12"),
)

UART_ID = 0
UART_TX = 12          # -> Pi GP5, phys 29
UART_RX = 13          # <- Pi GP4, phys 7
BAUD = 115200

LED_PIN = 14
RST_PIN = 15          # BNO085 RST, open-drain against a 10k pull-up to Pi 3V3

# 4 m of air is 23.3 ms there and back; 25 ms gives margin without stalling the
# loop on a dead channel.
ECHO_TIMEOUT_US = 25_000
# HC-SR04 needs ~60 ms between pings to avoid hearing its own last burst. One
# sensor per 30 ms slot, round robin, is 90 ms per sensor -- about 11 Hz each.
SLOT_MS = 30
US_TO_MM = 0.1715     # 343 m/s, there and back

RST_ASSERT_MS = 10

F_STUCK = {"front": 0x01, "left": 0x02, "right": 0x04}
F_RESET_DONE = 0x40   # an IMU reset has been performed since boot


class Sonar:
    def __init__(self, name, trig, echo):
        self.name = name
        self.trig = Pin(trig, Pin.OUT, value=0)
        self.echo = Pin(echo, Pin.IN)
        self.mm = -1
        self.stamp = None       # ticks_ms of the last VALID reading
        self.stuck = False

    def ping(self):
        # The sensor's own idle state is the first diagnostic. Check it before
        # driving anything -- section 16.12's table, check 1.
        if self.echo.value():
            self.stuck = True
            self.mm = -1
            return
        self.stuck = False

        self.trig.value(1)
        time.sleep_us(10)
        self.trig.value(0)

        us = time_pulse_us(self.echo, 1, ECHO_TIMEOUT_US)
        if us < 0:
            # -1 no pulse end, -2 no pulse start. Either way: not a distance.
            self.mm = -1
            return
        self.mm = int(us * US_TO_MM)
        self.stamp = time.ticks_ms()

    def age_ms(self, now):
        if self.stamp is None:
            return -1
        return time.ticks_diff(now, self.stamp)


class ImuReset:
    """Open-drain, idle hi-Z. A push-pull pin sitting at 0V while this board is
    unpowered and the Pi runs on Witty Pi would hold an active-low reset on a
    live IMU -- section 4.7 consequence 1. OPEN_DRAIN with value=1 is hi-Z, so
    that state is unreachable, and the pull-up is what holds RST high."""

    def __init__(self, pin):
        self.pin = Pin(pin, Pin.OPEN_DRAIN, value=1)
        self.count = 0

    def assert_reset(self):
        self.pin.value(0)
        time.sleep_ms(RST_ASSERT_MS)
        self.pin.value(1)
        self.count += 1


def checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return c


def send(uart, body):
    uart.write("${}*{:02X}\n".format(body, checksum(body)))


def main():
    led = Pin(LED_PIN, Pin.OUT, value=0)
    uart = UART(UART_ID, baudrate=BAUD,
                tx=Pin(UART_TX), rx=Pin(UART_RX),
                timeout=0, timeout_char=0)
    sonars = [Sonar(n, t, e) for (n, t, e, _a, _b) in SONARS]
    by_name = {s.name: s for s in sonars}
    imu = ImuReset(RST_PIN)
    uid = "".join("{:02x}".format(b) for b in machine.unique_id())

    send(uart, "I,{},{},{}".format(BOARD, uid, VERSION))

    seq = 0
    slot = 0
    next_slot = time.ticks_ms()
    next_led = next_slot
    rx = b""
    reset_done = False

    wdt = machine.WDT(timeout=2000)

    while True:
        wdt.feed()
        now = time.ticks_ms()

        # --- commands from the Pi -------------------------------------------
        chunk = uart.read()
        if chunk:
            rx += chunk
            while b"\n" in rx:
                line, rx = rx.split(b"\n", 1)
                cmd = line.strip().upper()
                if cmd == b"PING":
                    send(uart, "P,{}".format(seq))
                elif cmd == b"ID":
                    send(uart, "I,{},{},{}".format(BOARD, uid, VERSION))
                elif cmd == b"RST":
                    # Explicit and acknowledged, never implicit and never on
                    # boot -- section 4.7 consequence 1.
                    imu.assert_reset()
                    reset_done = True
                    send(uart, "R,ok,{}".format(imu.count))
                elif cmd:
                    send(uart, "X,unknown")
            if len(rx) > 128:
                rx = b""

        # --- one sensor per slot, round robin -------------------------------
        if time.ticks_diff(now, next_slot) >= 0:
            next_slot = time.ticks_add(next_slot, SLOT_MS)
            sonars[slot].ping()
            slot = (slot + 1) % len(sonars)

            now = time.ticks_ms()
            flags = 0
            for s in sonars:
                if s.stuck:
                    flags |= F_STUCK[s.name]
            if reset_done:
                flags |= F_RESET_DONE

            f = by_name["front"]
            l = by_name["left"]
            r = by_name["right"]
            seq = (seq + 1) & 0xFFFF
            send(uart, "S,{},{},{},{},{},{},{},{},{}".format(
                seq, now,
                f.mm, f.age_ms(now),
                l.mm, l.age_ms(now),
                r.mm, r.age_ms(now),
                flags))

        # --- heartbeat ------------------------------------------------------
        if time.ticks_diff(now, next_led) >= 0:
            next_led = time.ticks_add(next_led, 100)
            led.toggle()


if __name__ == "__main__":
    main()
