# WildWilly / willy-rover

Six-wheel rocker-bogie autonomous rover. Raspberry Pi 5 host, 5-DOF arm, and a
**single non-isolated I²C segment** — one VCC, one GND, one SDA, one SCL. The
ISO1540 came out on 2026-09-08 and there is no isolation and no second rail
domain; see the roll-call below. Hardware is 100% built as of 2026-08-14; the
phase now is **live verification, not construction**.

This file records hardware facts and pitfalls that cannot be derived from the
code. Where code and this file disagree, assume the hardware is right and the
code needs fixing — every line below was confirmed on the bench.

---

## When a fact changes, grep for the old one

**The dominant defect in this project's documentation is not wrong writing. It is
correct writing left in place.** A constant gets corrected, a part gets removed, a
decision gets closed — and the edit lands where someone happened to be looking while
a paragraph two sections away goes on asserting the old state, indefinitely.

Three review passes on 2026-09-11/13 found the same species repeatedly:

| Changed | Still said the old thing, and for how long |
|---|---|
| ISO1540 removed 2026-09-08 | §1's bus row, §9's pin table, §12 rule 3, §13's roll-call, the BOM, and two FRD sections — some for weeks |
| `ENCODER_COUNTS_PER_REV` 3292 → **752**, 2026-08-25 | Software Design S-2 *and* FRD G-2, both still arguing from the dead figure on 2026-09-13 — and both reached a **wrong conclusion** because of it |
| INA260 Pi rail 0x44 → **0x45**, 2026-08-28 | FRD §V's row, which a consistency pass had already been through |
| Cliff sensors dropped, ToF part changed, mux withdrawn | §6.5's own fusion paragraph, two paragraphs below the withdrawal |
| Four FRD requirements added | A header still claiming none had been |

**So: when you change a constant, a part, an address, a revision or a decision,
`grep -rn` the OLD value across the whole repo before calling it done.** Not the file
you are in. All of them — the three design docs, `CLAUDE.md`, the user guide, the
specs, and the code. It takes seconds and it is the only thing that reliably catches
this.

Two habits that make it stick:

- **State what is true now. History lives in `git log`.** The design docs carry no
  strikethrough and no correction narrative — a reader acting on them should find the
  current answer, not have to work out which of three paragraphs is live. Keep the
  *durable* part of a correction (the mechanism, the trap, the lesson that generalises)
  and drop the account of who believed what when. `git log` and `git blame` hold that
  losslessly, and nobody has to read past it.
  - **Removed hardware is the one exception worth keeping**, because history is what stops
    a part being re-fitted next month. Keep it to a short, clearly-labelled note — the
    part, the date, and *why* — not a running commentary.
  - **A correction is not done until you have grepped for the old value.** That is the rule
    above, and dropping the narrative does not soften it — it makes it matter more, because
    there is no longer a struck line left behind as a breadcrumb.
- **Prefer the artifact to the document.** When two documents disagree, read the
  code, the config, or the file itself — not the more recent doc. On 2026-09-13 a
  review concluded the hardware doc was right and the software doc stale about the
  `CLAUDE.md` repoint; reading `CLAUDE.md` showed the reverse. `config.py` settled
  the INA260 address and the encoder constants the same way.

---

## Bus topology and roll-call — AS-BUILT, verified 2026-09-08

**The bus is no longer isolated.** The ISO1540, the VCC2/GND2 isolated rail and
the Seengreat breakout HAT + ribbon are out of the build. **The TPSM84205 is a
different case: it is still physically fitted, just unused** (owner-confirmed
2026-09-09) — expect to find the part on the board, not an empty footprint. The
AMS1117-3.3 cannot be in service either, since its only input was the TPSM's
now-dormant 5V output. The TPSM84203EAB single-stage variant was never built. Everything now hangs off the Pi's
own I²C on `/dev/i2c-1`:

```
Pi 40-pin header (GP2/GP3)
  ├─ Witty Pi 5 HAT+                    0x51
  └─ GODIY I²C hub ── GODIY I²C hub    (passive, daisy-chained)
        └─ all remaining devices + LTC4311 accelerator
```

Both hubs are passive fan-outs, so this is **one electrical segment** — there is
no segmentation and no containment. A single device holding SDA or SCL low takes
the whole bus down, which is exactly what happened repeatedly on 2026-09-07/08.

A TCA9548A multiplexer (strapped `0x74`) was bought, wired and proven working
during that debugging, then removed in favour of this simpler topology. It is on
the shelf if segmentation is ever wanted; `dtoverlay=i2c-mux,pca9548,addr=0x74,
base=20,disconnect_on_idle` is still in `config.txt` and harmlessly fails to
probe at boot.

### Roll-call

`i2cdetect -y 1` returns **eleven devices plus one broadcast address**, verified
2026-09-08 across 20 consecutive scans with zero bus errors:

| Addr | Device | Notes |
|------|--------|-------|
| 0x27 | MCP23017 | Encoder expander, 6 channels. **Waveshare board** |
| 0x40 | INA260 | R2, 5V rail — steering servos, sonar VCC, Pi screen |
| 0x42 | PCA9685 | Steering servos, CH0–CH5 |
| 0x43 | PCA9685 | Arm servos, CH0–CH6 (CH7 unused, remapped 2026-09-06) |
| 0x44 | INA260 | **R3, 6V arm servo rail** — corrected 2026-09-15 |
| 0x45 | INA260 | **+12V bus → both FeatherWing VIN** — corrected 2026-09-15 |
| 0x48 | ADS1115 | Battery voltage ADC, A0. **See the divider pitfall below** |
| 0x4A | BNO085 | 9-DoF IMU |
| 0x51 | Witty Pi 5 HAT+ | On the Pi header, its own power domain |
| 0x60 | FeatherWing | Motor driver, **RIGHT** side — measured M-1, 2026-09-18 |
| 0x61 | FeatherWing | Motor driver, **LEFT** side — measured M-1, 2026-09-18 |

**0x70 is NOT a device.** It is the PCA9685 All-Call broadcast address and
answers whenever either PCA9685 is alive. Any roll-call check that counts
0x70 toward the device total will pass a scan that is actually missing a
device. Expect eleven, not twelve.


> **INA260 rail map — measured 2026-09-15 by direct register read, pack at 11.36V.**
>
> | Addr | Constant | Rail | Reads |
> |---|---|---|---|
> | 0x40 | `INA260_5V_ADDR` | R2, 5V — steering servos, sonar VCC, Pi screen | 4.986V |
> | 0x44 | `INA260_ARM_6V_ADDR` | R3, 6V — arm servo distribution | 6.043V |
> | 0x45 | `INA260_BUS_12V_ADDR` | +12V bus → both FeatherWing VIN | 11.174V |
>
> **R1's 9V and R5's 3.3V have no INA260 at all.** The Witty Pi HAT monitors its own VIN;
> nothing monitors R5, so encoder-rail draw is meterable only.
>
> **0x45 is the rail `brain.py` watches for a motor-power cut**, pinned by
> `tests/test_motor_rail_identity.py`. **0x44 is NOT the motor bus** — it was named
> `INA260_MOTOR_ADDR` until 2026-09-15 and read as though it were, which broke in both
> directions: a real motor cut collapses the 12V bus and leaves the arm rail untouched, so
> the cut was undetectable; and the arm rail idles at 6.043V against a 6.0V threshold, so
> 43mV of servo droop raised a false "motor rail lost".
>
> **Constants are named for VOLTAGE, never for a consumer.** A name like `'motor'` silently
> becomes a lie when the wire moves and nothing fails loudly; a name stating the voltage
> cannot. **If an INA260 is relocated again, re-measure all three and rename to match** —
> do not assume the old name still describes the new wire.

**Trust a live `i2cget` bus-voltage read over any written source, including `config.py`.**
The rails are 5V / 6V / 12V apart and cannot be confused once actually measured. `config.py`
is not a safe shortcut here — it was itself stale for three weeks after the monitors were
relocated, while `brain.py` went on watching the wrong rail.

**Witty Pi 5 HAT+ (0x51) — NOT YET PHYSICALLY INSTALLED, software prepared ahead of it
(2026-08-20).** Per its own user manual, it uses only SDA/SCL — confirmed no conflict with
anything above. Wired via VUSB (USB-C, off the DROK-Pi 9V feed — **no INA260 sits on R1**),
not the VIN
screw terminal. `config.ENABLE_WITTY_PI` stays `False` (and 0x51 stays out of `brain.py`'s
self-test expected-device set) until it's actually connected — flip it on then, not before.
See `docs/WildWilly_Software_Design_v1.0.md` §4.1 for the integration story and the open
VIN-vs-VUSB low-voltage-threshold question that needs live testing, not a guessed number.

**Witty Pi 5 install/config runbook — install + config both done, 2026-08-20/21.** `wp5` (CLI)
+ `wp5d` (daemon, `systemctl status wp5d.service`) are installed and running, confirmed talking
to the HAT (`/var/log/wp5d.log`: "Connected to Witty Pi 5", firmware v1.4). RTC synced. Via
`wp5`'s "Other settings..." submenu, configured 2026-08-21:
- **Default state when powered → ON, 2s delay** — Willie now boots when power is connected
  rather than requiring the HAT's physical button; the 2s delay is just a debounce against a
  brief power blip triggering a full boot.
- **Power source priority → V-USB first** (matches actual wiring).
- **Watchdog → Enabled, 200 missed heartbeats** (~10-20s at `brain.py`'s tick's ~50-100ms
  heartbeat cadence — tolerant of ordinary hiccups, still catches a genuinely wedged kernel).
- **Low-voltage threshold (options 7/8) deliberately left untouched** — still confirmed
  VIN-specific behavior per the manual; don't set this until it's verified to do something sane
  on VUSB. The existing software battery-tier system (real ADC) remains primary regardless.

`config.ENABLE_WITTY_PI=True` is now set, 0x51 is in `brain.py`'s self-test expected-device set.
See the Power section below for a live under-voltage issue found 2026-08-20 — still open, needs
a physical cable/connector check, independent of the above.

---

## Pin assignments (BCM)

**Sonar** — three units, front/left/right. There is no rear sonar.

| Position | TRIG | ECHO |
|----------|------|------|
| Front (centre) | 5 | 26 |
| Left | 13 | 14 |
| Right | 4 | 21 |

ECHO lines pass through 1k/2k dividers (HC-SR04 echoes at 5V). TRIG is
driven directly. Sonar VCC is 5V, not 3V3.

**Other GPIO**

- GP2 / GP3 — I²C. Straight to the GODIY hubs and the whole device bus. The
  ISO1540 isolator that used to sit here was removed 2026-09-08; there is no
  isolation on this bus any more.
- GP15 — BNO085 interrupt
- GP0 / GP1 — RESERVED for AI HAT EEPROM, do not use
- GP7 — encoder interrupt (`config.ENCODER_INT_PIN`), interrupt-driven quadrature decode.
  Hardware prerequisite: MCP23017 INTA must be wired to this pin — not yet done, falls back
  to polling until it is.
- GP8–GP11 — free (retired SPI/MCP3008)

**SPI0 must stay disabled (`dtparam=spi=off` in `/boot/firmware/config.txt`).** Found and
fixed 2026-08-20: even with the MCP3008 physically removed, `dtparam=spi=on` still made the
kernel unconditionally reserve GP7/CE1, GP8/CE0, GP9/MISO, GP10/MOSI, GP11/SCLK as SPI0
hardware pins at boot — regardless of whether anything used the bus. This crash-looped
`willy-rover.service` on every single restart: `Encoders.start()`'s `GPIO.setup(config.
ENCODER_INT_PIN, ...)` hit `lgpio.error: 'GPIO busy'` deterministically (confirmed even with
the service fully stopped, via a standalone script — not a restart race), and the uncaught
exception's native unwind then crashed the process with a different signal each time (SIGABRT/
SIGSEGV/SIGBUS), which is why it initially looked like two unrelated bugs. Verify with
`sudo cat /sys/kernel/debug/gpio | grep spi0` before reusing any of GP7–GP11 — it should show
nothing if SPI0 is genuinely off.

**Serial console must stay disabled.** GP14 and GP15 are UART0 TXD/RXD. With
the console enabled the kernel drives GP14 as an output onto the left sonar's
divider node. Disabled and verified 2026-08-14. Symptom if it regresses:
front and right sonar read fine, left returns garbage.

---

## Hardware pitfalls that have already cost time

- **Board address defaults are not the chip's datasheet defaults, and this cost
  two days (2026-09-07/08).** A misconfigured FeatherWing address wedged the
  whole bus and presented as *dead hardware*: SDA or SCL clamped low, `i2cdetect`
  hanging or reporting phantom devices at every address from `0x08` up,
  `lost arbitration` and `controller timed out` in the thousands. Four driver
  boards were written off as destroyed. **None of them were faulty** — every one
  came back once the addressing was corrected.
  - **FeatherWing (Adafruit #2927)** — the address jumper documentation is the
    thing that misled here. Verify `0x60`/`0x61` on a scan, never by assumption.
  - **MCP23017 (Waveshare)** — address pins are **HIGH by default when unwelded**
    (→ `0x27`); you short the pads to pull them LOW. That is inverted from the
    bare chip's convention, where all-low is `0x20`.
  - Diagnostic rule learned: a bus that scans as *everything present from 0x08*
    is a stuck-low SDA being read as an ACK at every address, not devices.
- **Battery divider — fed, reading, and re-trimmed. Two open items, neither blocking.**
  The ADS1115 at `0x48` reports real pack voltage off a divider on the 12V bus.
  `BATTERY_DIVIDER_SCALE` was re-trimmed **0.2386 → 0.3237** on 2026-09-17 (A0 3.7229V
  against 11.5V metered).

  🔴 **That re-trim is the cautionary tale worth keeping.** The old scale was **34% off
  and reporting 15.60V from an 11.5V supply**, and it passed every guard — because every
  guard only catches readings that are too LOW. A battery reading that is too HIGH is
  invisible to this rover's entire protection scheme.

  Still open:
  - **Meter the actual resistors.** The trimmed scale implies ~10k/4.7k, not the documented
    10k/3.197k.
  - **At PGA ±4.096V the scale saturates at 12.65V** — about 50mV above a rested 3S pack,
    so full-charge readings clip.
  - **`sensors.py` still cannot tell a real zero from a broken sensor**, so a future divider
    fault would repeat silently. See Software Design §12 item 13.

- **A crash-looping service will masquerade as flaky hardware.** On 2026-09-08
  `willy-rover.service` was found `active` with **196 restarts**, holding two file
  descriptors on `/dev/i2c-1`, alongside `scripts/power_logger.py` polling the
  INA260s. Hours of "intermittent device dropout" measurements were taken against
  that. Before trusting any bus observation: `systemctl is-active willy-rover`
  and `sudo lsof /dev/i2c-1`. Only `wp5d` belongs there.

- ✅ **RESOLVED 2026-09-17 — and the suspicion was right.** This entry warned that the
  2026-09-06 remap might never have been reflected in the physical wiring. It wasn't.
  Measured on hardware, one channel at a time with the owner watching:
  **wrist pitch CH0, elbow CH1, shoulder CH2, second shoulder axis CH3, wrist rotate CH4,
  gripper CH5, base yaw CH6.** CH0–CH3 are exactly reversed versus the paper remap;
  CH4–CH6 were already right. CH7 and every spare channel on 0x42 were probed and are
  empty. `config.py`, `arm.py`, `retrieval_task.py` and all three design docs now carry
  the measured map.

  **The mirrored pair does not exist.** `J1b = 2×1500µs − J1a` is retracted: mirrored and
  same-direction commands on CH2/CH3 drew statistically identical settled current
  (0.197A vs 0.176A). The derivation is removed from `arm.py` — it would have commanded
  CH3 to 2250µs at the verified 750µs waving position.

  ⚠ **Never centre the elbow.** `ARM_SERVO_CENTER_US` drives CH1 into the top of the
  chassis; one MG996R was destroyed holding ~8A there. `center_all()` skips it now.
  **And guard the current from inside the movement loop** (`ARM_CURRENT_LIMIT_A` 2.5A /
  `ARM_CURRENT_LIMIT_S` 0.4s) — a limit checked after a move completes protects nothing.
- **FeatherWing motor mapping — MEASURED 2026-09-18 (M-1), and one half of it was
  backwards.** Rover on boxes, each port driven alone by raw address and port — never by
  wheel name, since the mapping was the thing under test — with the owner naming the wheel
  that actually turned:

      0x61 M1 -> LEFT REAR     0x60 M1 -> RIGHT REAR
      0x61 M2 -> LEFT CENTER   0x60 M2 -> RIGHT CENTER
      0x61 M3 -> LEFT FRONT    0x60 M3 -> RIGHT FRONT

  **Port order M1=REAR, M2=MIDDLE, M3=FRONT is correct** — commit `484fbdc` asserted it on
  2026-09-04 from "physical layout symmetry", which was an argument rather than a
  measurement, and the argument happened to be right. **The board addresses were the thing
  that was wrong**, reversed in every document until this measurement. `config.py:29` and
  `config.py:64` carry the measured truth. See Master Hardware Design v2.0 §7.2.
- **Arm servo connector(s) — RECONNECTED 2026-09-14, owner-confirmed.** Open from
  2026-08-20, when voice `arm_home`/`wave` dispatched correctly in software (heard,
  matched, `brain.py::_drain_voice_commands()` called `arm.center_all()`/`_start_wave()`,
  TTS ack played) and produced zero physical motion. The cause was unplugged servo
  connector(s) under the cover, not the under-voltage issue investigated the same day.

  **Not yet retested.** The connector is fixed; nobody has issued a voice `arm_home` and
  watched it move. Do that before treating the arm as working — it is one command and it
  is the difference between "wired" and "works".

  This unblocks three things that were all waiting on it: **`arm_jog.py` calibration**
  (per-joint limits are still recorded "Not tested", and nothing else unblocks
  retrieval), the **door-knock** design, and the **arm reach envelope** the lidar
  mounting question needs.
- **Motor− (white) never lands on an MCP23017 GPIO.** It goes to a FeatherWing
  motor terminal. A motor lead on a logic pin destroyed the first MCP23017.
- **ADS1115 A0 must read 2.76–3.06V before the ADC is powered.** It sits on a
  10k / ~3.2k divider off the 12V bus. A reading near 12V means the divider is
  open and the part will be destroyed on power-up.
- ⚠ **A0 near 0V means the divider is UNFED or open — not that the ADS1115 is dead.**
  It has been misdiagnosed that way twice. Most recently A0 read **0.025V** with the pack at
  11.36V, where it should have been ~2.7V, and `battery_volts` reported 0.09V. **The ADS1115
  was fine both times.** How to tell the two apart
  without a meter, because the board gives you a control: `config.py` says the charge-sense
  divider is not wired, so **A2/A3 are unconnected — and they read ~0.906V.** That is what a
  *floating* input looks like here. A0 at 0.025V is not floating; it is connected and being
  pulled to ground by the divider's low leg, which means **the wire to A0 is good and the
  +12V feed into the top resistor is open.** Meter the divider's high side at `V21`. Read all
  four channels before blaming the chip — `sensors.ADC.read_channel(0..3)`.
- **Battery sensing has a second opinion now (2026-09-15).**
  `brain.py::_check_battery_crosscheck()` compares the ADS1115 pack reading against the +12V
  bus INA260 and puts `⚠BATTERY SENSE SUSPECT` on the face when they disagree by more than
  `BAT_CROSSCHECK_MAX_DIFF_V`. **The divider stays the authority** — it taps the pack side and
  keeps reading whatever is switched off downstream; the bus monitor does not, which is exactly
  why it cannot replace it. Detection only: it never stops, faults, or moves the tier.
> **Historical — these three parts are no longer in the build (2026-09-08).**
> Kept because the reasoning generalises and because older notes and the design
> documents still refer to them.
>
> - **AMS1117-3.3 input is the 5V rail, never 12V.** Fed from 12V it dissipates
>   ~9V across the pass element, overheats, and drags its output down
>   progressively. This presented as devices dropping off successive scans —
>   ten, then six, then four — with no rewiring between them. It failed twice
>   this way. Retired 2026-09-08 once the touchscreen went back on Pi power and
>   it had no consumers left.
> - **A linear regulator fed its own output voltage cannot regulate.** The
>   AMS1117 was briefly fed 3.3V from a TPSM84203EAB, leaving it no headroom: it
>   measured 3.28V at light load and sagged to 2.98V under load, behaving as a
>   resistor rather than a regulator. **A rail that moves with load is a linear in
>   dropout; a buck holds flat.** That distinction is the diagnostic.
> - **ISO1540 sides are not interchangeable.** Side 1 (Pi side) took max 40pF and
>   one device; Side 2 (bus side) took 400pF and multiple nodes. Wiring the device
>   bus to Side 1 silenced it, and that cost this build twice. The part provided
>   common-mode noise rejection, never galvanic isolation — GND1 and GND2 were
>   always common. Removed 2026-09-08.
- **A degrading failure means thermal.** A wiring fault gives the same wrong
  answer every time; a part in thermal foldback gives a progressively worse one.

---

## Contradictions from older docs — resolved by Master Hardware Design v2.0

These used to be genuine open disagreements between the engineering docs
(flagged here 2026-08-14 against the old Master Engineering Package's
internal inconsistencies). Master Hardware Design v2.0 gives each a single,
unambiguous answer now — recorded here only so nobody re-opens them by
citing the old, superseded wording:

1. **Motor side assignment — measured on hardware, M-1, 2026-09-18.**
   **`0x61` drives the LEFT side (LF/LM/LR) and `0x60` drives the RIGHT side
   (RF/RM/RR)**, one board per side — the reverse of what every document asserted
   until that measurement. `config.py:29` carries it
   (`MOTORKIT_LEFT_ADDR=0x61`, `MOTORKIT_RIGHT_ADDR=0x60`). The *port* order within
   a side was settled by the same session — see the motor-port entry in "Hardware
   pitfalls" above. See `docs/WildWilly_Master_Hardware_Design_v2.0.md` §7.2.
2. **Arm shoulder channels — CH2 and CH3, measured on hardware 2026-09-17.**
   Note this matches the *2026-08-21* arrangement, not the 2026-09-06 remap: the
   plugs were never moved. They are **not** a mirrored pair and there is no
   `J1b = 2×1500µs − J1a` relation — CH2 is the lift axis (decreasing µs raises),
   CH3's function is still unidentified. See §8 and the resolved CH0 entry above.

Still genuinely open (not a doc contradiction — a real unverified-hardware
item, tracked in Master Hardware Design v2.0 §14).

**Before working any hardware item, read `docs/WildWilly_Bench_Test_Procedures.md`.**
Prepared 2026-09-14, it holds a written procedure for each one — motor mapping (M-1),
encoders (E-1), arm (A-1), vision range (V-1), ToF (T-1), battery divider (B-1), systemd
watchdog (W-1) — with the pass criteria and the interpretation rules decided *in advance*,
so a reading cannot be rationalised after the fact. It also opens by listing what is
already **proven in software**, so no bench time is spent re-establishing it. **Every result
field in that document is blank and must stay blank until someone runs the procedure on the
physical rover.** Write results into that file and commit them; a measurement that lives
only in a chat log is a measurement nobody can check.

Suggested order is M-1 first: every per-wheel claim — odometry, stall attribution, crab
steering, autonomous recovery — depends on knowing which wheel is which.

3. **Motor crimps unverified.** Five of six motors have not been checked
   against the corrected colour scheme (Red=Motor+, White=Motor−, Blue=Enc
   VCC, Black=Enc GND, Yellow=Phase A, Green=Phase B). Meter before trusting
   wire colour — batch variation is documented.

---

## Architecture constraint — keep the NPU out of the safety path

> **PERMANENT, decided 2026-09-14: the model's self-reported confidence must never authorize a
> physical action.** Not by raising `HAILO_LLM_CONFIDENCE_FLOOR`, not by lowering it, not by
> adding a second threshold anywhere. Measured over 96 calls, the confidence distributions for
> correct and wrong answers are **identical** (0.8/0.9/1.0 in both), and the model never emitted
> a value below 0.8 for anything. A gate can only separate populations that differ. This is not a
> threshold awaiting a better value — it is a signal with no information in it, and no amount of
> tuning changes that. Full data: `experiments/results/2026-09-14-failure-classification.md`.
>
> Which functions may use which reasoner is recorded in **Software Design v1.0 §6.7** (Tier A
> deterministic-only, Tier B model-proposes-safety-disposes, Tier C model-is-fine). The rule
> throughout: **the model may recommend an action; it must never be the authority that makes the
> action safe.** Enforced by `tests/test_reflex_deliberative_separation.py` and
> `tests/test_no_direct_drive_bypass.py`.


An AI HAT+ 2 (Hailo-10H) is installed and PCIe-bonded as of 2026-08-16 (`/dev/hailo0`,
`hailortcli fw-control identify` reports firmware 5.1.1, architecture HAILO10H). This was a
driver/package mismatch, not a hardware fault: the board had the Hailo-8-only package line
(`hailo-all`) installed, whose driver's PCI ID table doesn't include the Hailo-10H's ID
(`1e60:45c4`) — it loaded but silently never bound the device. Fixed by swapping to the
`hailo-h10-all` package line (`h10-hailort`, `h10-hailort-pcie-driver`, `python3-h10-hailort`).
`vision.py`/`ObjectDetector` is now wired to use it (2026-08-21, `ENABLE_HAILO_VISION=True` —
see the CSI/Hailo note below). The older CPU/ultralytics path against the Arducam remains in
place as an unconditional fallback and stays off (`ENABLE_OBJECT_RETRIEVAL=False`).

**Camera orientation — corrected 2026-08-20, was wrong in code.** There are two physical
cameras: the Arducam OV9281 (USB, `config.CAMERA_DEVICE=/dev/video8`) and a Pi Camera Module
(CSI, imx708, `rp1-cfe` driver, `/dev/video0`-`7`). Owner confirmed **the Arducam is mounted
REAR-facing and the CSI camera is FRONT-facing** — the opposite of what `vision.py`'s
`_CAMERA_ID='front'` label and `retrieval_task.py`'s detect-then-drive-forward logic both
assume. `ENABLE_OBJECT_RETRIEVAL` was briefly flipped True and live-verified working end-to-end
(model, cv2 5.0.0, ultralytics 8.4.115, real frame captured, mean brightness confirmed non-zero
— the full pipeline genuinely works), then reverted immediately once the orientation was
flagged, since driving toward what a rear camera sees would misdirect retrieval/pursuit.

**CSI/Hailo vision backend — live-verified working 2026-08-21.** The orientation correction above
led to CSI front camera + Hailo-10H backend integration (using picamera2.devices.Hailo for NPU
access, CSI imx708 for capture). `config.ENABLE_HAILO_VISION=True` (enabled 2026-08-21).
Verified by a standalone run on the rover (`venv/bin/python3`, **service stopped**): backend
loads (`available: True`, 80 labels, `(640,640)` input shape) and a real detection round-trip
succeeded with `camera_id='front'`. Not yet covered by that: startup under the live
`willy-rover.service` (alongside the pygame/SDL display and voice audio stack) and per-tick
timing against `WatchdogSec=500ms` (see the watchdog note below — not armed until 2026-09-07)
— `detect()` runs synchronously on the tick thread, so watch
for `TICK_OVERRUN` during the first mapping/pursuit session.

**This flag does more than swap backends.** `_enabled` is `ENABLE_HAILO_VISION or
ENABLE_OBJECT_RETRIEVAL`, so `detector.available` is now True in production for the first time —
which activates vision-gated behaviour that was previously dead: voice `come_here`/`follow`
(`PursuitTask`) and `retrieve` (`RetrievalTask`, which is not gated on `available` at all) now
genuinely drive the rover. Both steer on `vision.py::localize()`, whose `_ASSUMED_HFOV_DEG`/
`_FOCAL_PX_ESTIMATE` are still uncalibrated Arducam-era estimates against a 1280-wide frame, so
ranges read short — conservative for stopping, but a grasp can fire while still out of reach.
Worth a bench check against the imx708 before trusting a distance.

Reflex/deliberative layer separation still applies:

- **Reflex layer** — sonars, encoders, INA260 current monitors. Deterministic,
  drives the emergency stop. Must never wait on vision.
- **Deliberative layer** — the NPU. Frame-rate at best, variable latency,
  seconds-scale for LLM/VLM. Feeds `world_model.py` for planning and
  classification only.

An obstacle stop must never depend on a detection frame arriving. Vision
informs navigation; it does not gate the stop.

**The systemd watchdog was never armed until 2026-09-07 — the installed unit was stale.**
`willy-rover.service` in this repo has set `WatchdogSec=500ms` since 2026-08-02 (df24199), but
the unit actually installed at `/etc/systemd/system/willy-rover.service` was byte-identical
*except* for that one line, and `systemctl show -p WatchdogUSec` returned `0`. Confirmed on the
rover 2026-09-07, resolving the "unreconciled since 08-08" question in `brain.py` and FRD v3.1
G-5: the repo file was right, it just was never deployed. Two consequences, opposite in
direction:
- Every "systemd kills the process mid-tick" risk written in this repo between 2026-08-02 and
  2026-09-07 was **dormant**, not live. Real in the code, unarmed in deployment.
- `brain.py`'s `WATCHDOG=1` heartbeat was a **no-op** for the same period, so a wedged tick
  loop would never have been restarted. The Witty Pi HAT watchdog was the only real backstop.

**Arming it on 2026-09-07 broke the rover and was reverted the same hour — the repo unit is
unusable as written.** Installing it put the service into a permanent crash loop: SIGABRT
~500ms after every start, four starts in twenty seconds, never reaching its own first log
line. The cause is not a bad threshold. The unit is `Type=simple`, so `NotifyAccess` defaults
to `none` and **systemd discards every `sd_notify` message the process sends** — `brain.py`'s
`WATCHDOG=1` was never received, so the watchdog fired unconditionally on a timer and no
`WatchdogSec` value would have helped. Reverted to the previous unit; `WatchdogSec` is now
commented out in `willy-rover.service` with the preconditions recorded inline.

**So the watchdog has still never run on this rover.** Before re-arming it, two things must
both be true: `Type=notify` (or `NotifyAccess=main`) so the heartbeat is received at all, and
a `WatchdogSec` matched to real measured startup — init loads a 1.7GB Hailo HEF plus vision
and voice models, and under `Type=notify` that figure doubles as the startup deadline, so a
self-test that never sends `READY=1` would count as a failed start. Bench-validate before
arming it on a rover anyone is standing next to.

---

**Autonomous ROAM — gated off 2026-08-20, re-enabled 2026-09-07.** `brain.py::_idle()`'s
idle-timeout auto-wander and the post-charging auto-resume (`_tick()`'s `DOCK` handling) both
check `config.ENABLE_AUTONOMOUS_ROAM` before calling `_go('ROAM')`.
Found live 2026-08-20: with only sonar for obstacle sensing (no vision yet), Willie was wandering
unprompted and tripping repeated `STALL_FAULT`s against things sonar didn't catch — sometimes
5 of 6 wheels at once. Owner decision then: no unprompted autonomous driving until vision is
live-verified working. Manual/voice-commanded driving was never affected; the flag only ever
gated the unprompted idle/post-charge wander.

**The flag is now `True` (owner decision 2026-09-07) and the underlying limitation was
accepted, not fixed.** Obstacle avoidance is still sonar-only — vision is deliberately kept
out of the reflex path (see "keep the NPU out of the safety path" above), so live-verified
vision never satisfied this gate and does not now. Two open items make that worse and both
are worth knowing before leaving Willie alone: `MOTOR_PORT` is unverified since 2026-09-04 (a
stall may be attributed to the wrong wheel — see the motor-port pitfall above), and the
STUCK-state on-device reasoning that recovery depends on is FRD v3.1 G-6, last benchmarked at
0%. Expect most STUCK episodes to fall through to Claude, i.e. unattended recovery currently
needs the network.

**He now ASKS before the first unprompted wander of each session (owner decision 2026-09-09,
FR-1000-005).** `ENABLE_AUTONOMOUS_ROAM=True` stopped meaning "roams unattended" and started
meaning "allowed to ask" — the real gate is `self._roam_permission` in `brain.py`, false at
every boot and never persisted. Both unprompted triggers go through `_roam_allowed()`.

- He asks on **both** channels at once: speaks it, and lights a `LET ME ROAM` button on the
  panel. Either answers. This is not belt-and-braces — the wake word is unreliable and nobody
  is necessarily looking at the screen, so one channel alone is regularly unavailable.
- **A refusal is not permanent, and a refusal and silence are the same thing.** Both start
  `ROAM_ASK_COOLDOWN_S` (10 min) and then he asks again. That is why there is no DECLINE
  button — it would offer a choice that changes nothing.
- **Granted permission lasts the whole session**, so this does not make unattended roaming
  impossible — the person who said yes can walk away. It puts a human in the loop once per
  boot, nothing stronger. Cleared by a voice stop (`_revoke_roam_permission()` — otherwise
  "stop" would just brake him and the idle timeout would send him back out 30s later) or a
  reboot.
- Debugging "he won't roam": check `_roam_permission` before anything else, then
  `_roam_ask_next` (he may be in cooldown), then the flags. `ROAM_PERMISSION_REQUIRED=False`
  restores the pre-2026-09-09 unattended behavior exactly.

Set `ENABLE_AUTONOMOUS_ROAM` back to `False` if unattended `STALL_FAULT`s reappear.

---

**Audio: two USB devices, split by role (mic swap 2026-09-09).** They are
distinguishable by ONE WORD, and getting them backwards is silent — read this before
touching anything audio.

| Role | Name in `arecord -l` | USB ID | Card (2026-09-09) |
|------|----------------------|--------|-------------------|
| **Microphone** — input | USB PnP **Sound** Device | `08bb:2902` | 3 |
| **Speaker** — output | USB PnP **Audio** Device (the puck) | `0c76:1203` | 2 |

- **Never disable the puck.** Owner wants its speakers; only its *microphone* is
  retired. It is the only non-HDMI playback device on the rover — disabling it leaves
  Willie mute, including the spoken roam-permission ask.
- **The mic cannot do 16kHz.** Its hardware offers 48000/44100 only, and openwakeword
  needs 16000. PortAudio exposes the raw `hw:` devices with NO plug/default/PipeWire
  route, so ALSA will not resample — `voice.py` captures at 48k and decimates 3:1 via
  `downsample_to_16k()`. Do not "simplify" that to `samples[::3]`: striding aliases
  everything above 8kHz into the speech band and degrades wake scoring while looking
  exactly like a flaky mic.
- **Never pin `hw:2,0`/`hw:3,0`.** Card indices follow USB enumeration and can swap on
  reboot. Capture is selected by NAME (`config.AUDIO_INPUT_DEVICE`); `_loop()` logs the
  resolved name at startup — check that line first when voice misbehaves.
- `config.AUDIO_OUTPUT_DEVICE` is **inert**. Nothing reads it. All playback is `pw-play`
  → PipeWire's default sink. To change the output device, change the default sink.
- **Whether this fixes the wake word is still open.** It has been unexplained since
  2026-08-21, and `hey_willie.onnx` was trained through the OLD puck mic — a new capsule
  plus a new decimation stage change what the model scores. May need a retrain. Do not
  record it as fixed without a live trigger test.

---

**Email is a COMMAND channel now (owner decision 2026-09-11, FR-2000-012/013).** This
reverses `brain.py`'s long-standing "surfaced, never acted on" rule, so read this before
touching `email_client.py` or the email path in `brain.py`.

- **Willie acts on email from the owner, INCLUDING MOTION.** The owner chose the full
  channel over the non-physical-only option, against advice. Do not quietly narrow it
  back; do not quietly widen it either.
- **`_sender_allowed()` is a string match on the From header. That is NOT authentication.**
  The real check is FR-2000-013: parse Gmail's `Authentication-Results` header and refuse
  to act on anything that did not pass DKIM. If you touch this path and that check is
  missing, it is a bug, not a simplification.
- **Freshness is not optional.** An emailed motion command older than
  `EMAIL_COMMAND_MAX_AGE_S` must be dropped, for the same reason
  `VOICE_COMMAND_MAX_AGE_S` exists — "acting late on a motion command is worse than not
  acting at all". Email is inherently late; this is the guard that makes motion-by-email
  tolerable at all.
- **Directives 1–5 still gate it.** Email commands go onto `pending_commands` and drain at
  Directive 6 like voice. Nothing bypasses `SafetyController` — not this, not anything.
- **He announces aloud before acting.** A rover that starts driving with no audible reason
  while its owner is out is indistinguishable from a malfunction to whoever is in the room.
- **`ENABLE_EMAIL_COMMANDS` is the kill switch.** If the owner's Gmail is ever suspected
  compromised, set it `False` and redeploy — that account can drive the robot.

Note this sits alongside FR-2000-006, the prompt-injection boundary, which still stands:
email bodies are untrusted data and must still be wrapped by `build_summary_prompt()`
before reaching any model. Acting on a *parsed intent* from the owner is not licence to
feed raw email text to an LLM as instructions.

---

**Multi-zone ToF — DFRobot SEN0628. WORKING as of 2026-09-15 — 200/200 clean frames via
`scripts/tof_probe.py -n 200`.** Front obstacle sensing
*alongside* the sonar, never replacing it. Full design in Master Hardware Design §6.5
and Software Design §6.5/§6.6; the traps are here.

- **Set the DIP switch first.** Three positions choosing UART-vs-I²C and address. Wrong
  setting is a silent device that looks exactly like a wiring fault.
- **Peel the protective film off the optics** — a ~5×3mm square over the laser window
  that the documentation does not mention, plus one over the DIP switch.
- **USB-C is for FIRMWARE ONLY, not a protocol bench.** The sensor's USB CDC does not answer
  the command protocol: with the DIP set to UART, a correctly-framed `GETALL` over `COM4`
  timed out both before and after the v1.3 flash, and a 15s passive listen returned zero
  bytes. **Every byte we have ever seen from this sensor came over the hardware UART**, so
  **do not treat USB silence as evidence of a fault.** (Accounts of "rows y0–y7, eight
  columns" over USB are a purchaser running an example sketch, not raw output.)
  **Still true:** one of six reviewers had the board reset-looping every few seconds even
  on firmware v1.3 — **prove a stable multi-minute stream before this goes anywhere near
  the reflex path.**
- **Firmware v1.3 flashed 2026-09-15** (board serial `E66554A14B3CA123`). Windows sees the
  sensor as `USB Serial Device (COMx)` / `VID_2E8A&PID_000A` when running, and as removable
  drive `RPI-RP2` / `VID_2E8A&PID_0003` in BOOTSEL (hold **BOOT** while plugging USB-C).
  Flashing is drag-and-drop of the `.uf2`; the drive ejects itself on success. v1.3 fixes
  *"the bug where invalid values remained unchanged — all invalid values will be uniformly
  set to 4000"*, so **seeing 4000s is evidence of v1.3, not of a fault.**
- **Power from 3.3V, NOT 5V.** It accepts both, but on UART the logic level follows the
  supply and the Pi's RX is not 5V tolerant. Under 80mA off Pi header pin 1 — which
  already carries the whole I²C device bus, see below.
- 🔴 **AND FROM THE RIGHT 3.3V. This cost a full session on 2026-09-15.** The sensor was wired
  to the **TPSM chain's** 3.3V, which has been dead since the ISO1540 came out on 2026-09-08.
  It then failed in the most misleading way available: **LED lit, TX idling high against a
  forced pull-down, answering a few commands after each power cycle and then going silent.**
  Every "is it powered?" test passed. It also enumerated fine over USB-C — but USB supplies its
  own power, so that proved nothing about the rover rail. Moving 3.3V to the **Pi's own 3V3 /
  I²C rail (R4)** fixed it instantly: 200/200 frames.
  **The lesson generalises: prove which RAIL a device is on, not merely that it has voltage.**
  A marginal supply boots a chip far enough to look healthy and not far enough to work, and on
  this rover the TPSM/AMS1117 chain is fitted-but-dead, so it looks like a legitimate 3.3V tap.
- **The TCA9548A is NOT needed for this** (a change from the 2026-09-11 design). The mux
  was mandated because a bare VL53L7CX uploads ~84KB of firmware over I²C at every init;
  the onboard RP2040 does that locally now. I²C traffic is just 64 values per frame.
- **UART is the chosen interface** (2026-09-13) — all four rover USB ports are occupied,
  and UART keeps it off the I²C bus entirely. 🔴 **BOTH DIRECTIONS ARE REQUIRED.**
  Assuming RX alone would do cost most of a session. The sensor does **not** stream. It is strictly request/response: the host
  sends a command and the sensor answers, proven two ways — the library source polls
  (`getAllData()` writes a frame then blocks in `recvPacket()`), and **30 seconds of purely
  passive listening on a powered, correctly-wired sensor produced zero bytes.** **BOTH
  directions are required.** With only RX wired, commands never reach the sensor and it is
  silent for ever — which presents exactly like dead hardware. `GP8`/`GP9` are the
  candidates: free, and **SPI0 is already off** so the kernel is not holding them.
- **The overlay is `uart3-pi5`, NOT `uart3`** — VERIFIED on Willie 2026-09-15 and now in
  `/boot/firmware/config.txt`. `dtoverlay -h uart3` reports *"Enable uart 3 on GPIOs 4-7.
  **BCM2711 only**"* — the Pi 4 part. `uart3-pi5` reports *"Enable uart 3 on GPIOs 8-9.
  Pi 5 only."* Getting this wrong is silent: `config.txt` looks correct, the board boots
  clean, and the sensor reads as dead hardware on the wrong pins. Confirm with
  `ls /boot/firmware/overlays/ | grep uart`, `dtoverlay -h uart3-pi5`, and
  `sudo cat /sys/kernel/debug/gpio | grep spi0` (must be empty). After a reboot,
  `/dev/ttyAMA3` exists and `sudo pinctrl get 8-9` shows `a2 ... TXD3 / RXD3`.
- **GP8/GP9 are silkscreened `CE0` and `MISO` on the GeeekPi breakout** — SPI names,
  owner-confirmed 2026-09-14. GP9 = `MISO` = physical pin 21 (**required**, sensor TX);
  GP8 = `CE0` = physical pin 24 (**required** — it carries the Pi's TX, and without it no
  command can ever reach the sensor). **Re-label both for the UART they carry** — and note SPI0 must stay disabled
  (see the SPI0 entry above), so wiring actual SPI there would break two things at once.
- **`pinctrl` settles "is it even connected?" without a meter.** `sudo pinctrl get 9` shows
  `pu | hi` by default, which a *floating* pin also shows — so that level proves nothing.
  Force the pull down (`sudo pinctrl set 9 pd`) and re-read: still `hi` means something is
  actively driving the line, i.e. the sensor is powered and its TX is alive. Restore with
  `sudo pinctrl set 9 pu`. This distinguished "sensor absent" from "sensor present but
  mute" three times on 2026-09-15.
- **The USB-C bench test runs on the LAPTOP, not Willie.** It costs no rover port.
- **FOV is 60° H × 60° V, 90° DIAGONAL.** If you see "90 × 90" anywhere, that came from
  the earlier MusRock listing and is wrong. It matters: 60° vertical puts the floor
  intersection at ~1.7× mount height, not 1×.
- **Never blanket-mask the floor rows.** Calibrate a per-zone floor profile and flag a
  zone only when it returns meaningfully *shorter* than its stored value — see §6.5. And
  an **uncalibrated sensor must report nothing**, not raw ranges, or the floor becomes a
  permanent obstacle and Willie never moves.
- **It is also the cliff detector** now that dedicated cliff sensors were dropped (the
  chassis extends past the body, so nothing can mount ahead of the front wheels). A drop
  reads as zones returning *nothing* where the profile expects floor. Dark carpet does
  the same, which is the safe direction — he stops for nothing rather than driving off.
- **Unavailable ≠ fault.** If it drops out, `sensors.py` falls back to sonar alone and
  logs it. Adding a sensor must never lower Willie's availability floor.

---

**The I²C bus runs on the PI'S OWN 3.3V (header pin 1). DROK-4 / R5 feeds the motor
encoders and nothing else.** Owner-stated 2026-09-14, and it corrects a claim that was
in every document: several tables said R5 fed "Hall encoders and all I²C device logic".

- **Pi header pin 1 is a loaded rail with a real budget.** It carries eleven devices'
  logic plus the bus pull-ups plus the SEN0628. The Pi 5 rates that pin for a few
  hundred mA; that should be comfortable, but it is a budget that exists. Anything
  claiming "nothing loads Pi 3V3" is wrong — that error sat in §5.3, §9 and the rails
  table until 2026-09-14, and cost the breakout HAT a line.
- **The breakout HAT needs a 3V3 terminal.** It was removed from the list on 2026-09-11
  on the false premise above and restored on 2026-09-14. The list is **13 lines**, 14
  with the optional ToF UART return — count from Master Hardware Design §5.3's table,
  not from prose.
- **R5 is now cleanly separable, which matters for the dead encoders.** Since the
  encoders are its only consumer, R5 can be changed without risking the MCP23017,
  either PCA9685, or anything else on the bus. The standing hypothesis — that these
  Hall encoders want 5V and are sitting under-volted at 3.3V, which would explain six
  channels producing nothing since 2026-08-25 — is therefore a **clean experiment**
  now, not a risky one. **But the twelve encoder SIGNAL lines still land on a 3.3V
  MCP23017 whose inputs are NOT 5V tolerant**, so raising the supply still requires
  level shifting on those twelve lines. Supply and signal are separate problems.

---

**TWO places decide what is on the I²C bus, and they drifted.** `brain.py::_EXPECTED_I2C`
gates motion at startup; `diagnostics.py::_EXPECTED_I2C` is the read-only FR-1100-004
report. On 2026-09-14 brain expected **eleven** and diagnostics expected **ten** — Witty Pi
`0x51` was missing from diagnostics, which had never learned about `ENABLE_WITTY_PI`.

- **The failure direction was the bad one.** `python3 diagnostics.py` would report a clean
  bus on a rover whose Witty Pi had fallen off it — a health check that cannot see an
  absent device.
- Fixed, and `tests/test_expected_i2c_agreement.py` now compares the two sets directly, so
  they cannot drift again. **If you add a device, add it to `config.py` and let both sets
  derive from there** — an address written as a literal in one file and a config name in
  the other is how this happened.
- **`0x70` belongs in neither.** It is the PCA9685 all-call broadcast, cleared by
  `PCA9685.reset()` during construction, so expecting it would make every healthy rover
  fail its own self-test.

---

## Power

- Pi 5V rail measured 5.144V under boot load, `vcgencmd get_throttled` = 0x0.
  Floor is 4.85V. Do not let changes erode that margin.
- Worst-case 5V draw is already near 9A against an 8A UBEC rating. The AI HAT
  draws from this same rail — budget before fitting.
- Separately, worst-case steering draw is also near 9A, but through the
  PCA9685 boards' own V+ terminal/PCB trace/channel-header path, not the Pi's
  5V rail above — servo current now flows through the board itself, not just
  signal current. Confirm against the board's ratings before running all six
  steering servos under load simultaneously (Master Hardware Design v2.0 §14).
- GPIO power bypasses the Pi's onboard input protection. **There is no
  brownout trip in software.** Docs previously claimed this was "firmware-only
  via the 0x44 INA260" — that code does not exist: `safety.py` contains no
  INA260 logic, and `config.py:177` states the monitors are "Monitor/log only
  — no numeric overcurrent trip thresholds exist anywhere." Corrected
  2026-08-28. There is no hardware supervisor behind it either. **The Witty Pi 5 HAT+ (above) is the intended fix for
  this** — its own MCU can force a real power cycle independent of whatever
  the Pi's own OS/kernel is doing — now installed and software-configured
  (see below), but the underlying undervoltage gap itself is still open.

**Live under-voltage found 2026-08-20, root-caused and fixed 2026-08-21 — degraded AMS1117-3.3.**
`dmesg -T | grep -i voltage` showed `hwmon3: Under-voltage detected!` / `Voltage normalised`
cycling every 15-30s continuously, confirmed present even with `willy-rover.service` fully
stopped (owner caught this independently; not driven by rover software/CPU load). The next day
this had escalated into the isolated I2C bus itself flickering — repeated `i2cdetect -y 1`
scans one second apart showed *different devices* dropping in and out unpredictably (0x27,
0x42, 0x43, 0x44 flickering; 0x45/0x48/0x4a not appearing at all for a stretch), not a clean
single-device failure. Owner found and reconnected two separate loose connectors along the way
(a servo connector, then a "base side" power connector) — real issues, but neither one fully
stabilized the bus. **Root cause**: the AMS1117-3.3 regulator (VCC2, feeding the isolated bus
side) had degraded — the same failure category already documented above (fed the wrong
voltage, or just failed from that historical stress), pulling down its shared upstream supply
enough to also trip the Pi's own brownout detector, which is why both symptoms tracked
together. **Fixed by physically swapping the part** — confirmed with 18 consecutive
`i2cdetect -y 1` scans (10 before + 8 after reinstalling the ADS1115), one second apart, **zero
flicker**, full 11-device set present every single time. The `hwmon3` under-voltage messages
also stopped recurring the same moment (40+ min clean afterward, vs. cycling every 15-30s
before) — one root cause explains both symptoms, not two separate issues.

**Power rails as-built — four DROK converters, 2026-09-08.** The isolated power
chain carries nothing: no VCC2 rail, and the TPSM/AMS1117/F6 path has no
consumers. Note "out of service", not "unfitted" — the TPSM84205 is still on the
board (owner-confirmed 2026-09-09). Everything live runs off these four DROKs:

| Rail | Volts | Source | Feeds |
|------|-------|--------|-------|
| R1 | **9V** | DROK-Pi | Witty Pi 5 VIN → Pi | **Witty Pi HAT** (no INA260) |
| R2 | 5V | DROK-5V | Steering servos, sonar VCC, Pi screen | INA260 `0x40` |
| R3 | 6V | DROK-6V | Arm servo distribution |
| R5 | **3.3V** | DROK-4 | **Motor Hall encoders ONLY** (corrected 2026-09-14) |

**R5 is settled at 3.3V** — that resolves the "3V or 5V, voltage TBD" question
open in Master Hardware Design §2.2 since 2026-08-28.

⚠ **R5's entire load is the six Hall encoders.** It does not feed the I²C bus and
never did — all I²C device logic runs from **Pi header pin 1**, which is the rail
with a budget worth watching: eleven devices' logic plus every pull-up plus the
SEN0628, against a pin the Pi 5 rates for a few hundred mA.

**That makes R5 cleanly separable, which matters.** Since the encoders are its only
consumer, R5 can be changed without risking the MCP23017, either PCA9685, or
anything else on the bus — so the "do these encoders want 5V?" question is a clean
experiment, not a risky one. **R5 also has no INA260**, so its draw is invisible to
software and can only be checked with a meter.

⚠ **3.3V is the documented *minimum* for these encoders.** The 2026-08-25
root-cause notes Hall encoders "typically need 3.3V minimum and often 4.5V" —
which is why a sag to 2.83V killed all six while every I²C device kept working.
Running them at 3.3V leaves no margin. It is still the right choice, because the
alternative needs level shifting: the MCP23017 is at 3.3V and its inputs are
**not** 5V tolerant. If they do turn out to need 5V, check first whether the Hall
outputs are open-collector — if so, power the sensor at 5V and pull the output up
to 3.3V and no shifting is needed at all (Master Hardware Design §14 item 8).

**Superseded:** notes above and in the design documents describing a two-stage
TPSM84205 → AMS1117 chain, a single-stage TPSM84203EAB, or a VCC2 rail describe
builds that either never existed or no longer do. `git log` has the full
sequence; the table above is what is actually fitted.

The abnormally slow local-LLM voice latency measured 2026-08-20 (`intent=40.9s` vs. this repo's
own documented ~15-20s expectation from the 2026-08-15 voice latency work, `vcgencmd
get_throttled` reading `0x50000`) was measured *before* this fix — likely explained by CPU
throttling from the same under-voltage condition. Not yet re-measured post-fix; do that before
any further voice-latency software work (see owner's 2026-08-20 "needs to be immediate" ask).
- A hard cut at the main switch or E-stop with the OS running risks filesystem
  corruption. The graceful path is `shutdown -h now` followed by Switch 2.
  Bulk capacitance cannot hold a Pi 5 up long enough to shut down — that would
  need farads, not microfarads.

---

## Reference documents

The authoritative set, as of 2026-08-18, is three companion documents:

- **WildWilly Master Hardware Design v2.0** — as-built hardware, BOM,
  pin-to-pin connection schedule (§16). Section numbers cited elsewhere in
  this file (§7.2 motor mapping, §8 arm, §14 open items) refer to this
  document.
- **Functional Requirements Document v3.1** — what the rover must do and how
  each requirement is proven (§V verification register, §V.1 coverage,
  §V.2 known gaps).
- **WildWilly Software Design v1.0** — module architecture, control
  layering, FSM, safety gate.

**Do not cite the old Master Engineering Package (any revision) as
authoritative.** `docs/archive/WildWilly_Master_Engineering_Package_rev6.0.7.md`
is the oldest document in the repo — it predates the isolator orientation
fix, the Seengreat breakout swap, channel-header servo power, the
FeatherWings and the ADS1115, and its §5.7/§17.4 section numbers do not
exist in it (they were only ever created in a later "rev 6.2.0" that was
never committed to this repository — the historical record is a real
document, it just isn't in git). If that history is wanted in-repo, commit
it as its own file; don't treat citing its section numbers as equivalent to
having it, and don't resurrect rev 6.0.7 as a stand-in for it (found and
corrected 2026-08-18 — an earlier pass in this file wrongly did exactly
that, pointing here at rev 6.0.7 instead of recognizing rev 6.2.0 as a real,
newer, uncommitted document; see Master Hardware Design v2.0 §17.2 for the
full finding).
