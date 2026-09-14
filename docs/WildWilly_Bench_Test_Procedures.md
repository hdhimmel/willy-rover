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
passing at time of writing). They need no bench time and are listed so nobody re-does them.

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

**Record:**

| measurement | value | notes |
|---|---|---|
| Encoder supply, idle | | target 3.3 V |
| Encoder supply, under load | | sag here explains a lot |
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

**Why:** `tof.py::read_frame()` deliberately raises `NotImplementedError` — the sensor had
not arrived, so its wire format has never been observed. `ENABLE_TOF=False`.

**Procedure:**

1. Bench only, not on the rover, until frames decode. DIP switch set to UART. Protective
   film off the optics. Port per `config.TOF_PORT` (`/dev/ttyAMA3`).
2. Capture raw bytes from the port and confirm the frame structure against the datasheet
   **before writing any decode** — read the artifact, not the datasheet alone.
3. Implement `read_frame()` against the observed bytes.
4. On clear level floor, on the surface Willie actually roams, run
   `python3 scripts/calibrate_tof_floor.py`.
5. Only then set `ENABLE_TOF=True`.

**Record:**

| check | result |
|---|---|
| Raw frame observed (paste a sample) | |
| Frame length and structure match datasheet | |
| All 64 zones return data | |
| Floor profile captured, zones with no data | |
| Reads consistent at fixed distance | |

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
