# WildWilly — Bench Test Procedures

**Created 2026-09-14.** Prepared in advance of a hardware session, at the owner's request,
following the direction to *"make the physical robot's control and safety foundation
rock-solid before expanding autonomy."*

> **NO RESULT IN THIS DOCUMENT HAS BEEN OBSERVED.** Every result field is blank and stays
> blank until someone runs the procedure on the physical rover and writes down what
> happened. A procedure with a plausible-looking number already in it is worse than no
> procedure: the whole point of this session is to replace assumptions with measurements,
> and the repository already contains several defects that survived because a reasonable
> guess was written down as though it were a reading.

This is an operational checklist, not a design document. It does not count against the
three-document rule (Master Hardware Design, Software Design, Functional Requirements) and
follows the existing convention of `WildWilly_ADS1115_Bringup_Checklist.md` and
`WildWilly_PCA9685_Arrival_Punchlist.md`.

---

## What is already verified, and what is not

The distinction matters because it decides what still needs the rover.

### Verified in software — done, no hardware required

These are proven by the test suite (`WILLY_SIMULATE=1 ./venv/bin/python -m pytest`, 398
passing at time of writing; **412 as of 2026-09-17**). They need no bench time and are listed
so nobody re-does them.

✅ **S-1 sonar array — CLOSED ON HARDWARE 2026-09-17.** All three channels range-tested
together for the first time since the build: front 49.7cm, left 91.1cm, right 30.9cm, each
stable to ±0.4cm over 8 samples and each reading its own direction (three distinct
distances, so no cross-talk). All three ECHO lines idle LOW and go low against an internal
pull-down. R2 at 4.990V @ 0.026A — no sensor drawing fault current. There is no separate
S-1 procedure below because the array was closed while debugging it; the method is recorded
in Master Hardware Design §16.13, which now carries a diagnosis table for a dead channel.

| area | evidence |
|---|---|
| Emergency stop phrasing, incl. negation | `tests/test_emergency_stop_phrases.py` (40) |
| Reflex/deliberative separation | `tests/test_reflex_deliberative_separation.py` (5) |
| Nothing bypasses `safety.py` to the motors | `tests/test_no_direct_drive_bypass.py` |
| AI result → motion gating, all result kinds | `tests/test_stuck_ai_fallback_chain.py` |
| Malformed model output never becomes an action | `tests/test_malformed_model_output.py` (24) |
| Confidence gate semantics | `tests/test_confidence_gate_semantics.py` (9) |
| Hailo ChatML framing, statelessness, params, device sharing | 4 files, 27 tests |
| STUCK prompt shape and single-source | `tests/test_stuck_prompt.py` (11) |
| sd_notify wire format, inertness, fault tolerance | `tests/test_sd_notify.py` (6) |
| I²C expected-device agreement | `tests/test_expected_i2c_agreement.py` (5) |

### Requires the physical rover — everything below

Nothing in the sections that follow can be established from a laptop, and none of it should
be inferred from code reading. Each has a blank result field.

**Safety rules for every procedure here:**

1. **Rover on blocks, wheels free**, unless a step explicitly says otherwise.
2. **Stop the service first**: `sudo systemctl stop willy-rover` — it holds the I²C bus, the
   camera and the serial ports, and two processes driving the same PCA9685 is its own defect.
3. **Keep a hand on the power switch.** The hardware e-stop is a latching cut with no
   documented GPIO sense pin, so software cannot observe or override it — that is the point.
4. Restart afterwards: `sudo systemctl start willy-rover`.

---

## M-1 — Motor port mapping (one wheel at a time)

**Why:** `config.py:59` `MOTOR_PORT` was changed on 2026-09-04 from a bench-measured mapping
to an assumed physical ordering. Until this is confirmed, do not trust per-wheel odometry,
stall attribution, crab steering, or autonomous recovery — every one of those names a
specific wheel.

**Tooling:** `scripts/encoder_map_check.py` already drives one wheel at a time and reads the
MCP23017 GPIO registers directly (deliberately not through `sensors.Encoders`, whose decode
assumes the mapping under test). `scripts/wheel_current_test.py` drives one wheel and reports
current, which independently confirms *which* motor moved.

**Procedure:**

1. Rover on blocks. Service stopped. Label the six wheels physically (LF, LM, LR, RF, RM, RR)
   with tape so the observer and the recorder mean the same thing.
2. For each of the six `MOTOR_PORT` entries in turn, drive that port alone, forward, ~2s at
   a duty above breakaway (`config.py:61` notes this chassis needs roughly 0.5+ duty to turn
   at all; below that a healthy motor only hums).
3. Record **which physical wheel turned** and **in which direction**.
4. Repeat in reverse for any wheel whose direction looked wrong.

**Record:**

| config key | address, port | wheel that actually turned | direction correct? |
|---|---|---|---|
| `lf` | `MOTORKIT_LEFT_ADDR`, 3 | | |
| `lm` | `MOTORKIT_LEFT_ADDR`, 2 | | |
| `lr` | `MOTORKIT_LEFT_ADDR`, 1 | | |
| `rf` | `MOTORKIT_RIGHT_ADDR`, 3 | | |
| `rm` | `MOTORKIT_RIGHT_ADDR`, 2 | | |
| `rr` | `MOTORKIT_RIGHT_ADDR`, 1 | | |

**Pass:** all six map to the wheel their key names, and forward is forward on both sides.
**If it fails:** correct `MOTOR_PORT` in `config.py`, then re-run this whole procedure —
not just the rows that were wrong. A mapping is a permutation; fixing one entry can move
another.

**Note:** the encoder A/B channel assignment is a *separate* unverified question
(`config.py:57`) and is **not** settled by settling this one. See E-1.

---

## E-1 — Encoder supply and output

**Why:** `ENCODER_COUNTS_PER_REV=752` (11 PPR × 4 quadrature × 17.1:1) is arithmetic, not a
measurement, and the A/B assignment is flagged unverified. FRD G-2 separately computes that
at 620 RPM output the edge rate is ~7,770 Hz against a ~1 kHz polling ceiling — roughly 8×
oversubscribed — which means counts may be *systematically* low rather than noisy.

**Do not hand-turn the wheels.** Measured 2026-08-25: 30s of hand-turning produced one
distinct pin state while 3s of driving produced seven. The encoder is on the motor shaft
behind the 17.1:1 gearbox and does not back-drive. Any encoder measurement here must be
taken under power.

**Procedure:**

1. Meter the encoder supply rail at the encoder connector, motors idle, then again while
   driving. Record both — a rail that sags only under load is the failure mode that looked
   like a dead sensor on 2026-08-25 (measured 2.83 V against a 3.3 V target).
2. Run `scripts/encoder_map_check.py` (rover on blocks) and record which encoder channels
   move for which driven wheel.
3. Run `scripts/encoder_calibration.py` to compare observed counts per revolution against
   the configured 752.

**RESULT 2026-09-18 — partially closed.**

| measurement | value | notes |
|---|---|---|
| Encoder supply, idle | **3.3 V** | in spec; the datasheet range is 3.3–5 V, so undervoltage was never the fault |
| Encoder supply, under load | **3.3 V** | no sag — the 2026-08-25 theory (2.83 V) is dead |
| Encoder supply POLARITY | ⚠ **WAS REVERSED** | found and corrected 2026-09-18. LF Phase A went 2/6 → 6/6 immediately after |
| Pin-to-wheel map | ✅ **measured** | left/right were transposed, same as the motor boards — see Master Hardware Design §7.2 |
| Phase A (yellow, even pin) | ✅ all six | |
| Phase B (green, odd pin) | ❌ **dead on all six** | one wiring pattern, not six faults — trace the green wires |
| Counts per revolution vs 752 | not measured | blocked on Phase B: quadrature needs both channels |

**The method matters more than the numbers here.** Do not poll these pins for edges: at 0.6
duty the edge rate is ~7.7 kHz against a ~1.2 kHz I²C ceiling, and the aliasing reads as a
CONSTANT. Three attempts concluded "no encoder output at all" and all three were wrong. Drive
one wheel ~1 s, compare the MCP23017 resting state before and after, and count across several
trials which pins change.

**Still open:** the green/Phase-B wiring, and only then counts-per-rev. Note step 3 below is
itself invalid — `scripts/encoder_calibration.py` is built on hand-turning, which produces
nothing on this rover (§2.2: the encoder is behind the 17.1:1 gearbox and does not
back-drive).
| Channels responding per wheel | | |
| Observed counts/rev vs 752 | | |
| Counts plausible at speed, or systematically low? | | bears on FRD G-2 |

**Pass:** supply holds within tolerance under load, every wheel produces distinct A/B
activity, and observed counts/rev are within a few percent of 752.

---

## A-1 — Arm connector reconnection

**Why:** the arm connector was reconnected and has not been exercised since.

**Procedure:**

1. Arm clear of obstructions, rover powered, service running.
2. Issue `arm_home` by voice ("willie, home the arm") or via the pending-command path.
3. Observe physically.

**Record:**

| check | result |
|---|---|
| All expected joints moved | |
| Any joint stuck, buzzing, or fighting | |
| Motion smooth or jerky | |
| Servo current during motion (`scripts/servo_current_test.py`) | |

**Pass:** every joint moves to centre, nothing buzzes at the limit, current is in family
with the other joints.

**Note for the recorder:** `brain.py:807` currently aliases **both** `arm_stow` and
`arm_home` to `arm.center_all()`, because no calibrated stow pose exists yet (§20.6). So
this procedure tests the connector and the servos — it does **not** test a stow pose,
because there is not one. Do not record "stow verified".

---

## V-1 — IMX708 range and bearing calibration

**Why:** `vision.py:19-20` uses `_ASSUMED_HFOV_DEG = 70.0` and `_FOCAL_PX_ESTIMATE = 600.0`,
both explicitly not bench-measured. `come_here`, `follow`, `retrieve` and the grasp standoff
all rest on them. Conservative stopping does not make the numbers right; it makes the error
land in a safer direction *most* of the time.

**Precondition — settle the camera question first.** `vision.py`'s constants are commented as
being for the **OV9281**, while `config.CAMERA_DEVICE` is `/dev/video8`, which `config.py:587`
records as the **rear-facing Arducam**. Calibrating range for a camera that is not looking
where the rover drives produces a confident wrong number, which is worse than the current
honest estimate. `scripts/calibrate_vision_range.py` refuses to proceed until this is
confirmed, deliberately.

**Procedure:**

1. `sudo systemctl stop willy-rover`
2. `./venv/bin/python scripts/calibrate_vision_range.py --object person`
3. Place the object squarely at measured distances across the working range — suggested
   50, 75, 100, 150, 200, 300 cm, measured to the **front face of the rover**.
4. For bearing: place the object at a measured lateral offset at one fixed distance, both
   left and right, and record reported bearing against true angle.

**Record:**

| true distance (cm) | reported (cm) | ratio |
|---|---|---|
| 50 | | |
| 75 | | |
| 100 | | |
| 150 | | |
| 200 | | |
| 300 | | |

| bearing check | true angle | reported |
|---|---|---|
| left offset | | |
| right offset | | |

**Interpretation, decided in advance so the result is not rationalised afterwards:**

- A **constant** true/reported ratio across all distances is a focal-length error. Scale
  `_FOCAL_PX_ESTIMATE` by it.
- A **varying** ratio is *not* a focal-length error — a wrong focal length scales every
  reading by the same factor. Varying means the assumed object width is wrong, the detector
  box is unstable, or the object was not square to the camera. **Do not apply a correction
  from such a run.**

**Pass:** ratio constant within ±0.1 across the range, bearing within a few degrees.
**Until this passes**, treat `retrieve` grasp distance as unvalidated regardless of how
conservative the stopping behaviour looks.

---

## T-1 — ToF (DFRobot SEN0628) bench test, before integration

**Why:** `tof.py::read_frame()` deliberately raises `NotImplementedError` — the wire format
had never been observed. `ENABLE_TOF=False`.

> ✅ **LARGELY CLOSED 2026-09-15 — the sensor works.** Transport, protocol and sensor are all
> verified: **200/200 clean frames** at 0.13s each, 62–63 of 64 zones live.
>
> **Root cause of the day spent getting there: it was powered from the dormant TPSM chain**, not
> from the Pi's 3V3 / I²C rail (R4). A marginal supply boots the RP2040 far enough to light its
> LED, hold TX idle-high and answer a few commands, then go quiet — so every "is it powered?"
> check passed. **Prove which RAIL a device is on, not just that it has voltage.**
>
> What remains: the near-field zone anomaly below, one longer stability run, `read_frame()`,
> and the floor profile.

**Pi side — VERIFIED 2026-09-15, does not need rechecking:**

| check | result |
|---|---|
| `dtoverlay=uart3-pi5` in `/boot/firmware/config.txt` | ✅ added and confirmed |
| `/dev/ttyAMA3` exists after reboot | ✅ `PL011 AXI` at `1f0003c000.serial` |
| `pinctrl get 8-9` shows `a2` = TXD3 / RXD3 | ✅ |
| `spi0` not holding GP8/GP9 | ✅ empty |

⚠ **It must be `uart3-pi5`, never `uart3`.** The plain overlay is BCM2711/Pi 4 and puts
UART3 on GPIOs 4–7. It does not error, the Pi boots cleanly, and the sensor reads as dead
hardware on the wrong pins.

**UART protocol — derived from `DFRobot_MatrixLidar.cpp` verbatim, 2026-09-15:**

```
request   [0x55][argsNumH][argsNumL][cmd][args...]      argsNum = len(args) + 1
reply     [status][cmd][lenL][lenH][payload...]          lenL BEFORE lenH
          status 0x53 = SUCCESS, 0x63 = FAILED
          0xFF is filler; skip it while hunting the status byte
getAllData    55 00 01 02
setRangingMode 8x8   55 00 05 01 00 00 00 08   then wait 5s (library does delay(5000))
payload   little-endian uint16 millimetres, 64 zones = 128 bytes; 4000 = invalid
```

Two traps, both of which cost hours: `argsNum` is `len+1` not `len` (the un-incremented
value returns `STATUS_FAILED`, which reads like a hardware fault), and the reply's `0x53`
is a **status byte, not a header** — parsing it as a header yields nonsense lengths.

**`scripts/tof_probe.py` implements all of this.** Use it rather than rewriting a client.

**Procedure — the sensor-dependent half:**

1. **Set the DIP switch to UART and then DISCONNECT POWER.** The factory default is I²C, and
   DFRobot require a power disconnect for the change to latch — a Pi reboot will not do it,
   because the 3.3V header rail stays up. A sensor in I²C mode is silent on UART with both
   lines idling high, indistinguishable from any other fault here.
2. **Peel the protective film** off the optics and off the DIP switch.
3. **Wire BOTH data lines.** `sensor TX → GP9 = pin 21` *and* `sensor RX → GP8 = pin 24`.
   Power from **3.3V, not 5V**. Earlier guidance that only RX was needed was wrong — see
   below — and one wire produces permanent silence.
4. `./venv/bin/python scripts/tof_probe.py --listen` → **expect zero bytes.** The sensor is
   polled, not streaming. Zero here is a pass, not a fault.
5. `./venv/bin/python scripts/tof_probe.py` → expect `SUCCESS`, `len=128`, and a grid.
6. `./venv/bin/python scripts/tof_probe.py -n 200` for the stability bar. §6.5 requires a
   **stable multi-minute stream**; intermittent is a fail. Return inside 30 days if it will
   not hold one.
7. Implement `read_frame()` against the observed bytes.
8. On clear level floor, on the surface Willie actually roams, run
   `python3 scripts/calibrate_tof_floor.py`.
9. Only then set `ENABLE_TOF=True`.

**`pinctrl` answers "is it even connected?" without a meter.** `sudo pinctrl get 9` reads
`pu | hi` by default — but a *floating* pin reads the same, so that proves nothing. Force
the pull down (`sudo pinctrl set 9 pd`) and re-read: still `hi` means something external is
actively driving the line, i.e. the sensor is powered and its TX is alive. Restore with
`sudo pinctrl set 9 pu`. This separated "sensor absent" from "sensor present but mute"
three times on 2026-09-15.

**Record:**

| check | result |
|---|---|
| Raw frame observed (paste a sample) | ✅ 2026-09-15 — `status=0x53 cmd=2 len=128`, payload LE uint16 mm; sample row `1087 1145 1182 1211 1167 1203 1227 1212` |
| Frame length and structure match library source | ✅ 128 bytes = 64 zones × uint16, exactly as derived |
| All 64 zones return data | ⚠ **62–63 of 64.** Rows 1–4 read **5–14mm**, below the sensor's 20mm minimum, with scattered zeros and two `4000`s. Rows 5–8 read a sensible 1.0–1.2m. **Check the protective film on the optics first** (CLAUDE.md's first ToF trap — a ~5×3mm square the vendor docs never mention), then the bench pose. Do NOT run the floor profile until this is understood — `calibrate_tof_floor.py` would bake it into the baseline |
| Stable multi-minute stream (`-n 200`) | ✅ **200/200, zero dropouts, 0.13s/frame.** Run took ~1.8 min — repeat at `-n 600` to fully satisfy "multi-minute" before `ENABLE_TOF=True` |
| Floor profile captured, zones with no data | blocked on the near-field anomaly above |
| Reads consistent at fixed distance | |

**Supply — record this, it was the whole fault.** 3.3V must come from the **Pi 3V3 / I²C rail
(R4)**, never the TPSM/AMS1117 chain, which has been dormant since 2026-09-08. The sensor adds
up to 80mA to R4 and is now its largest single consumer; nothing monitors that rail, so if it
goes tight the symptom is I²C flakiness appearing after `ENABLE_TOF` goes True.

**Note:** re-run the floor capture after **any** mechanical change. The profile is tied to
the sensor's exact pose; a shifted bracket invalidates it. That failure is loud rather than
silent (phantom obstacles, so he stops for nothing), but it is still a failure.

---

## B-1 — Battery divider calibration

**Why:** `BATTERY_DIVIDER_SCALE=0.2386` needs re-trimming, and the feed should be confirmed
electrically correct first. A scale trimmed against a wrong feed is a wrong number that
looks right.

**Procedure:**

1. Confirm the divider feed is what the documentation says it is — meter it, do not infer it.
2. With a meter on the pack, compare true pack voltage against `adc.battery_volts` at three
   states of charge across the usable range.
3. Compute the corrected scale; do not fit from a single point.

**Record:**

| true pack voltage | reported `battery_volts` | ratio |
|---|---|---|
| | | |
| | | |
| | | |

**Pass:** reported tracks true within ~0.1 V across the range after correction.

**Related:** `config.BAT_IMPLAUSIBLE_V=5.0` rejects readings below a plausibility floor. Note
during this procedure whether any legitimate reading is being rejected.

---

## W-1 — systemd watchdog, bench validation before arming

**Why:** on 2026-09-07, `WatchdogSec=500ms` was installed on a `Type=simple` unit.
`NotifyAccess` then defaults to `none`, so systemd **discarded every** `sd_notify` message —
the heartbeat was never received, no heartbeat rate could have satisfied the deadline, and
the rover was SIGABRTed four times in twenty seconds, never reaching its own first log line.

**Prepared, not installed:** `willy-rover-watchdog.service.prepared`. It is named `.prepared`
so a wildcard copy cannot pick it up, and it carries two `__MEASURE__` placeholders.

**systemd does not reject those** — verified 2026-09-14 with `systemd-analyze`, it logs
`Failed to parse ... ignoring` for both lines and starts the unit with the **defaults**, and the
default for `WatchdogSec` is *disabled*. That would be the worst outcome available: the rover
comes up cleanly and whoever installed it believes the watchdog is armed while nothing is
watching. So the refusal is enforced explicitly by an `ExecStartPre` guard that fails the start
while any placeholder remains (checked in both directions: exit 1 with placeholders, exit 0 once
filled). **A unit that refuses to start is a better failure than a rover that crash-loops, and
far better than one that lies about being protected.**

**Software side already verified** (`tests/test_sd_notify.py`): message wire format,
inertness when `NOTIFY_SOCKET` is unset, abstract-socket translation, no exception into the
tick loop from a dead socket, and that `READY=1` is reachable after a *failed* self-test — so
a degraded rover stays up instead of restart-looping.

**Procedure:**

1. `sudo systemctl stop willy-rover`
2. `./venv/bin/python scripts/measure_startup.py --runs 5 --out /tmp/startup.json`
   This launches `main.py` with its own notify socket; it does not install anything or use
   `systemctl`.
3. Fill both `__MEASURE__` values from the printed suggestions. Sanity-check `WatchdogSec`
   against `config.TICK_OVERRUN_THRESHOLD_S` — a watchdog **below** the tick-overrun
   threshold kills the process before it has logged that it was running slow, destroying the
   evidence for why it died.
4. Install as a **separate** unit; do not overwrite `willy-rover.service`, so rollback is one
   command.
5. **Rover on blocks.** Restart it 10 times: `sudo systemctl restart willy-rover-watchdog`,
   confirming each time that it reaches ready and stays up for at least two minutes.
6. Confirm the watchdog actually bites: induce a stalled tick (e.g. `SIGSTOP` the process) and
   confirm systemd restarts it within roughly `WatchdogSec`.

**Record:**

| measurement | value |
|---|---|
| Startup, worst of 5 runs | |
| Startup, median | |
| Worst tick-gap between heartbeats | |
| `TimeoutStartSec` chosen | |
| `WatchdogSec` chosen | |
| `WatchdogSec` > `TICK_OVERRUN_THRESHOLD_S`? | |
| 10 restarts all reached ready | |
| Watchdog fires on an induced stall | |
| Degraded self-test still reaches ready (not a restart loop) | |

**Pass:** all ten restarts reach ready, the watchdog demonstrably fires on a real stall, and
a deliberately failed self-test produces a degraded-but-running rover rather than a loop.

**Rollback:**
`sudo systemctl disable --now willy-rover-watchdog && sudo systemctl enable --now willy-rover`

---

## Suggested order

Each stage assumes the one before it. Doing them out of order produces measurements that
have to be retaken.

1. **M-1** motor mapping — everything per-wheel depends on knowing which wheel is which.
2. **E-1** encoders — needs M-1 to attribute channels to wheels correctly.
3. **B-1** battery divider — cheap, independent, and it underpins every "is the rail sagging"
   question in E-1.
4. **A-1** arm — independent, quick.
5. **W-1** watchdog — do it before any unattended running, and after M-1/E-1 so a restart
   loop cannot be confused with a drive fault.
6. **V-1** vision range — gate for `retrieve`/`come_here`/`follow`; settle the camera-facing
   question first or skip it.
7. **T-1** ToF — last, because it is the only one that needs new code written against
   observed bytes.

---

## Recording results

Write results **into this file** and commit them, rather than into a chat log. The standing
repo rule applies: when a measurement contradicts a document, prefer the artifact, and sweep
the *old* value repo-wide before calling the change done. Strike superseded text rather than
deleting it, so the correction stays legible.
