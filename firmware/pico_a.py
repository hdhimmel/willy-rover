"""Pico A firmware -- six wheel encoders, reported to the Pi over uart4-pi5.

Written 2026-09-24, the day the boards arrived. Master Hardware Design section
4.7 is the wiring authority; this file must not disagree with it.

STATE: the PIO encoder counter is VERIFIED ON HARDWARE (see count_edges) on the
board carrying UID 643f69a756a232ea -- Pico A, MicroPython v1.29.0 (2026-08-24).
NOTHING IS WIRED YET, so the UART link, the LED, the R5 divider and the frame
rate under real edge load are all unproven.

WHY PIO AND NOT INTERRUPTS. At 620 RPM output the edge rate is 3,885 Hz per
channel (752 counts/rev / 2 channels x 10.33 rev/s), so twelve channels is
~46,600 edges/s. MicroPython's IRQ overhead is 5-15us per handler, i.e. 20-70%
of a 21us budget before any work is done -- it would starve the reporting loop
and still miss edges. The gearbox does not save us either: the encoder is on the
MOTOR shaft, ahead of the reduction, so the 170 RPM motors on order give the
same ~7.8 kHz per wheel (section 7.1). PIO counts in hardware and is the only
thing that actually solves this.

WHY EDGE COUNTING AND NOT QUADRATURE, FOR NOW. Phase B (green) reads dead on
all six channels (config.py:222) and may have been destroyed by the reversed
supply of 2026-09-18. Direction-aware decode cannot be validated against
hardware that cannot produce a B transition, so this firmware counts Phase A
edges only -- distance without direction, which is exactly what the rover can
prove today. It also SAMPLES the B pins and reports whether any of them has
ever moved, which turns that open question into telemetry instead of a bench
session. When the green wires are fixed, replace count_edges() with a
jump-table quadrature decoder and the wire protocol does not change.

THE RADIO IS NOT INITIALISED. Do not import `network`. Section 12 item 17.
"""

import rp2
import sys
import time
import machine
from machine import Pin, ADC, UART

VERSION = "a-0.2"
BOARD = "A"

# --- wiring, section 4.7 -----------------------------------------------------
# Pairs are in MCP23017 GPA0->GPB3 order so the existing twelve-way harness
# lands 1:1 (config.py:235). Yellow = Phase A = even GP, green = Phase B = odd.
WHEELS = ("rf", "rm", "lf", "lm", "rr", "lr")
PHASE_A = {"rf": 0, "rm": 2, "lf": 4, "lm": 6, "rr": 8, "lr": 10}
PHASE_B = {"rf": 1, "rm": 3, "lf": 5, "lm": 7, "rr": 9, "lr": 11}

UART_ID = 0
UART_TX = 12          # -> Pi GP13, phys 33
UART_RX = 13          # <- Pi GP12, phys 32
BAUD = 115200

LED_PIN = 14          # external LED + 330R; the CYW43439's LED is unavailable
R5_SENSE = 28         # ADC2, 10k/10k divider tapped UPSTREAM of F1

R5_DIVIDER = 2.0      # 10k/10k
ADC_VREF_MV = 3300    # the Pico's own regulated 3V3, not R5 -- that is what
                      # keeps the reading valid while R5 sags

REPORT_HZ = 50
LED_HZ = 5

# --- flags ------------------------------------------------------------------
F_PHASE_B_SEEN = 0x01   # at least one B channel has transitioned since boot
F_R5_LOW = 0x02         # R5 below R5_WARN_MV -- the 2026-08-25 failure mode
F_OVERFLOW = 0x04       # a counter wrapped between reports (should not happen)

R5_WARN_MV = 3000


@rp2.asm_pio()
def count_edges():
    """Count rising edges on one pin, forever, in X, pushing X after each one.

    X starts at 0 and counts DOWN, because PIO can decrement but not increment
    -- so the count is (-X) & 0xFFFFFFFF.

    VERIFIED ON HARDWARE 2026-09-24 (Pico 2 W, MicroPython v1.29.0): six state
    machines watching one PIO-generated 46.9 Hz square wave all read exactly 47
    over one second. Two earlier versions of this program did not work, and both
    failures are worth keeping:

    1. `jmp(x_dec, "cont")` with `label("cont")` immediately before `wrap()`
       targets an address PAST THE END of the program, because the label has no
       instruction after it. It counted 2 edges in 1000, silently. A label must
       name a real instruction.
    2. Reading X by injecting `mov(isr, x)` + `push()` via StateMachine.exec()
       OVER-counts -- 50 and 61 against a true 47. Writing to SMx_INSTR while the
       SM is stalled on `wait` replaces the stalled instruction and the PC moves
       past it, so a read can skip a wait and manufacture a count. **Do not read
       X with exec while this program is running.**

    So the count is pushed from inside the loop instead, and the CPU drains the
    FIFO often and keeps the newest value. X remains authoritative: `push(noblock)`
    discards rather than stalling when the FIFO is full, so a slow drain costs
    freshness, never counts.
    """
    wrap_target()
    wait(0, pin, 0)
    wait(1, pin, 0)
    jmp(x_dec, "emit")     # decrement X; target is the next instruction either way
    label("emit")
    mov(isr, x)
    push(noblock)
    wrap()


class Encoders:
    def __init__(self):
        self._sm = {}
        self._raw = {}
        self._b = {}
        self._b_first = {}
        self.phase_b_seen = False
        for i, w in enumerate(WHEELS):
            pin = Pin(PHASE_A[w], Pin.IN, Pin.PULL_UP)
            sm = rp2.StateMachine(i, count_edges, freq=2_000_000, in_base=pin)
            sm.exec("set(x, 0)")
            sm.active(1)
            self._sm[w] = sm
            self._raw[w] = 0
            # Phase B is sampled, not counted -- see the module docstring.
            b = Pin(PHASE_B[w], Pin.IN, Pin.PULL_UP)
            self._b[w] = b
            self._b_first[w] = b.value()

    def drain(self):
        """Take the newest count from each FIFO. Call this every loop pass, not
        once per report: a FIFO is 4 deep and saturates in about 1 ms at full
        speed, and a saturated FIFO holds OLD values. Measured 11,000 drain
        passes per second on a Pico 2 W with nothing else running, against the
        ~4 kHz per channel this has to keep up with."""
        for w in WHEELS:
            sm = self._sm[w]
            while sm.rx_fifo():
                self._raw[w] = sm.get()

    def counts(self):
        return {w: (-self._raw[w]) & 0xFFFFFFFF for w in WHEELS}

    def poll_phase_b(self):
        """Report whether any green wire has ever moved. Cheap, and it answers
        the standing question in config.py:222 from the rover itself."""
        if self.phase_b_seen:
            return
        for w in WHEELS:
            if self._b[w].value() != self._b_first[w]:
                self.phase_b_seen = True
                return


def checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return c


def send(uart, body):
    """$<body>*<XX>\n -- NMEA-style so a human with a terminal can read it.
    Every frame this rover has lost a session to was one nobody could read."""
    uart.write("${}*{:02X}\n".format(body, checksum(body)))


def main():
    led = Pin(LED_PIN, Pin.OUT, value=0)
    uart = UART(UART_ID, baudrate=BAUD,
                tx=Pin(UART_TX), rx=Pin(UART_RX),
                timeout=0, timeout_char=0)
    adc = ADC(Pin(R5_SENSE))
    enc = Encoders()
    uid = "".join("{:02x}".format(b) for b in machine.unique_id())

    send(uart, "I,{},{},{}".format(BOARD, uid, VERSION))

    seq = 0
    zero = enc.counts()
    period_ms = 1000 // REPORT_HZ
    led_ms = 1000 // (LED_HZ * 2)
    next_report = time.ticks_ms()
    next_led = next_report
    rx = b""

    wdt = machine.WDT(timeout=2000)

    while True:
        wdt.feed()
        enc.drain()                # every pass -- see Encoders.drain()
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
                elif cmd == b"ZERO":
                    zero = enc.counts()
                    send(uart, "Z,ok")
                elif cmd:
                    send(uart, "X,unknown")
            if len(rx) > 128:
                rx = b""          # a partial line this long is noise, not a command

        enc.poll_phase_b()

        # --- telemetry ------------------------------------------------------
        if time.ticks_diff(now, next_report) >= 0:
            next_report = time.ticks_add(next_report, period_ms)
            raw = enc.counts()
            deltas = [(raw[w] - zero[w]) & 0xFFFFFFFF for w in WHEELS]

            mv = int(adc.read_u16() / 65535 * ADC_VREF_MV * R5_DIVIDER)

            flags = 0
            if enc.phase_b_seen:
                flags |= F_PHASE_B_SEEN
            if mv < R5_WARN_MV:
                flags |= F_R5_LOW

            seq = (seq + 1) & 0xFFFF
            send(uart, "E,{},{},{},{},{},{},{},{},{},{}".format(
                seq, now,
                deltas[0], deltas[1], deltas[2], deltas[3], deltas[4], deltas[5],
                mv, flags))

        # --- heartbeat ------------------------------------------------------
        if time.ticks_diff(now, next_led) >= 0:
            next_led = time.ticks_add(next_led, led_ms)
            led.toggle()


if __name__ == "__main__":
    main()
