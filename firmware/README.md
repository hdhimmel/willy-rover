# Pico 2 W firmware

MicroPython for the two Pico 2 W boards of Master Hardware Design **§4.7**.
Written 2026-09-24, the day the boards arrived.

| Board | UID | MicroPython | State |
|---|---|---|---|
| **A** | `643f69a756a232ea` | v1.29.0, 2026-08-24 | PIO counter **verified**; all code paths run |
| **B** | `ad25bbf0f1e1f160` | v1.29.0, 2026-08-24 | all code paths run; open-drain reset **verified** |

**Nothing is wired.** Proven on **A**: the PIO encoder counter, and that every
code path runs — six state machines claim GP0–GP11, the drain loop turns over
6,500 times a second, UART0 opens on GP12/GP13, the ADC path reads, GP14 toggles.
Proven on **B**: the open-drain reset behaves (idle 1 → asserted 0 → released 1
against an emulated pull-up), three disconnected sonars report `-1` and never a
distance, UART0 opens, GP14 toggles.

Not proven on either: anything needing a wire — the link to the Pi, the LEDs, the
R5 divider, real echoes, and the frame rate under real load.

| File | Board | Link | Job |
|---|---|---|---|
| `pico_a.py` | **A** | `uart4-pi5`, Pi GP12/GP13 | six wheel encoders, R5 rail sense |
| `pico_b.py` | **B** | `uart2-pi5`, Pi GP4/GP5 | three HC-SR04, BNO085 reset |

Both use **UART0 on their own GP12/GP13** at **115200**, an external status LED
on **GP14**, and leave the radio uninitialised (§12 item 17). Do not
`import network`.

## Installing

Test from the REPL before making it permanent — once `main.py` runs a loop with
a watchdog, the REPL is hard to reach.

```
mpremote connect COM4 run firmware/pico_a.py      # try it, Ctrl-C to stop
mpremote connect COM4 fs cp firmware/pico_a.py :main.py   # make it permanent
```

To recover a board that boots straight into a loop: hold **BOOTSEL** while
plugging in USB and re-flash MicroPython, or `mpremote ... fs rm :main.py` if you
can still interrupt it.

## Wire protocol

Line-based ASCII, NMEA-style: `$<body>*<XX>\n` where `XX` is the XOR of every
character between `$` and `*`. Deliberately human-readable — every frame this
rover has lost a session to was one nobody could read at a terminal.

**Pico → Pi**

```
$I,<board>,<uid>,<ver>*XX                                  on boot, and on ID
$E,<seq>,<ms>,<rf>,<rm>,<lf>,<lm>,<rr>,<lr>,<r5mv>,<flags>*XX     50 Hz, Pico A
$S,<seq>,<ms>,<f_mm>,<f_age>,<l_mm>,<l_age>,<r_mm>,<r_age>,<flags>*XX  13-33 Hz, Pico B
$P,<seq>*XX            reply to PING
$R,ok,<count>*XX       reply to RST
$Z,ok*XX               reply to ZERO
$X,unknown*XX          unrecognised command
```

**Pi → Pico:** `PING`, `ID`, `ZERO` (A — rezero counts), `RST` (B — assert the
IMU reset). One per line.

### Rules the protocol exists to enforce

- **An unmeasurable distance is `-1`, never a number.** `sensors.py:43,46`
  return `999.0` on timeout and `safety.py:22,38` default to it, which makes *no
  reading* and *clear path* the same value. Behind a serial link that is a
  fail-open. See Software Design **S-9**.
- **Every channel carries its own age in milliseconds**, so the Pi can apply a
  per-sensor staleness deadline instead of trusting the frame as a whole.
  **Stale must mean stop.**
- **Every frame carries a sequence number**, so a gap is visible rather than
  silently interpolated.
- **The IMU reset is an explicit, acknowledged command.** Never implicit, never
  on boot.

## Design notes worth knowing before editing

**Pico A counts Phase A edges only — on purpose.** Phase B (green) reads dead on
all six channels (`config.py:222`) and may have been destroyed by the reversed
supply of 2026-09-18, so direction-aware decode cannot be validated against this
hardware. The firmware therefore reports distance without direction, and
separately **samples the B pins and reports whether any of them has ever
moved** — turning that open question into telemetry instead of a bench session.
When the green wires are fixed, replace `count_edges()` with a jump-table
quadrature decoder; the wire protocol does not change.

**PIO is not optional.** 3,885 edges/s per channel × 12 = ~46,600/s, against a
MicroPython IRQ overhead of 5–15 µs. And the 170 RPM motors do not help: the
encoder sits on the **motor** shaft, ahead of the gearbox, so the rate is
`bare RPM / 60 × 44` regardless of reduction (§7.1). A slower rover is not a
slower encoder.

**ECHO stuck high is a destroyed sensor, not a timeout.** `pico_b.py` checks
ECHO idles low *before* triggering and flags a stuck line separately — that is
the signature of the two sonars killed on 2026-09-17 (§16.12), and a stuck line
never lets a measurement start, so without the check it would read invalid
forever with no clue why.

**No internal pull on the ECHO pins, deliberately.** The ECHO divider's lower
2 k leg holds the Pico's input low whenever the sensor is not driving — that *is*
the pull-down, in hardware. It also sidesteps RP2350 erratum **E9**, where an
input with the internal pull-down enabled can latch around 2.2 V and read high.
An internal pull-down on an ECHO line would be both redundant and exposed to E9.

**A no-echo costs the full timeout, and that sets the frame rate.** Measured on
board B with nothing connected: **40 pings/s**, i.e. 25 ms each — the whole
`ECHO_TIMEOUT_US`. This is not only the fault case: any channel pointing at open
space beyond range times out in normal operation. So the round-robin is **90 ms
when all three see something and ~75 ms of pure blocking when none do**, and the
frame rate is 33 Hz at best, ~13 Hz at worst, with per-sensor updates dropping
from 11 Hz to about 4 Hz.

> **Worth a decision:** `ECHO_TIMEOUT_US = 25000` matches `config.SONAR_TIMEOUT`
> and covers 4.3 m, but every reflex threshold is inside 60 cm
> (`DIST_STOP=20`, `DIST_SLOW=40`, `DIST_CLEAR=60`). Cutting it to **12000 µs
> (≈ 2.05 m, still 3.4× the largest threshold)** halves the worst case and lifts
> the floor to ~28 Hz frames. Not changed here, because shortening a sensor's
> range is a design call, not a tuning one — and the Pi-side `SONAR_TIMEOUT`
> would want to move with it.

**RST is `Pin.OPEN_DRAIN` with `value=1`.** Hi-Z idle, pull-up holds it high. A
push-pull pin at 0 V while Pico B is unpowered and the Pi runs on Witty Pi would
hold an active-low reset on a live IMU (§4.7 consequence 1); open-drain makes
that state unreachable.

## Two PIO bugs found by testing, both silent

Kept because both failed *quietly*, which is the expensive kind.

**1. A label with no instruction after it jumps off the end of the program.**
`jmp(x_dec, "cont")` followed by `label("cont")` and then `wrap()` targets an
address past the last instruction. It counted **2 edges out of 1000** and raised
nothing. A label must name a real instruction.

**2. Reading X with `StateMachine.exec()` while the program is running
OVER-counts.** Injecting `mov(isr, x)` + `push()` gave **50 and 61 against a true
47**. Writing to `SMx_INSTR` while the SM is stalled on `wait` replaces the
stalled instruction and the PC advances past it, so a read can skip a `wait` and
manufacture a count. The exec mechanism itself is fine — `set(x, 5)` reads back 5
— it is exec *while stalled on wait* that is unsafe.

The fix is that PIO pushes the count from inside the loop and the CPU drains
often. **X stays authoritative:** `push(noblock)` discards instead of stalling
when the FIFO is full, so a slow drain costs freshness, never counts. Measured
margin is about 7× — the 4-deep FIFO fills in ~1 ms at full speed and the loop
drains every ~0.15 ms — and it will shrink as the loop gets busier, so re-measure
once the UART is carrying real traffic.

## Unverified — check these on the bench

1. **Counts against reality.** Drive one wheel a known number of revolutions
   **under power** — never by hand, the 17.1:1 gearbox does not back-drive — and
   compare against `ENCODER_COUNTS_PER_REV`. `scripts/encoder_map_check.py` is
   the equivalent check on the old path.
2. **`machine.WDT` on RP2350** — confirm the 2 s timeout behaves as expected, and
   that it does not fire during `time_pulse_us`'s 25 ms worst case.
3. **Slot timing.** 30 ms per sensor assumes an HC-SR04 needs ~60 ms between its
   own pings. If cross-talk appears between front and left, lengthen `SLOT_MS`
   rather than firing them together.
4. **`ADC_VREF_MV`.** Taken as the Pico's own regulated 3V3. Meter it; the whole
   point of the R5 sense is that its reference does *not* move with R5.
