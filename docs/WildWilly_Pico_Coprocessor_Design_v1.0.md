# WildWilly — Pico 2 W Coprocessor Design v1.0

**Created 2026-09-20.** Two designs, at the owner's request: **Pico-E** replaces the
MCP23017 as the wheel-encoder front end, and **Pico-S** takes the three-unit sonar array
off the Pi's GPIO. They are separate boards and separate firmware, and §1 says why.

> **STATUS: DESIGN. NOTHING BELOW IS BUILT, WIRED OR MEASURED.** No part of this document
> records an observation. Every number is either quoted from an existing measurement in
> this repo (cited where it is) or derived from a datasheet figure that is flagged as
> needing confirmation. Following the convention of the Bench Test Procedures, the result
> fields in §9 stay blank until someone runs them on the rover.
>
> This is a design document and does **not** join the three-document authoritative set
> (Master Hardware Design, Software Design, Functional Requirements). If the design is
> built, its content folds into those three and this file becomes history.

---

## 0. What this changes, and what it does NOT

Read this section before the rest. The most likely way this design does harm is by being
believed to fix something it does not touch.

### It does not fix Phase B

`config.py:220` and E-1's 2026-09-18 result record **Phase B dead on all six wheels** —
every odd pin silent except a flicker on A7 — after the encoder supply was found reversed
and corrected. That is a wiring fault (or six output stages killed by the reverse polarity),
one pattern and not six faults. **A Pico reads a dead wire exactly as well as an MCP23017
does: not at all.**

So:

- Counts-per-rev stays unmeasured. It is blocked on Phase B, not on sampling rate.
- Direction resolution stays unavailable. Quadrature needs two channels.
- `ENCODER_COUNTS_PER_REV=752` stays derived, not measured.

**Trace the green wires first.** If Phase B comes back, this design gets a real quadrature
decoder. If it does not, §3.5 specifies the degraded single-channel mode and is explicit
about what that mode cannot do.

### What it does fix

| Problem | Today | After |
|---|---|---|
| Encoder under-sampling (FRD G-2) | ~7.77 kHz/channel against a ~1 kHz poll ceiling — **8× oversubscribed**, aliasing to a constant | PIO decode with ~3 orders of magnitude of margin (§3.4) |
| I²C bus load | The encoder thread is the bus's highest-frequency talker; `sensors.py:353`'s 1 ms sleep exists *only* to stop it starving motor-stop commands, the battery ADC and the IMU | 0x27 leaves the bus entirely. The busiest talker is gone, not throttled |
| Sonar echo timing | Busy-wait in CPython on a shared tick machine, competing with Hailo inference and the voice stack. Jitter becomes distance error | Deterministic PIO pulse measurement on a dedicated MCU |
| A broken sonar reads as "clear" | `sensors.py:43/46` returns `999.0` for *both* "no target" and "echo line stuck" — well past `DIST_CLEAR=60` | Separated into distinct status codes (§4.4) |
| Sonar has no health check at all | `brain.py:425` checks imu/encoders/current/battery_adc. **Not sonar.** There is no `SonarArray.is_healthy` | §4.5 adds one, and makes staleness fail *safe* |
| GP14 hazard | Left sonar ECHO sits on UART0 TXD; the serial console must stay disabled forever or left sonar reads garbage | GP14 frees. The hazard class disappears |
| **Pi CPU** | The sonar busy-waits in Python and burns **an estimated 38–82% of one core**, worst when the path is clear; the encoder thread adds ~1000 wakeups/sec (§7) | Both become a short serial read. Estimated net saving **~0.4–0.8 of a core** |

### What it costs

Two more MCUs, two more firmware artifacts to version, and — most importantly — **a UART
and a second processor inserted between the reflex sensors and the stop.** §4 is mostly
about paying that cost honestly. The architecture constraint in `CLAUDE.md` ("an obstacle
stop must never depend on a detection frame arriving") was written about the NPU, but it
binds here too, and harder, because sonar *is* the reflex ranging rather than an input to it.

---

## 1. Why two boards and not one

One Pico 2 W has ample GPIO (26) and PIO (12 state machines across 3 blocks) for all 18
lines — 12 encoder, 6 sonar — and a single board would be cheaper and one less thing to
flash. Two is still right:

1. **Fault isolation across a tier boundary.** Sonar is reflex-path; encoders feed odometry
   and stall detection. A firmware bug, a busy loop or a watchdog reboot on the encoder side
   must not be able to take the obstacle stop with it. On one board it can.
2. **Different change discipline.** Pico-S firmware should change almost never and every
   change should be bench-proven against a tape measure. Pico-E firmware will change while
   counts-per-rev, sign convention and the Phase B question are being settled. Putting a
   frequently-edited artifact and a safety artifact in the same binary guarantees the safety
   one gets re-flashed casually.
3. **Separate links, separate failure.** Two UARTs means a desynchronised or wedged link
   degrades one subsystem, not both.
4. **Physical routing.** The six encoder harnesses run to the wheels; the three sonar
   harnesses run to the front and both flanks. One board means one of those bundles crosses
   the chassis for no reason.

The cost is two firmware images in a repo whose documented dominant defect is *correct
writing left in place*. §2.6 answers that directly: both images report their own version
over the link, and `diagnostics.py` prints it. The artifact states its own identity, so a
document cannot be wrong about it for three weeks.

---

## 2. Shared design

### 2.1 Part

**Raspberry Pi Pico 2 W (RP2350).** Relevant figures — **confirm against the datasheet
revision in hand before committing the pinout**:

| | |
|---|---|
| Core | Dual Cortex-M33 @ 150 MHz (RP2350 also offers dual Hazard3 RISC-V; use the M33s) |
| PIO | 3 blocks × 4 state machines = **12 SMs** |
| GPIO | 26 usable (GP0–GP22, GP26–GP28); GP23/24/25/29 are tied up by the CYW43 radio and the internal ADC on the W variant |
| Logic | **3.3 V, NOT 5 V tolerant** — same constraint as the MCP23017 it replaces |
| Watchdog | Hardware, on-die (§2.5) |
| Radio | CYW43439 Wi-Fi/BLE — **deliberately never initialised**, see §2.7 |

⚠ **RP2350 internal pull-downs: check the errata sheet for your stepping.** Early RP2350
silicon carried an erratum in which a GPIO configured as input with the internal pull-down
enabled could latch at an intermediate voltage rather than resolving low. Both designs below
have inputs that idle low (sonar ECHO, and encoder lines at rest), so **specify external
pull-downs rather than relying on internal ones** unless the stepping in hand is confirmed
clear. This is cheap insurance and it costs two resistors per line.

### 2.2 Power — prove the rail, not the voltage

Both boards take **5 V from R2 (DROK-5V) into `VSYS`**, and use the Pico's own onboard
buck to make 3.3 V. Not the Pi's 3V3 pin, and not the `3V3` pad.

- `VSYS` accepts a wide input (nominally 1.8–5.5 V), so 5 V is comfortable.
- Pi header pin 1 is already a loaded rail carrying eleven devices' logic, the bus pull-ups
  and the SEN0628 (`CLAUDE.md`, corrected 2026-09-14). Do not add two more MCUs to it.
- R2 is the sonar's existing VCC rail, so Pico-S and its three HC-SR04s share one supply and
  one ground reference — which is what you want for a pulse-timing measurement.

🔴 **Budget it, and then prove which rail you actually landed on.** Worst-case 5 V draw is
already documented as near 9 A against an 8 A UBEC rating. Two Pico 2 Ws add little (tens of
mA each with the radio dark), but "little" is not "nothing" and this rail has no margin to
spend carelessly.

And the lesson the SEN0628 taught on 2026-09-15 applies verbatim: **the TPSM/AMS1117 chain
is fitted but dead, and it looks like a legitimate tap.** A Pico brought up on a marginal or
dormant rail will enumerate over USB (which supplies its own power), light its LED, and fail
in the most misleading way available. Meter the rail at the board, under load, before
believing anything the firmware says.

### 2.3 Level shifting — unchanged, and still not solved

Both Picos are 3.3 V devices with non-5V-tolerant inputs, exactly like the MCP23017.
**Nothing about this design changes the level-shifting question:**

- Encoder signal lines: fine today at R5's 3.3 V. If the standing hypothesis is ever
  revisited and the encoders move to 5 V, **all twelve signal lines still need shifting** —
  see Master Hardware Design §14 item 8, and check first whether the Hall outputs are
  open-collector, in which case a pull-up to 3.3 V does it with no shifter at all.
- Sonar ECHO: keep the **existing 1k/2k dividers**. They are already fitted, already
  verified (S-1, closed 2026-09-17), and the Pico needs them for the same reason the Pi did.
- Sonar TRIG: driven at 3.3 V today and working. Keep it. Do not "improve" it to 5 V.

### 2.4 Link — UART, one per board, and why not I²C

**Each Pico gets its own hardware UART at 115200 8N1**, matching the SEN0628 precedent.

I²C was considered and rejected. The bus is a **single non-isolated electrical segment** with
two passive hubs and no containment; a single device holding SDA or SCL low takes the whole
rover down, which is exactly what happened repeatedly on 2026-09-07/08. Putting the reflex
ranging sensor behind that bus would make the obstacle stop depend on the one shared resource
with a documented history of total failure. The whole point of Pico-S is to *shorten* the path
from echo to stop, not to route it through the rover's most fragile component.

USB was also rejected: all four rover USB ports are occupied (`CLAUDE.md`, 2026-09-13), and
that constraint is what put the ToF on UART in the first place.

### 2.5 Both Picos run their own watchdog

Enable the RP2350 hardware watchdog in both images, fed from the main loop, timeout ~250 ms.

The rover has been bitten from both directions here and the design should learn from both:
the Pi's systemd watchdog **was never armed for five weeks** because the installed unit was
stale, and then **crash-looped the rover** when it was armed, because `Type=simple` meant
systemd discarded every heartbeat. Meanwhile one SEN0628 reviewer had a board reset-looping
every few seconds on current firmware.

So: the watchdog exists so a wedged Pico **reboots in milliseconds and resumes streaming**
rather than sitting mute. The Pi side must be able to tell the two apart, which is what the
sequence number in §2.6 is for — a reboot shows as a sequence reset, a dead board shows as
silence.

### 2.6 Frame format — ASCII, sequenced, CRC'd

One line protocol, shared by both boards. **Newline-terminated ASCII**, not binary.

Binary would be more compact and this is not a bandwidth problem: the encoder stream at
50 Hz is under 1 KB/s against 11.5 KB/s available. ASCII is chosen because **this rover has
repeatedly lost entire sessions to silent devices**, and `cat /dev/ttyAMA4` showing readable
frames is a diagnostic that needs no script, no library and no bench rig. That is worth more
here than compactness.

```
E,<seq>,<t_us>,<lf>,<lm>,<lr>,<rf>,<rm>,<rr>,<mode>,<crc16>\n
S,<seq>,<t_us>,<front_mm>,<left_mm>,<right_mm>,<st_f>,<st_l>,<st_r>,<crc16>\n
```

- `seq` — monotonic uint16, wraps. **A reset to 0 means the Pico rebooted**, and the Pi must
  log that rather than absorb it.
- `t_us` — the Pico's own microsecond clock at sample time. The measurement's timestamp comes
  from the board that took it, never from when Linux happened to read the line.
- `crc16` — CRC-16-CCITT over everything before the final comma, hex. **Table-driven on the Pi
  side, not bitwise** — §7.2 shows the bitwise version costs ~0.75% of a core at 50 Hz, which
  is most of a percent spent proving the ASCII choice was cheap. A frame that fails CRC
  is **dropped, never repaired**, and logged as desync — the same rule `tof.py` already applies
  to a frame of the wrong length ("desynchronised UART, not data").
- Both boards **stream unprompted** at a fixed cadence. Neither is request/response. This is a
  deliberate difference from the SEN0628, which is polled — and note that assuming the
  SEN0628 streamed cost most of a session on 2026-09-15. Streaming is correct *here* because
  the Pi must be able to detect silence, and a device that only speaks when spoken to cannot
  be distinguished from a device that has died.

Commands, Pi → Pico, also newline-terminated ASCII:

| Command | Pico-E | Pico-S |
|---|---|---|
| `ID?` | replies `ID,pico-e,<fw_version>,<git_sha>` | replies `ID,pico-s,<fw_version>,<git_sha>` |
| `ZERO` | zeroes all six counts | not accepted |
| anything else | ignored, logged | **ignored, logged** |

**Pico-S accepts no command that changes its behaviour.** After boot it ranges and it streams;
there is no mode it can be talked into. That is the strongest safety property available on a
link, and it costs nothing because there is no legitimate reason for the Pi to reconfigure the
obstacle sensor at runtime.

`ID?` exists so `diagnostics.py` can print both firmware versions in its FR-1100-004 report.
This is the direct answer to §1's cost: **the firmware states its own version, so no document
can be quietly wrong about which build is flashed.**

### 2.7 ⚠ Pico-E stays silent until spoken to — a consequence of the service port

Added 2026-09-20 with §5.2. The service port is **the Pi's own boot console**: firmware and
bootloader diagnostics come out of it before Linux exists, and a bootloader may accept input
on it. A Pico that starts streaming the instant it has power is therefore injecting bytes into
the Pi's boot process on every single power-up.

So **Pico-E does not transmit until it receives a valid `ID?`.** After that it streams at
50 Hz as §2.6 describes. Two things fall out of this and both are wanted:

- The Pi controls when the link goes live, which is after `brain.py` is up and the boot
  console is done with the port.
- Garbage arriving on Pico-E's RX during boot is already handled — §2.6's command table
  ignores and logs anything that is not `ID?` or `ZERO`, so boot text cannot be mistaken for a
  command.

**Pico-S is the opposite and must stay that way: it streams unconditionally from boot.** It is
on an ordinary header UART with no boot traffic, and §4.5 depends on being able to read
*silence* as a fault. A sonar board that waits to be asked cannot be distinguished from a
sonar board that has died. **This asymmetry is deliberate — do not "harmonise" the two
firmwares by giving them the same startup behaviour.**

### 2.8 The radio stays dark

The Pico 2 **W** is specified because it is what the owner has. **Neither image initialises
the CYW43.**

The sonar board decides whether Willie stops. Adding a network interface to it adds an attack
surface and a source of nondeterministic interrupt load to the single most safety-critical
processor on the rover, in exchange for nothing — the Pi is six inches away on a wire. The
same argument applies to Pico-E with less force but the same conclusion.

If a Wi-Fi telemetry build is ever wanted for bench work, it is a **separate, clearly-named
firmware image that never goes on the rover**, and it goes on Pico-E, never Pico-S.

---

## 3. Part A — Pico-E, the encoder coprocessor

Replaces the MCP23017 @ 0x27. Implements fix-plan Priority 1 item 7, which the Gap Analysis
marked `N/A-HW` on the grounds that "no RP2040 exists on this unit" — that premise changes if
this is built, and both documents need updating (§10).

### 3.1 What leaves the I²C bus

**0x27 disappears from the roll-call. The expected device count goes eleven → ten.**

This is a tripwire. `CLAUDE.md` records that `brain.py::_EXPECTED_I2C` and
`diagnostics.py::_EXPECTED_I2C` already drifted once, and that
`tests/test_expected_i2c_agreement.py` exists to stop it happening again. Both sets derive
from `config.py`, so removing `ENCODER_ADDR` must be done there and allowed to propagate.

Also unchanged and still true: **0x70 belongs in neither set.** It is the PCA9685 all-call
broadcast. Expect ten devices after this change, not eleven, and not twelve.

### 3.2 ⚠ The IMU reset line has to go somewhere

**The MCP23017 is not only an encoder expander.** `config.py:114` sets
`IMU_RST_MCP_PIN=12` — the BNO085's RST lands on MCP23017 port B bit 4, confirmed 2026-08-08,
and `sensors.py:120` calls `mcp.get_pin()` on it. Remove the chip without rehoming that line
and the IMU loses its reset.

**Rehome it to a Pi GPIO, not to Pico-E.** The IMU is a reflex-layer sensor feeding the tilt
check; its ability to be reset must not depend on a second MCU being alive. **`GP7` is the
natural choice** and frees up in exactly this change — it is `config.ENCODER_INT_PIN` today,
reserved for an MCP23017 INTA wire that was never landed and whose design was retracted.

Note the SPI0 interaction: `dtparam=spi=off` must stay off, or the kernel reserves GP7–GP11
at boot and `GPIO.setup()` fails with `lgpio.error: 'GPIO busy'` — the fault that
crash-looped the service for a day on 2026-08-20. Verify with
`sudo cat /sys/kernel/debug/gpio | grep spi0` before using GP7 for anything.

`config.py`'s validator currently checks `IMU_RST_MCP_PIN` for collisions against
`ENCODER_PINS`. That check becomes meaningless when both leave; replace it with a check that
the new IMU reset pin does not collide with any other BCM assignment.

### 3.3 Pinout

Twelve signal lines plus supply. Encoder colour scheme, per Master Hardware Design: Red =
Motor+, White = Motor−, Blue = Enc VCC, Black = Enc GND, **Yellow = Phase A, Green = Phase B**.

| Wheel | Phase A (yellow) | Phase B (green) | PIO SM |
|---|---|---|---|
| lf | GP2 | GP3 | PIO0 SM0 |
| lm | GP4 | GP5 | PIO0 SM1 |
| lr | GP6 | GP7 | PIO0 SM2 |
| rf | GP10 | GP11 | PIO1 SM0 |
| rm | GP12 | GP13 | PIO1 SM1 |
| rr | GP14 | GP15 | PIO1 SM2 |

Six SMs of twelve used; PIO2 free. A/B pairs are **adjacent and A-even** because the standard
PIO quadrature program reads two consecutive pins with one `in pins, 2`.

UART to the Pi on GP0 (TX) / GP1 (RX) — UART0, and note these are the Pico's GP0/GP1, which
have nothing to do with the *Pi's* GP0/GP1 (those are reserved for the AI HAT EEPROM and must
stay untouched).

⚠ **Motor− (white) never lands on a Pico GPIO, for exactly the reason it never lands on an
MCP23017 GPIO.** A motor lead on a logic pin destroyed the first MCP23017. It goes to a
FeatherWing motor terminal.

⚠ **Meter the crimps before trusting wire colour.** Five of six motors have still not been
checked against the corrected colour scheme, and batch variation is documented. This design
does not change that — it just makes getting it wrong cost a Pico instead of an MCP23017.

### 3.4 Decode

One PIO state machine per wheel running a standard 4× quadrature program: sample both lines,
index a transition table, increment or decrement a counter held in a scratch register, and
push accumulated counts to the FIFO. Core 0 drains the FIFOs, computes per-wheel rate over a
fixed window, and emits a frame at **50 Hz**.

**The margin is enormous and that is the point.** FRD G-2 computes ~7,770 Hz per channel at
620 RPM output. A PIO SM clocked even at 15 MHz samples ~2,000× faster than that. The 8×
oversubscription that makes the current polled decode alias to a constant simply stops being a
consideration — and, critically, the Pi no longer needs `dtparam=i2c_arm_baudrate=400000`,
the alternative G-2 proposed, which would have raised the speed of a bus this rover has
already had to debug for two solid days.

Rate is computed on the Pico over a fixed window and shipped, rather than differenced on the
Pi, so `counts_per_sec` no longer depends on Linux scheduling jitter. `Encoders.stalled()` —
the Directive 5 consumer at `brain.py:449` — compares that rate against 1.0, so its input
becomes deterministic.

### 3.5 ⚠ Degraded mode: what happens while Phase B is dead

Today, Phase B is silent on all six wheels. A quadrature decoder fed one live channel and one
dead one produces **nothing** — the transition table sees no valid transitions. So the
firmware must detect the condition rather than report zero.

**Startup probe, then a declared mode.** After boot, for each wheel: if channel A produces
transitions while channel B produces none over N counts of A, that wheel enters
`MODE_SINGLE`. The `<mode>` field in the frame carries a 6-bit mask of which wheels are in it.

In `MODE_SINGLE` the firmware counts **A edges only** and reports magnitude with **no sign**.

What that buys and what it does not:

- ✅ **Stall detection keeps working.** `stalled()` only asks whether the magnitude of the
  rate is near zero while commanded. A-only counting answers that correctly.
- ✅ **Distance keeps working**, to whatever accuracy the unmeasured counts-per-rev allows.
- ❌ **Direction does not.** A wheel being dragged backwards reads identically to one driven
  forwards.

🔴 **Do not paper over this by taking the sign from the commanded direction.** It is the
obvious move and it is wrong: it makes the encoder confirm whatever the motor was told to do,
which destroys the one thing odometry is for — detecting that the wheel did *not* do what it
was told. If `MODE_SINGLE` is set for a wheel, `odometry.py` must be told that wheel's sign is
unknown, and the mode mask must surface in `diagnostics.py`. **A measurement that agrees with
the command by construction is not a measurement.**

`MODE_SINGLE` is a limp-home state, not a destination. The exit is tracing the green wires.

### 3.6 Software interface

The existing `sensors.py::Encoders` API is already the right shape — the Gap Analysis says so
explicitly, predicting that an RP2040 swap "looks like a backend swap behind the existing
interface, not a rewrite". Keep it exactly:

```python
counts          -> dict[wheel, int]      # FR-500-001
counts_per_sec  -> dict[wheel, float]    # FR-500-002
stalled(w, cmd) -> bool                  # FR-500-003, Directive 5
is_healthy      -> bool
```

- New class `PicoEncoders` in `sensors.py`, same five members, no new ones.
- `config.ENCODER_BACKEND = 'mcp23017' | 'pico'`, defaulting to `'mcp23017'` until Pico-E is
  built and bench-passed. The MCP23017 path **stays in the tree as a working fallback** —
  the same pattern `vision.py` already uses for the CPU/ultralytics path.
- Transport isolated in one thin function at the bottom of the module, mirroring
  `tof.read_frame()`, so the frame parser and every rule above it are testable with no
  hardware and no `pyserial` installed.
- `is_healthy` keeps its existing contract — a staleness flag, `(now - last_ok) < 1.0` —
  now measured against frame arrival. `brain.py:311` already escalates it.

### 3.7 Tests to add

- Frame parser: valid frame, bad CRC, short frame, garbage, partial line across two reads.
- Sequence reset detected and logged as a reboot, not absorbed.
- `MODE_SINGLE` mask propagates to `odometry.py` as unknown-sign, and never as a
  command-derived sign.
- Interface equivalence: `PicoEncoders` and `Encoders` satisfy the same contract test.
- `test_expected_i2c_agreement.py` passes with 0x27 removed, and the expected count is ten.

---

## 4. Part B — Pico-S, the sonar coprocessor

Takes the three HC-SR04s off the Pi's GPIO. **This is the reflex path, and it is the half of
this design that can make the rover less safe if it is done casually.**

### 4.1 The rule that governs this board

`CLAUDE.md`: *"An obstacle stop must never depend on a detection frame arriving."*

That was written about the NPU, where the rule is satisfiable by simply never letting vision
gate the stop. **Here it cannot be satisfied that way**, because after this change the sonar
frame *is* how the obstacle is known. The rule therefore has to be re-satisfied differently:

> **Silence must produce a stop, not a "clear".**

Everything in §4.4 and §4.5 follows from that one sentence. If a future change makes a missing
frame behave like an unobstructed path, this design has failed and should be reverted.

### 4.2 Pinout

| Position | TRIG | ECHO (via existing 1k/2k divider) | PIO SM |
|---|---|---|---|
| Front (centre) | GP2 | GP3 | PIO0 SM0 |
| Left | GP4 | GP5 | PIO0 SM1 |
| Right | GP6 | GP7 | PIO0 SM2 |

UART to the Pi on GP0 (TX) / GP1 (RX). There is no rear sonar; there never was.

Keep the dividers. Keep TRIG at 3.3 V. Both are already verified working (S-1, 2026-09-17:
front 49.7 cm, left 91.1 cm, right 30.9 cm, each stable to ±0.4 cm over 8 samples, no
cross-talk).

### 4.3 Ranging cycle

Sequential, never simultaneous — one sensor at a time, so a neighbour's burst cannot be
mistaken for an echo. Fixed **60 ms** cycle: trigger, measure, settle, advance. Full
three-sensor sweep at ~16 Hz, streamed as one frame per sweep.

That is *faster* than today. `SonarArray._loop` currently takes three median-of-three
readings with a 16.7 ms gap between sensors, putting a full sweep somewhere around 100–200 ms
(5–10 Hz) and worse when any channel times out — and the whole thing competes for the GIL
with everything else on the Pi.

Pulse width is measured by a PIO SM with a counter, giving sub-microsecond resolution that
does not move when Hailo runs an inference. **Timing accuracy stops being a function of
system load**, which is the real reason to do this at all.

Median-of-N filtering moves onto the Pico and out of `Sonar.read()`.

### 4.4 ⚠ Status codes — the fail-dangerous case this fixes

`sensors.py::_ping()` returns `999.0` on both of its timeout branches. `999.0` is far past
`DIST_CLEAR=60`, so it reads as "nothing anywhere near me" — and it is returned both when
there genuinely is no target and **when the echo line never goes high, or never comes back
down.** A sensor with a cut echo wire, a stuck-high line or a dead transducer currently reports
maximum confidence in a clear path.

The Pico separates the cases, because it can see the difference:

| Status | Meaning | Pi-side treatment |
|---|---|---|
| `OK` | echo returned within the window | distance is valid |
| `NO_TARGET` | trigger sent, no echo within max range | clear, out to max range |
| `NO_ECHO` | echo line never rose at all | **fault** — sensor or wiring |
| `STUCK` | echo line rose and never fell within the window | **fault** — stuck line |

`NO_TARGET` is the only one of the three non-`OK` codes that means "clear". The other two are
faults, and `brain.py` should treat a sustained fault on the **front** channel the way it
treats any other sustained sensor fault — through `_check_health()`'s existing
`SENSOR_FAULT_GRACE_S=1.0` path, which already exists and already stops the rover.

### 4.5 ⚠ Staleness, and the rule that must not be copy-pasted from the ToF

`tof.py` states: **"UNAVAILABLE IS NOT A FAULT"** — a dropped UART means fall back to sonar
alone and log it. That rule is correct *for the ToF*, because the ToF is supplementary and
sonar is underneath it.

🔴 **That rule is wrong for Pico-S and must not be carried over.** Nothing is underneath
sonar. There is no fallback. For this board, **unavailable IS a fault.**

Concretely:

- `SonarArray` gains `is_healthy` — which it does not have today — and `brain.py:425`'s
  checks dict gains a `'sonar'` key alongside imu/encoders/current/battery_adc.
- A frame older than a small multiple of the 60 ms cycle makes `distances` report
  **`front = 0.0`**, not the last good value and not `999.0`. Zero is below `DIST_STOP=20`,
  so the existing reflex logic stops the rover with no new state, no new threshold and no new
  branch — the same "fail-safe by construction" argument the ToF fusion already makes for
  `min()`.
- Sides degrade to `0.0` on the same rule, making `better_side()` refuse to recommend a turn
  into unknown space.
- Never hold the last good reading forward. A stale distance is the one output that is
  actively worse than no output.

### 4.6 Software interface

`SonarArray`'s public surface is consumed in several places and by the ToF fusion, so keep it
byte-identical:

```python
distances       -> {'front': float, 'left': float, 'right': float}
obstacle_ahead()-> bool
should_slow()   -> bool
better_side()   -> str
tof             -> ToFSensor | None
is_healthy      -> bool            # NEW
```

**The ToF fusion point does not move.** `distances` stays THE fusion point, `min()` stays the
whole design, and the ToF keeps pulling `front` down and never up. A `PicoSonarArray` that
changed that would break `test_sonar_tof_fusion.py`, and should.

`config.SONAR_BACKEND = 'gpio' | 'pico'`, defaulting to `'gpio'`. The direct-GPIO path stays
in the tree.

### 4.7 Tests to add

- **Staleness → `front = 0.0` → `obstacle_ahead()` is True.** This is the load-bearing test
  of the whole design; name it so nobody deletes it as redundant.
- `NO_ECHO` and `STUCK` produce a health fault, and `NO_TARGET` does not.
- ToF fusion still holds over the Pico backend: an available ToF pulls `front` down, an
  unavailable or uncalibrated one never raises it.
- `better_side()` does not recommend a side whose reading is stale.
- Interface equivalence between `SonarArray` and `PicoSonarArray`.

---

## 5. Pin and UART budget

> **REVISED 2026-09-20 — the owner proposed putting one Pico on the Pi 5's dedicated UART
> ("service") connector, and it changes this section's conclusion.** ~~Part B pays for Part
> A's link, which is the strongest argument for doing both rather than either.~~ That was true
> only while the 40-pin header was the sole source of UARTs. **The service port decouples
> them**, and §5.2 is now the recommended assignment.

### 5.1 The 40-pin header, and why it deadlocks

Pi UARTs on the 40-pin header, current state:

| Overlay | Pi GPIO | Device | Status |
|---|---|---|---|
| `uart0` | GP14/15 | `/dev/ttyAMA0` | **Blocked** — GP14 is left sonar ECHO, GP15 is the BNO085 interrupt |
| `uart1-pi5` | GP0/1 | `/dev/ttyAMA1` | **Reserved** — AI HAT EEPROM, do not use |
| `uart2-pi5` | GP4/5 | `/dev/ttyAMA2` | **Blocked** — GP4 right TRIG, GP5 front TRIG |
| `uart3-pi5` | GP8/9 | `/dev/ttyAMA3` | **In use** — SEN0628 ToF, verified 2026-09-15 |
| `uart4-pi5` | GP12/13 | `/dev/ttyAMA4` | **Blocked** — GP13 is left TRIG |

**Every free UART on this header is blocked by a sonar pin.** Note the shape of that: it is
not that the header is full, it is that the three sonars happen to sit on three different
UARTs' pins. Moving the sonar to Pico-S frees GP4, GP5, GP13, GP14, GP21 and GP26 in one
stroke, unblocking `uart2-pi5` and `uart4-pi5` together — but it means **Pico-E has nowhere to
land until Pico-S is done**, which forces the more-broken subsystem to wait on the less-broken
one.

GP7 additionally frees when the MCP23017 leaves, and §3.2 spends it on the IMU reset.

### 5.2 The service port breaks the deadlock — recommended

The Pi 5 has a **dedicated 3-pin UART connector** on the board (JST-SH 1.0 mm: TX, RX, GND,
no power), separate from the 40-pin header and from everything in §5.1. It is the Pi's debug
/ service console port. **Nothing in this repository currently mentions it, and nothing on
this rover uses it.**

That makes it a free UART that costs zero header GPIO, and it changes the build order:

| Board | Link | Device | Depends on |
|---|---|---|---|
| **Pico-E** (encoders) | **Service port** (3-pin UART connector) | `/dev/ttyAMA10` — **verify** | nothing |
| **Pico-S** (sonar) | `uart2-pi5`, GP4 TX / GP5 RX | `/dev/ttyAMA2` | frees its own pins in the same rewire |

**Pico-E takes the service port, not Pico-S.** Three reasons, and the order matters:

1. **Pico-S is the reflex path and belongs on the most boring connector available.** A 1.0 mm
   JST-SH on the board edge is the most mechanically fragile connection on this rover, which
   has already lost time to a loose servo connector, a loose base-side power connector, and
   two connectors reassembled with reversed polarity. Put the obstacle sensor on a 0.1" header
   with the rest of the build.
2. **The failure modes are asymmetric.** A service-port cable working loose on Pico-E drops
   odometry and stall detection — `is_healthy` goes False and `brain.py:311` escalates it. The
   same cable on Pico-S would trip §4.5's staleness rule and stop the rover, so a wiggly
   connector becomes a phantom obstacle that halts Willie mid-session.
3. **Pico-S frees its own pins anyway.** It was never the blocked one — moving the sonar off
   GP4/GP5 and using GP4/GP5 for the link is a single atomic rewire. Only Pico-E was stuck.

### 5.3 ⚠ What using the service port costs, and the check to make first

**It is the recovery console**, and this rover has a history that makes that worth something:
196 restarts masquerading as flaky hardware; the SPI0 fault that killed the process with a
different signal each time; and the 2026-09-07 watchdog attempt that hit SIGABRT ~500 ms after
every start and **never reached its own first log line**. That last one is exactly the case
where a serial console is the only instrument left, because there is nothing in the logs yet.

**But it may already be disabled, in which case this costs nothing.** Master Hardware Design
§9 disables the console via `raspi-config` → Interface Options → Serial Port, **answering no to
both prompts** — which turns off the login shell *and* the serial hardware. Whether that also
cleared the Pi 5 debug connector has never been recorded either way.

**So check before deciding, rather than assuming in either direction:**

```
ls -l /dev/ttyAMA*                      # is ttyAMA10 present?
cat /boot/firmware/cmdline.txt          # any console=serial0 / console=ttyAMA10 ?
systemctl list-units 'serial-getty@*'   # any login shell attached?
grep -E 'enable_uart|uart' /boot/firmware/config.txt
```

- **Console already off** → take the port, note in §10 that it is now spoken for, and keep a
  USB-TTL adapter with the rover for the day it is needed.
- **Console still live** → this is a real trade. Decide it deliberately and write down that it
  was decided; do not let it be discovered later by someone who needed it at 2am.

Either way: all four USB ports are occupied, so reaching the console already means unplugging
something. It is an emergency instrument, not a daily one — which is part of why spending it
on Pico-E is defensible and spending it on Pico-S is not.

### 5.4 Verifying the overlays

🔴 **VERIFY THE OVERLAY NAMES BEFORE WIRING ANYTHING.** The `-pi5` suffix is not cosmetic and
getting it wrong is **silent**: `config.txt` looks right, the board boots clean, and the device
reads as dead hardware on the wrong pins. This cost a session on 2026-09-15, when `uart3`
(GPIOs 4–7, BCM2711, a Pi 4 part) was used where `uart3-pi5` (GPIOs 8–9, Pi 5 only) was meant.

The mapping above is **extrapolated from that one verified data point** and must be confirmed
on the rover, not trusted from this table:

```
ls /boot/firmware/overlays/ | grep uart
dtoverlay -h uart2-pi5          # expect: GPIOs 4-5, Pi 5 only
sudo cat /sys/kernel/debug/gpio | grep spi0     # must be empty
```

After a reboot, `/dev/ttyAMA2` exists and `sudo pinctrl get 4-5` shows the alt-function
TXD/RXD names.

**The service port needs no overlay at all** — it is a dedicated UART, not a pinmux of header
GPIO, which is precisely why it sidesteps this whole class of mistake. Its device node still
has to be confirmed (§5.3), but there is no `dtoverlay` line to get wrong. `uart4-pi5` is no
longer used by this design; it stays free.

**And `pinctrl` settles "is it even connected?" without a meter**, the same trick that
separated "sensor absent" from "sensor present but mute" three times on 2026-09-15: force a
pull-down on the Pi's RX pin and re-read. Still high means something is actively driving it,
i.e. the Pico is powered and its TX is alive.

---

## 6. Migration order

> **REVISED 2026-09-20 alongside §5.** ~~Pico-S first, then Pico-E — counter-intuitive, since
> the encoder problem is more broken, but Pico-S frees both UARTs so Pico-E has nowhere to land
> until it is done.~~ **With the service port (§5.2) that ordering constraint is gone.** The two
> boards are now independent and can be built in either order, or in parallel by two people.

**Recommended: Pico-E first**, because the encoder subsystem is the more broken one and no
longer has to wait its turn. Pico-S is a self-contained rewire whenever you want it.

**Step 0, before either, and independent of both: trace the green wires.** If Phase B is
recoverable, Pico-E ships with a real quadrature decoder instead of living in `MODE_SINGLE`
(§3.5). This is still the highest-value item on the whole list and none of the rest of it
substitutes for the work.

### Track E — Pico-E, on the service port

**E0.** Confirm the service port is free and decide the console trade, per §5.3.
**E1.** **Rehome the IMU reset to GP7** (§3.2) and confirm the BNO085 still resets. Do this
*before* pulling the MCP23017, so a failure has exactly one possible cause.
**E2.** Bench Pico-E off-rover, driving the A/B lines from a signal generator or a spare motor
on a bench supply. Prove the decode against a known edge count before it sees a wheel.
**E3.** Fit Pico-E and wire the service port, but keep `ENCODER_BACKEND='mcp23017'`. Log both
sources side by side for a full session — they read the same six encoders and should agree.
**E4.** Flip `ENCODER_BACKEND='pico'`. The MCP23017 path stays in the tree.
**E5.** Pull the MCP23017 and drop `ENCODER_ADDR` from `config.py`. **Expect ten devices**, and
let both `_EXPECTED_I2C` sets derive from config rather than editing them separately (§3.1).
**E6.** Re-run E-1, including counts-per-rev — which is measurable only if step 0 above (the
green wires) succeeded. If it did not, record the `MODE_SINGLE` mask instead and leave
counts-per-rev blank rather than filling it from a single-channel count.

### Track S — Pico-S, on `uart2-pi5`

**S1.** Bench Pico-S off-rover: three HC-SR04s, a bench supply, a tape measure. Prove a stable
multi-minute stream before it goes anywhere near the reflex path — the standing rule from the
SEN0628, where one reviewer in six had a board reset-looping on current firmware.
**S2.** Fit Pico-S and move the three sonar harnesses to it, freeing GP4/GP5/GP13/GP14/GP21/GP26
in one rewire. Bring up `uart2-pi5` on the now-free GP4/GP5 and confirm it per §5.4.
**S3.** Keep `SONAR_BACKEND='gpio'` — which is now reading pins with nothing on them, so this
step is a stream-to-a-logging-script comparison against the *bench* figures from S1, not
against a live GPIO path. **This is the one ordering trap in Track S:** the moment the
harnesses move, the old backend stops being a reference. Capture the comparison data before
S2, not after.
**S4.** Flip `SONAR_BACKEND='pico'`. Re-run S-1 against a tape measure, and run P-1's staleness
test (§9) — pull the UART and confirm the rover stops.

### Both tracks

**Rollback is a config flag and a re-plug** at every step, because both old paths stay in the
tree. Do not delete either until E-1, S-1, P-1 and P-2 have all been re-run and passed on the
new backends.

Nothing in Track E depends on anything in Track S, or vice versa. They share only the §2
conventions — frame format, power, watchdog — which is the reason to settle those first and
not per-board.

---

---

## 7. CPU and power headroom

> ⚠ **Every figure in this section is DERIVED FROM READING THE CODE. None of it is measured.**
> It is written here because the arithmetic is worth having before the bench session, not
> because it is evidence. §7.4 is how it becomes evidence. Treat these numbers the way this
> repo treats any other plausible-looking figure that nobody observed.

**Short answer: yes, substantially — and almost all of it is the sonar half, not the encoders.**

### 7.1 What is spent today

**Sonar dominates, and it costs the most when nothing is happening.**

`sensors.py::_ping()` is two **busy-wait spin loops** in Python — one waiting for ECHO to rise,
one waiting for it to fall, each polling `GPIO.input()` and `time.perf_counter()` as fast as
CPython manages. This is not a sleep and it is not a blocking read; it is a hot loop at
essentially 100% of a core for its whole duration.

`requirements.txt` makes it more expensive than it looks: `RPi.GPIO` here is **`rpi-lgpio`**,
the Pi 5 drop-in, so each `GPIO.input()` is an **ioctl syscall** rather than a memory-mapped
register read. The spin is paying kernel entry/exit on every iteration.

How long it spins, per ping — ~0.46 ms for the HC-SR04 to raise ECHO, then the echo-high time,
which is the round trip `2d/343`:

| Nearest surface | ECHO high | Spin per ping |
|---|---|---|
| ~0.5 m | 2.9 ms | ~3.4 ms |
| ~2 m | 11.7 ms | ~12.2 ms |
| nothing in range | — | **25 ms** (`SONAR_TIMEOUT`) |

A full sweep is 3 sensors × `SONAR_SAMPLES=3` = **nine pings**, plus 3 × `SONAR_INTERVAL/3`
= 50 ms of actual sleep:

| Scene | Spin per sweep | Sweep period | Duty on one core |
|---|---|---|---|
| Everything close (~0.5 m) | ~31 ms | ~81 ms | **~38%** |
| Typical room (~2 m) | ~110 ms | ~160 ms | **~69%** |
| Open space / no return | ~230 ms | ~280 ms | **~82%** |

🔴 **Note which way that runs.** The clearer the path, the longer the echo takes to come back,
and the longer the loop spins. **The current design burns the most CPU when there is nothing
to see** — which is most of a roam session, and exactly when Willie should be cheapest.

**Encoders cost less but wake more.** The poll loop is ~1 kHz of `_update()` + `sleep(0.001)`.
Each `_update()` is two `smbus2` register reads, where the thread is **blocked in the I²C
driver rather than spinning**, so the CPU cost is mostly CPython overhead — call it 2–3% of a
core. The subtler cost is **~1000 timer wakeups per second**, which keeps the package out of
deeper idle states continuously.

**One aside the Pico also fixes.** `_ping()` opens with `time.sleep(0.000002)` and
`time.sleep(0.00001)` to shape a 10 µs TRIG pulse. Linux cannot honour a 2 µs sleep — the
nanosleep floor plus scheduler granularity puts the real pulse somewhere in the tens to
hundreds of microseconds, and jittery. The HC-SR04 wants *at least* 10 µs so this is harmless
in practice, but it is two syscalls per ping, and on a PIO state machine the pulse becomes
exact for free.

### 7.2 What replaces it

Pico-E streams at 50 Hz, Pico-S at ~16 Hz. Per frame the Pi does one buffered serial read, a
`split(',')`, a handful of `int()` calls, and a CRC check.

⚠ **The CRC must be table-driven, or it quietly eats the saving.** CRC-16-CCITT computed
bitwise over a ~60-byte frame is ~480 CPython loop iterations, roughly 150 µs; at 50 Hz that
is ~0.75% of a core spent checksumming. A 256-entry lookup table makes the same frame ~20 µs,
about 0.1%. §2.6 chose ASCII framing for debuggability on the argument that the cost is
negligible — **that argument holds only with the table.**

Total added, both links: **under 1% of one core.**

### 7.3 Net, and what it is actually worth

**Removes an estimated 0.4–0.8 of a core; adds under 0.01.** But be precise about what that
buys, because it is easy to oversell:

- **The Pi 5 has four cores.** Freeing most of one does not make anything single-threaded
  faster. What it buys is *headroom*, and headroom only matters where something is currently
  contending.
- **Where it does contend:** `TICK_OVERRUN_THRESHOLD_S=0.15` and `vision.py::detect()` running
  **synchronously on the tick thread** — `CLAUDE.md` explicitly flags watching for
  `TICK_OVERRUN` during the first mapping/pursuit session. A sonar thread spinning 110–230 ms
  out of every sweep is competing with exactly that.
- **GIL — and this is the part I cannot resolve from the code.** Whether `rpi-lgpio` releases
  the GIL around its ioctl is not something this repo records and I have not verified it. If it
  does **not**, the spin loop is blocking every other Python thread for its whole duration and
  the real win is considerably larger than the CPU percentage suggests. **Worth settling with
  `py-spy` during §7.4 rather than assuming either way.**
- **Power, weakly.** Dropping from ~1000 wakeups/sec plus a near-continuous spin to ~66 serial
  reads/sec improves idle residency. The 5 V rail's worst case is already near 9 A against an
  8 A UBEC, and `WHISPER_CPU_THREADS=3` was capped **specifically to keep peak draw off that
  rail** — so this moves the right way, on a rail with no margin. It is a second-order effect,
  not a headline.

### 7.4 ⚠ Measure the baseline BEFORE the migration

```
# per-thread CPU, named threads
ps -L -o tid,pcpu,comm -p $(pgrep -f 'venv/bin/python3 main.py')
top -H -p $(pgrep -f main.py)

# where the time actually goes, and whether the GIL is held
py-spy top    --pid $(pgrep -f main.py)
py-spy record --pid $(pgrep -f main.py) -d 60 -o before.svg

vcgencmd measure_clock arm ; vcgencmd get_throttled
grep -c TICK_OVERRUN <the day's log>
```

Take it in all three scenes from §7.1 — nose to a wall, normal room, and pointed at open space
— because the spread between them *is* the finding. One number from one scene proves nothing.

🔴 **This has to happen before Track S touches the harnesses.** The moment the sonar leaves the
Pi's GPIO there is no baseline left to compare against, and the CPU claim in this section
becomes permanently unverifiable. Same ordering trap as §6's Track S step S3, for the same
reason.

## 8. Interaction with the systemd watchdog

Both Picos add startup time: two serial opens, two `ID?` handshakes, and a wait for the first
valid frame from each.

`WatchdogSec` is currently commented out in `willy-rover.service` and **the watchdog has never
run on this rover.** Before it is ever re-armed, `Type=notify` (or `NotifyAccess=main`) must be
set — with `Type=simple`, systemd discards every `sd_notify` and the watchdog fires on a timer
regardless of value, which is what crash-looped the rover on 2026-09-07. And under
`Type=notify`, `WatchdogSec` doubles as the **startup** deadline.

So: **measure startup again after this change** (`scripts/measure_startup.py` exists) and feed
the new figure into W-1. Init already loads a 1.7 GB Hailo HEF plus vision and voice models;
two more serial handshakes are small, but W-1's number is currently unmeasured and this makes
it staler.

---

## 9. Bench procedures to add

To be appended to `WildWilly_Bench_Test_Procedures.md` in that document's format, with
**result fields blank until someone runs them.**

**P-1 — Pico-S sonar coprocessor.** Stream stability over ≥10 minutes with zero CRC failures
and no sequence resets; three distinct distances against a tape measure at 20/50/100 cm on each
channel; `NO_ECHO` raised within one cycle of unplugging a sensor; `STUCK` raised on a shorted
echo line; **and the staleness test — pull the UART and confirm the rover stops** rather than
reporting clear.

**P-2 — Pico-E encoder coprocessor.** Counts tracked against a marked wheel over a known number
of turns, at low and at full commanded duty, to settle counts-per-rev *and* to prove the
under-sampling is gone; `MODE_SINGLE` mask correct per wheel; `stalled()` raised within
`STALL_GRACE_S` of a blocked wheel; ten-device roll-call after the MCP23017 is pulled.

**Do not hand-turn the wheels for P-2.** The encoder is on the motor shaft behind the 17.1:1
gearbox and does not back-drive — 30 s of hand-turning produced one distinct pin state while
3 s of driving produced seven. Any encoder measurement must be taken under power. Note this
also makes `scripts/encoder_calibration.py` invalid as written, since it is built on
hand-turning; it needs rewriting before P-2 can use it.

---

## 10. Documents that must be updated IF this is built

Per the standing rule — *when you change a constant, a part, an address, a revision or a
decision, `grep -rn` the OLD value across the whole repo before calling it done.*

**Nothing in this list should be touched until the hardware exists.** It is recorded now so
that the sweep is a checklist rather than an archaeology exercise later.

| Old fact | Where it is asserted |
|---|---|
| `i2cdetect` returns **eleven** devices | `CLAUDE.md` roll-call, `brain.py::_EXPECTED_I2C`, `diagnostics.py::_EXPECTED_I2C`, FRD §V FR-100 row, Master Hardware Design §11.2 |
| MCP23017 @ 0x27 is the encoder expander | `CLAUDE.md` roll-call + pitfalls, `config.py:194`, `sensors.py:288` docstring, Master Hardware Design §9.1, Software Design S-2 |
| `IMU_RST_MCP_PIN=12` | `config.py:114`, `config.py:949` validator, `sensors.py:120`, `tests/test_config_validate.py` |
| `ENCODER_INT_PIN` = GP7, awaiting an INTA wire | `CLAUDE.md` pin table, `config.py` |
| Sonar TRIG/ECHO are Pi BCM pins | `CLAUDE.md` pin table, `config.py:84-86`, `config.py:930` validator, Master Hardware Design §8.1/§16.13 |
| GP14 hazard: serial console must stay disabled | `CLAUDE.md` — the *hazard* goes away, but GP14 still must not host a console while anything else needs it |
| "No RP2040 exists on this unit" | `docs/WildWilly_Claude_Fix_Gap_Analysis.md` row 7 |
| Item 7 is an unimplemented planned architecture | `docs/WildWilly_Claude_Fix_Implementation_Plan.md` §7 |
| G-2: raise `i2c_arm_baudrate` if polling is too slow | FRD v3.1 G-2 — **superseded by this design**, which removes the poll entirely |
| Encoder polling ceiling ~1 kHz, 1 ms sleep protects the bus | `sensors.py:353` comment block |
| `ENCODER_COUNTS_PER_REV=752` is derived, not measured | `config.py:222`, FRD G-2, Software Design S-2 — **still true**, and not fixed by this design |
| The serial console is disabled and the Pi 5 service port is unclaimed | `CLAUDE.md` pin section, Master Hardware Design §9 and §16.13, FRD v3.1's left-sonar-garbage signature note — **the service port is not mentioned anywhere today**, so claiming it for Pico-E means *adding* the fact, not correcting one. Record which console state was chosen and why (§5.3) |

**Strike, don't delete.** The MCP23017 and direct-GPIO sonar entries stay visible with a
marker and a date once superseded, so neither gets re-fitted next month.
