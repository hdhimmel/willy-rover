"""Pico A firmware -- six wheel encoders, reported to the Pi over uart4-pi5.

Written 2026-09-24, the day the boards arrived. Master Hardware Design section
4.7 is the wiring authority; this file must not disagree with it.

STATE: the PIO encoder counter is VERIFIED ON HARDWARE (see count_edges) on the
board carrying UID 643f69a756a232ea -- Pico A, MicroPython v1.29.0 (2026-08-24).
ALL OF IT IS NOW PROVEN ON HARDWARE, 2026-09-30. This said "NOTHING IS WIRED YET"
until then. Measured from the Pi on /dev/ttyAMA4: $E at exactly 50.0 Hz, 300 frames
in 6.0s with zero sequence gaps and zero bad checksums; the board answered a bare ID
with its own UID, so the Pi -> Pico direction works here (it does not on B); the R5
divider read 3.392 V; the LED lights and winks; and all six channels counted under
real edge load with one wheel driven at a time on blocks.

COUNTS ARE SIGNED, from a-0.3 (2026-10-01). Phase B is alive on all six new motors
(proven that day over USB -- see PHASE_A below), so count_quad() decodes direction:
both edges of A, with B sampled at each, x2 resolution. Until a-0.3 the counts were
Phase-A-rising-only and unsigned -- lf ran in reverse on 2026-09-29 and nothing could
see it. Which sign is "forward" differs by side, because the motors are mirrored;
the Pi owns that (config.ENCODER_SIGN), not this board.

WHY PIO AND NOT INTERRUPTS. At 620 RPM output that is 7,773 counts/s per wheel
(752 counts/rev x 10.33 rev/s), ~3,900 edges/s on each of twelve channels.
MicroPython's IRQ overhead is 5-15us per handler -- a large fraction of the
budget before any work is done, so it would starve the reporting loop and still
miss edges.

REVERTED 2026-09-27. Yesterday this said the swap would cut the rate 1.78x. The
vendor parameter table shows the JGA25-370 family runs ONE ~6,000 RPM motor behind
every gearbox, so the bare speed does not change: 4,365 counts/s per wheel fitted
(9.6:1, 422 counts/rev, 620 RPM) against 4,426 after (35.5:1, 1562, 170 RPM) --
within 1.5%. PIO is required either way.

Those old-motor figures were never measured; the motors came out first. On the
fitted 35.5:1 motors the count is MEASURED: 382 Phase A edges per wheel revolution
(2026-10-01, config.py), i.e. an effective ~34.7:1.

WHY x2 AND NOT FULL x4 QUADRATURE. Phase B read dead on the OLD motors from
2026-09-18; on the new ones it works. x4 would also count B's edges, which needs
a jump-table decoder that MicroPython's asm_pio makes awkward, for resolution the
rover does not need: x2 is 763 counts per wheel revolution, ~0.42 mm of travel
per count. x2 keeps one state machine per wheel -- the CYW43 radio driver holds
one of the twelve, so there is no room for two per wheel anyway.

THE RADIO IS NOT INITIALISED. Do not import `network`. Section 12 item 17.
"""

import rp2
import sys
import time
import machine
from machine import Pin, ADC, UART

VERSION = "a-0.4"   # 2026-10-10: firmware update over the UART (uartupd.py)
BOARD = "A"

# --- wiring, section 4.7 -----------------------------------------------------
# Pairs are in MCP23017 GPA0->GPB3 order so the existing twelve-way harness
# lands 1:1 (config.py:235). Yellow = Phase A = even GP, green = Phase B = odd.
WHEELS = ("lf", "lm", "rf", "rm", "lr", "rr")
# CORRECTED 2026-09-29. This tuple used to read rf, rm, lf, lm, rr, lr -- copied
# from config.ENCODER_PINS, which disagrees with the as-built landing recorded in
# Master Hardware Design 16.6 by a left/right swap at every position. Bench proof,
# one wheel at a time on blocks: driving lf counted on GP0/GP1, rf on GP4/GP5, lm on
# GP2/GP3, rr on GP10/GP11 -- the as-built table, every time. The HARNESS was never
# wrong; this label was. Do not "fix" it by re-landing twelve wires.
#
# ⚠ THAT CORRECTION WAS HALF DONE, found 2026-10-01. It reordered WHEELS but left these two
# dicts keyed the old way (rf: 0, lf: 4 ...), so WHEELS[0]="lf" read GP4 -- the RIGHT front.
# This file was never flashed in that state: the board still runs the 2026-09-29 copy whose
# WHEELS is ("rf","rm","lf","lm","rr","lr"), wrong labels but GP0,2,4,6,8,10 in slot order,
# which the Pi relabels correctly. Flashing this file before today's fix would have swapped
# every wheel left/right, and test_encoder_order passed throughout because it compared only
# label tuples. Measured on Pico A over USB the same day, each wheel driven alone at 0.5:
# lf GP0/1, lm GP2/3, rf GP4/5, rm GP6/7, lr GP8/9, rr GP10/11 -- A and B toggling in step
# on all six. Slot i is GP 2i (A) and 2i+1 (B); tests/test_encoder_order.py now pins that.
PHASE_A = {"lf": 0, "lm": 2, "rf": 4, "rm": 6, "lr": 8, "rr": 10}
PHASE_B = {"lf": 1, "lm": 3, "rf": 5, "rm": 7, "lr": 9, "rr": 11}

UART_ID = 0
UART_TX = 12          # -> Pi GP13, phys 33
UART_RX = 13          # <- Pi GP12, phys 32
BAUD = 115200

# Status LED: the Pico 2 W has one ONBOARD, on the CYW43439, exposed by
# MicroPython as Pin("LED"). An earlier revision of this file fitted an external
# LED on GP14 in the belief that the onboard one was unusable without the radio.
# That was wrong: driving it brings up the wireless CHIP and loads its firmware
# over SPI, but joins no network and transmits nothing. Section 12 item 17 was
# amended 2026-09-26 to permit exactly that and nothing more. Do NOT import
# `network`. VERIFIED on both boards 2026-09-30 -- lit, and winking once a second.
LED_PIN = "LED"       # GP14 is free
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


@rp2.asm_pio()
def count_quad():
    """Signed x2 quadrature: both edges of A (in_base), B (jmp_pin) sampled at each.

    Forward-for-this-encoder means A leads B: A rises while B is low, and falls while
    B is high. Those edges DECREMENT X; the other two INCREMENT it. PIO has no
    increment, so X++ is done as X = ~(~X - 1). The count is (-X), so A-leads-B
    reads positive -- the same convention count_edges() used, and the same pushing
    from inside the loop, for the reasons recorded there.

    Every label names a real instruction (count_edges' failure 1).
    """
    wrap_target()
    wait(1, pin, 0)              # A rose
    jmp(pin, "rise_b_hi")
    jmp(x_dec, "rise_push")      # B low: A leads -> X--
    label("rise_push")
    jmp("push_rise")
    label("rise_b_hi")
    mov(x, invert(x))            # B high: B leads -> X++
    jmp(x_dec, "rise_inv")
    label("rise_inv")
    mov(x, invert(x))
    label("push_rise")
    mov(isr, x)
    push(noblock)
    wait(0, pin, 0)              # A fell
    jmp(pin, "fall_b_hi")
    mov(x, invert(x))            # B low: B leads -> X++
    jmp(x_dec, "fall_inv")
    label("fall_inv")
    mov(x, invert(x))
    jmp("push_fall")
    label("fall_b_hi")
    jmp(x_dec, "push_fall")      # B high: A leads -> X--
    label("push_fall")
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
            b = Pin(PHASE_B[w], Pin.IN, Pin.PULL_UP)
            sm = rp2.StateMachine(i, count_quad, freq=2_000_000, in_base=pin, jmp_pin=b)
            sm.exec("set(x, 0)")
            sm.active(1)
            self._sm[w] = sm
            self._raw[w] = 0
            # B is also sampled for F_PHASE_B_SEEN -- kept as a cheap wiring check.
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


class Status:
    """Onboard LED, lit from the moment the board is powered.

    Wrapped, and never allowed to fail loudly. Driving Pin("LED") brings the
    CYW43439 up over SPI, and this sits in main.py's boot path: if it threw, the
    board would crash-loop and send nothing -- which is exactly the silent-board
    failure that cost 2026-09-28. A Pico that cannot blink must still report.

    Lit steady with a short wink once a second. LIT means powered; the wink means
    the loop is still turning. Steady with no wink is a hung board, and dark is no
    power -- three states, one indicator, readable from across the bench.
    """

    WINK_MS = 60
    PERIOD_MS = 1000

    def __init__(self, pin):
        self.led = None
        self.off_until = None
        try:
            self.led = Pin(pin, Pin.OUT)
            self.led.value(1)
        except Exception:
            self.led = None
        self.next_wink = time.ticks_add(time.ticks_ms(), self.PERIOD_MS)

    def beat(self, now):
        if self.led is None:
            return
        try:
            if self.off_until is not None:
                if time.ticks_diff(now, self.off_until) >= 0:
                    self.led.value(1)
                    self.off_until = None
            elif time.ticks_diff(now, self.next_wink) >= 0:
                self.led.value(0)
                self.off_until = time.ticks_add(now, self.WINK_MS)
                self.next_wink = time.ticks_add(self.next_wink, self.PERIOD_MS)
        except Exception:
            self.led = None


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
    led = Status(LED_PIN)
    uart = UART(UART_ID, baudrate=BAUD,
                tx=Pin(UART_TX), rx=Pin(UART_RX),
                timeout=0, timeout_char=0, rxbuf=1024)   # update lines are ~280 chars
    try:
        from uartupd import Receiver
        upd = Receiver(lambda body: send(uart, body))
    except ImportError:
        upd = None        # installed without uartupd.py: USB updates only, as before
    adc = ADC(Pin(R5_SENSE))
    enc = Encoders()
    uid = "".join("{:02x}".format(b) for b in machine.unique_id())

    send(uart, "I,{},{},{}".format(BOARD, uid, VERSION))

    seq = 0
    zero = enc.counts()
    period_ms = 1000 // REPORT_HZ
    next_report = time.ticks_ms()
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
                # Update lines are case-sensitive hex: handled BEFORE the upper() below.
                if upd is not None and upd.handle(line.strip()):
                    continue
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
            if len(rx) > 600:      # must fit an update line (was 128)
                rx = b""          # a partial line this long is noise, not a command

        enc.poll_phase_b()

        # --- telemetry ------------------------------------------------------
        if time.ticks_diff(now, next_report) >= 0:
            next_report = time.ticks_add(next_report, period_ms)
            raw = enc.counts()
            # Signed since a-0.3: a wheel driven backwards counts DOWN. Sent as a signed
            # decimal; the Pi unwraps across the 32-bit boundary either way.
            deltas = []
            for w in WHEELS:
                d = (raw[w] - zero[w]) & 0xFFFFFFFF
                deltas.append(d - 0x100000000 if d & 0x80000000 else d)

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
        led.beat(now)


if __name__ == "__main__":
    main()
