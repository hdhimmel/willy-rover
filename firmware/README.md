# Pico 2 W firmware

MicroPython for the two Pico 2 W boards of Master Hardware Design **§4.7**.
Written 2026-09-24, the day the boards arrived.

| Board | UID | MicroPython | State |
|---|---|---|---|
| **A** | `643f69a756a232ea` | v1.29.0, 2026-08-24 | **`main.py` installed 2026-09-29**, LED verified. Link to the Pi untested |
| **B** | `ad25bbf0f1e1f160` | v1.29.0, 2026-08-24 | **PROVEN ON THE ROVER 2026-09-29** — three sonars ranging at 33.3 Hz over `uart2-pi5` |

**Both boards run their firmware as `main.py` since 2026-09-29.** Board **B** is
proven end to end on the rover: `$S` frames at **33.3 Hz** over `uart2-pi5`, zero
sequence gaps and zero bad checksums over six seconds, all three HC-SR04 ranging,
and the stuck-ECHO flag firing correctly on two dead sensors and clearing on a good
one. Board **A** is installed and runs, but nothing has listened to `uart4-pi5` yet.

⚠ **THE FAULT THAT COST 2026-09-28 WAS A FILENAME.** Both boards had their code on
them as `pico_a.py` / `pico_b.py`, and **a Pico only autoruns `main.py`**. Each board
sat at a bare REPL driving nothing, which on the UART is indistinguishable from an
absent board, a reversed feed or a swapped pair. Worse, the Pi then heard a corrupted
copy of its own transmission — crosstalk across the J2 harness into an unterminated
stub — which read as damaged hardware. Nothing was broken. **`fs cp` the file to
`:main.py`, and delete the copy under its own name so there is only ever one.**

Still not proven: **A's link to the Pi**, the **R5 divider** on A, the encoders, and
the **Pi → Pico direction on B** — `PING`, `ID` and a deliberate `BOGUS` all go
unanswered while frames stream the other way, which isolates it to the one wire from
Pi phys 7 to `c27`. That direction carries `RST`, so the BNO085 needs it.

**The onboard LED is lit at boot and winks for 60 ms once a second** (`Status` in both
files). Lit means powered, the wink means the loop is turning, steady means hung.
It is wrapped in try/except on purpose: driving `Pin("LED")` brings the CYW43439 up
over SPI, and that now sits in `main.py`'s boot path — if it threw, the board would
crash-loop and send nothing, which is the exact failure this firmware exists to make
impossible. Verified on **both** boards 2026-09-29; it had never been run before.

| File | Board | Link | Job |
|---|---|---|---|
| `pico_a.py` | **A** | `uart4-pi5`, Pi GP12/GP13 | six wheel encoders, R5 rail sense |
| `pico_b.py` | **B** | `uart2-pi5`, Pi GP4/GP5 | three HC-SR04, BNO085 reset |

Both use **UART0 on their own GP12/GP13** at **115200** and the **onboard status
LED** (`Pin("LED")` on the CYW43439). **GP14 is free.**

⚠ **The onboard LED needs the wireless chip up.** Driving it loads CYW43439
firmware over SPI — it joins no network and transmits nothing, and §12 item 17 was
amended 2026-09-26 to permit that and nothing more. Still do not `import network`.
An earlier revision of these files fitted an external LED on GP14 on the mistaken
belief that the onboard one was unusable; dropping it also removed a bare GP14
lead that crossed the GP15 reset net on the carrier board.

## Installing

Test from the REPL before making it permanent — once `main.py` runs a loop with
a watchdog, the REPL is hard to reach.

```
mpremote connect COM4 run firmware/pico_a.py      # try it, Ctrl-C to stop
mpremote connect COM4 fs cp firmware/pico_a.py :main.py   # make it permanent
mpremote connect COM4 fs rm :pico_a.py                    # leave only ONE file
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

**PIO is not optional.** 7,773 counts/s per wheel across twelve channels, against a
MicroPython IRQ overhead of 5–15 µs.

⚠ **Reverted 2026-09-27.** Yesterday this was "corrected" to say the swap would cut
the rate 1.78×. The vendor parameter table shows the family runs one ~6,000 RPM motor
behind every gearbox, so the bare speed is unchanged: **4,365 counts/s per wheel
fitted** (9.6:1, 422 c/rev, 620 RPM) against **4,426 after** (35.5:1, 1562 c/rev,
170 RPM) — within 1.5%. The original wording was right. Both are ~4× the I²C poll
ceiling, so PIO is required regardless.

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
