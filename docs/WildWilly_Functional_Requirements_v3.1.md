**Willie Functional Requirements Document (FRD)\
Version 3.1**

**Document control**

  -----------------------------------------------------------------------
  Field                   Value
  ----------------------- -----------------------------------------------
  Revision                3.4

  Date                    2026-09-24

  Owner                   Howard Himmel

  Status                  Hardware build complete; live verification in
                          progress

  Companion documents     WildWilly Master Hardware Design rev 2.5 --- current
                          hardware configuration. Section references of the
                          form §n refer to it unless stated otherwise.
                          WildWilly Software Design rev 1.3 --- module
                          architecture and control layering.

  -----------------------------------------------------------------------

**This document carries 128 requirement IDs** (distinct FR-xxx-yyy rows, recounted
2026-10-02; it said 117). §V is the verification-status
register; §V.1 records which requirement groups have implementing modules and test
coverage, and §V.2 lists the known gaps where a requirement cannot currently be
satisfied as written.

# V. Verification Status Register

Requirements are implemented and unit-tested off-hardware unless noted.
"Live-verified" means proven on the assembled rover.

  -----------------------------------------------------------------------
  Group                   Status                  Notes
  ----------------------- ----------------------- -----------------------
  FR-000 Prime Directives Implemented, not        Requires E-stop and
                          live-verified           motion testing

  FR-100 Startup          PARTIAL --- I²C         Eleven-device roll-call
                          enumeration             passes on the single
                          live-verified           non-isolated segment ---
                                                  20 consecutive scans,
                                                  zero errors, 2026-09-08.
                                                  Encoder and IMU checks
                                                  outstanding.
                                                  Roll-call is TEN since
                                                  2026-09-30 (0x27 gone).
                                                  Self-test retry probes
                                                  only missing addresses,
                                                  base-off is named:
                                                  built 2026-10-01/02,
                                                  not yet run on the
                                                  rover. No startup
                                                  scan, 0x4A never
                                                  probed (05bcddd):
                                                  live-proven
                                                  2026-10-02.
                                                  Clock from internet
                                                  time before start, then
                                                  written to the Witty Pi
                                                  RTC (clock_sync.sh,
                                                  2026-10-06; the RTC had
                                                  been a week fast).

  FR-200 Power            PARTIAL --- rail        Pi rail 5.144V,
                          measurement, and the      throttled 0x0. Divider
                          BATTERY DIVIDER IS       fed and in spec since
                          READING (2026-09-14);     2026-09-14.
                          scale trimmed           `BATTERY_DIVIDER_SCALE`
                          2026-10-01               = 0.2432, ONE-POINT trim
                                                  2026-10-01 (A0 2.7653V
                                                  vs 11.37V metered);
                                                  second point open. The
                                                  unfed-divider (0.0146V,
                                                  2026-09-02..14) and
                                                  0.3237-scale states
                                                  recorded here earlier
                                                  are both over.
                                                  Ladder halts (rth and
                                                  shutdown tiers) and
                                                  per-rail overcurrent:
                                                  built 2026-10-02, not
                                                  yet run on the rover.
                                                  See Master Hardware
                                                  Design §6.2 / §14 item
                                                  12.
                                                  2026-10-07: authority
                                                  explicit -- bus live =
                                                  bus is the reading;
                                                  bus dead = divider,
                                                  and a halt is vetoed
                                                  while the divider is
                                                  flagged suspect. The
                                                  divider reads 0.31 vs
                                                  0.242 design: resistor
                                                  values being metered.
                                                  2026-10-07 later: legs
                                                  meter right powered off
                                                  (3.2k / 9.2k in-circuit)
                                                  but live A0 reads a
                                                  steady 1.77 V for ~2.9
                                                  expected (ratio 0.15).
                                                  Next: live P1-13 and
                                                  P1-14 to P1-17.

  FR-300 Safety / E-stop  SATISFIED by hardware   The E-stop IS the main power
                          (owner decision          switch: it cuts all power,
                          2026-08-24)              the Pi included, so there is
                                                  nothing to sense. NO LONGER BLOCKS
                                                  FR-400..700 live testing.
                                                  See FR-300 Acceptance
                                                  Criteria and G-1.

  FR-400 Drive            LIVE-VERIFIED           Owner, 2026-10-06:
                          (owner, 2026-10-06)     drive verified on the
                                                  rover. Supersedes the
                                                  crimp and not-yet-run
                                                  notes that stood here
                                                  (170 RPM motors fitted
                                                  2026-10-01; mph speeds,
                                                  1.5 mph cap).
                                                  Brake on a stopped,
                                                  released drive is a
                                                  no-op (6be1091) ---
                                                  fixes a twitch seen
                                                  live in a latched
                                                  fault.

  FR-500 Encoders         PARTIAL --- counts and  All six count A and B
                          direction live          through Pico A a-0.3
                          2026-10-01              (signed x2); Phase B
                                                  alive on all six.
                                                  ENCODER_COUNTS_PER_REV
                                                  = 763, measured
                                                  2026-10-01 on ONE wheel
                                                  (lf), under power.
                                                  Straight-line distance,
                                                  stall stop and
                                                  closed-loop speed not
                                                  live-verified.
                                                  Uncommanded-motion
                                                  report built
                                                  2026-10-02, not yet run
                                                  on the rover.
                                                  Closed-loop wheel speed
                                                  (FR-500-004, feed-
                                                  forward + bounded PI):
                                                  built 2026-10-02, not
                                                  yet run on the rover.
                                                  2026-10-07: rf encoder
                                                  counts near zero while
                                                  the wheel turns (-39,
                                                  0, 1, 16, -10 in runs
                                                  where others counted
                                                  thousands) -> false
                                                  STALL_FAULT latches
                                                  while roaming. Plug
                                                  checked OK; open.

  FR-600 Steering         Not live-verified       Servo V+ current path
                                                  unconfirmed
                                                  Channel map MEASURED
                                                  2026-10-06, one at a
                                                  time: LF3 RF2 LM0 RM1
                                                  LR9 RR8. All six centre
                                                  straight at 1500. INA260
                                                  0x40 saw no current
                                                  while a servo swung:
                                                  servo V+ is not on its
                                                  path (see FR-600).
                                                  2026-10-07: +us turns
                                                  all four corners RIGHT,
                                                  ~15 deg/200 us (by eye).
                                                  Rotation mode (corners on
                                                  the turning circle, spin
                                                  on IMU, sonar/ToF/camera
                                                  watching): built; live
                                                  2026-10-07: LIVE-
                                                  VERIFIED both ways in
                                                  open space: +90 -> +87.8,
                                                  -90 -> -93.8; front and
                                                  rear cameras agree with
                                                  the IMU, check live.
                                                  No rear/diagonal
                                                  sensing: spun into the
                                                  couch once; IMU bump
                                                  stop added and proven
                                                  (stopped in ~1.7 s).
                                                  Wired into brain.py
                                                  (voice turn around/N
                                                  degrees, roam avoidance
                                                  turns): built, not yet
                                                  run in the service.

  FR-700 Arm              Not live-verified       Arm current limit
                                                  (release) built
                                                  2026-10-02, not yet run
                                                  on the rover.
                                                  Both poses applied by
                                                  code since 2026-10-02
                                                  (wave, stow); stow
                                                  opens the elbow before
                                                  the shoulder moves:
                                                  built 2026-10-06, not
                                                  yet run on the rover.

  FR-800 Sensors          PARTIAL --- sonars      Sonar re-proven through
                          connected               Pico B 2026-09-29; IMU
                                                  RST recovery proven
                                                  2026-10-01. Per-channel
                                                  SONAR_FAULT and
                                                  IMU.heading built
                                                  2026-10-02, not yet run
                                                  on the rover.
                                                  SONAR_FAULT debounce
                                                  (2 s): built 2026-10-02,
                                                  not yet run. IMU
                                                  freshness on quat +
                                                  accel, IMU_STALE_S 3.0:
                                                  live-proven 2026-10-02
                                                  (53 false recoveries
                                                  -> 0).
                                                  2026-10-07: ToF
                                                  remounted 180 deg, new
                                                  housing, orientation
                                                  re-measured, floor
                                                  profile saved (rows
                                                  6-7); upper rows report
                                                  anything < 40 cm.
                                                  Second ToF on order.
                                                  7 IMU_FAULTs were the
                                                  Hailo freeze, not the
                                                  IMU (FR-1400-006).

  FR-1500 Voice           PARTIAL --- live-       Wake word/STT/fast-path
                          verified repeatedly,    live-verified and
                          latency real-measured   tuned across several
                                                  sessions (endpointing,
                                                  base.en model, widened
                                                  fast-path matching).
                                                  Local-LLM intent
                                                  parsing (non-fast-path)
                                                  is live-verified on
                                                  CPU only, 75% pass on
                                                  a 32-case reliability
                                                  batch --- see FR-1500
                                                  section and Software
                                                  Design v1.0 Section 7.

  FR-1600 Display         Live-verified           Fault-state expressions
                                                  (frown/red-eyes on
                                                  self-test failure)
                                                  directly observed
                                                  2026-08-23.

  FR-1700 Object          PARTIAL --- detection   Hailo YOLOv8 backend
  Detection/Retrieval     live-verified,          shipped and enabled
                          approach/grasp not      2026-08-21 (FR-1700-001).
                                                  FR-1700-002's range/
                                                  bearing remains
                                                  uncalibrated heuristic
                                                  (per-class widths, not
                                                  one 8 cm: built
                                                  2026-10-02, not yet run
                                                  on the rover).
                                                  FR-1700-003/004 (approach
                                                  planning, grasp) not
                                                  live-verified.

  FR-1000 Autonomous      PARTIAL --- FR-1000-005 Roam-permission gate
  navigation              logic verified          live-verified in
                          off-hardware; the rest  simulation
                          BLOCKED                 (test_brain_roam_
                                                  permission.py, 13 cases).
                                                  FR-1000-001/003 and
                                                  FR-1200-005's standoff are
                                                  BLOCKED: Navigator steers
                                                  by odometry.pose and the
                                                  encoders have produced no
                                                  edges since 2026-08-25.
                                                  FR-1000-002's avoidance is
                                                  SONAR-ONLY today --- the
                                                  encoder half of the reflex
                                                  layer is dead. Added to
                                                  this register 2026-09-13;
                                                  it had no row at all.
                                                  Superseded 2026-10-01:
                                                  encoders count, signed
                                                  (a-0.3, 763/rev, one-
                                                  wheel scale); odometry
                                                  unproven on the floor.
                                                  Rooms and stairs by
                                                  voice, stair standoff,
                                                  IMU-heading odometry
                                                  (off by default), come-
                                                  here search sweep:
                                                  built 2026-10-02, not
                                                  yet run on the rover.
                                                  Come to me (FR-1000-006),
                                                  doorway routing, ask at
                                                  a shut door, avoidance
                                                  turn from sonar + ToF +
                                                  camera: built
                                                  2026-10-06, not yet run
                                                  on the rover.

  FR-900 through FR-1400, Implemented, off-       FR-1300: inbound
  FR-1800 onwards         hardware tested only    remote_cmd.py added
                                                  2026-10-01. FR-1400:
                                                  Claude, owner
                                                  decision 2026-10-02
                                                  (claude-sonnet-5-5).
                                                  FR-2100: identity.py
                                                  store/matcher only.
                                                  Superseded 2026-10-02:
                                                  faces built
                                                  (recognition.py,
                                                  enabled). FR-1900-001/
                                                  002/003 demonstrations,
                                                  FR-2000-011/012/013
                                                  email commands, FR-2200
                                                  feature requests: built
                                                  2026-10-02.
                                                  FR-1400-001 intent gate,
                                                  FR-1900-005/007/008:
                                                  built 2026-10-02.
                                                  Everything dated
                                                  2026-10-01/02 below is
                                                  simulated tests only.
  -----------------------------------------------------------------------

Motion-related groups (FR-400 through FR-700) were gated behind FR-300 passing
--- Directive 2. **That gate is released as of 2026-08-24** by the owner decision
recorded in FR-300's Acceptance Criteria: the E-stop's physical power cut
satisfies FR-300-001/002/003 without a Pi-side sense line. Remaining pre-drive
items are physical, not requirement-level: the steering servo V+ current path (~9A worst case against an
8A UBEC, Master Hardware Design §12 rule 13).

## V.1 Implementation and test coverage (2026-08-18)

The software is 26 modules / ~4,160 lines with 144 off-hardware tests, all
passing under `WILLY_SIMULATE=1`. ⚠ **Stale counts — 2026-10-02:** 33 modules /
~8,490 lines; **476 tests** collected across 66 files under `WILLY_SIMULATE=1`. **Updated 2026-10-07:** CI (GitHub
Actions, `.github/workflows/tests.yml`, Ubuntu, Python 3.13) runs the whole simulated suite on
every push — **520 passed, 0 failed** on `3a288d5`, the first green run.
Later 2026-10-02: +5 test functions (`test_rooms_stairs_memory.py` new, 2;
`test_sensor_gaps.py` +3), so **481 across 67 files** by count — not re-collected;
~8,720 lines.
Recount 2026-10-02 after `80c074f`: **35 modules / ~9,700 lines; 403 `def test_`
functions across 73 test files** (a plain count of `def test_`, which is lower than the
collected figures above because parametrised cases collect as several items; the new
2026-10-02 suites run one subprocess script per function with many assertions each).
Not re-collected on the rover.
Rows marked 2026-10-02 were added for this; the rest of the table dates from
2026-08-18 (full module list: Software Design §1.1). Every requirement group below has an
implementing module. Coverage here means unit tests exist and pass off
hardware; it is not evidence of live behaviour.

  -----------------------------------------------------------------------
  Group                   Implementing module(s)  Test coverage
  ----------------------- ----------------------- -----------------------
  FR-000 Directives       brain.py (_tick          test_safety.py,
                          arbitration order),      test_safety_controller.py,
                          safety.py                test_no_direct_drive_bypass.py

  FR-100 Startup          brain.py::_self_test,    test_config_validate.py,
                          diagnostics.py,          test_sim_hardware.py
                          config.py::validate

  FR-200 Power            brain.py::_update_bat_   test_brain_battery.py
                          tier, sensors.py::ADC,   (2026-10-02:
                          CurrentMonitor           test_battery_halt.py,
                                                   test_battery_crosscheck.py,
                                                   test_current_limits.py)

  FR-300 Safety           safety.py::Safety        test_safety_controller.py
                          Controller

  FR-400/500/600 Motion   motors.py, odometry.py,  test_odometry.py,
                          sensors.py::Encoders     test_tick_timing.py,
                          (motors.wheel_duty,      test_wheel_speed_
                          2026-10-02)              control.py,
                                                   test_brake_no_twitch.py
                                                   (2026-10-02)

  FR-700 Arm              arm.py, arm_jog.py,      test_current_limits.py
                          brain.py::_check_arm_    (2026-10-02)
                          current

  FR-800 Sensors          sensors.py, pico_link.py test_sim_hardware.py,
                          (2026-10-02 row),        test_pico_link.py,
                          tof.py (not wired in)    test_sensor_gaps.py,
                                                   test_tof.py

  FR-900 Manual           brain.py::_manual,       test_brain_manual_drive.py
                          voice.py

  FR-1000 Navigation      navigation.py,           test_navigation.py,
                          pursuit_task.py,         test_mapping.py,
                          mapping.py,              test_world_model.py,
                          world_model.py           test_rooms_stairs_
                                                   memory.py,
                                                   test_sensor_gaps.py
                                                   (2026-10-02 row)

  FR-1100 Diagnostics     diagnostics.py,          test_logsetup.py
                          logsetup.py::log_event

  FR-1300 Smart home      smart_home.py,           test_remote_cmd.py
                          remote_cmd.py            (2026-10-02 row)
                          (inbound, 2026-10-01)

  FR-1400 Cloud AI        ai_provider.py           test_ai_provider.py

  FR-1500 Voice           voice.py                 test_voice_*.py,
                                                   test_brain_voice_*.py,
                                                   test_retrieve_gate.py
                                                   (2026-10-02 row)

  FR-1600 Display         display.py               ---

  FR-1700 Retrieval       retrieval_task.py        test_retrieval_task.py

  FR-1800 Privacy         privacy.py               ---

  FR-1900 Learning        memory_store.py,         test_memory_store.py,
                          world_model.py,          test_storage.py,
                          storage.py, voice.py     test_rooms_stairs_
                          (forget/recall/apply,    memory.py
                          2026-10-02 row)          (2026-10-02 row),
                                                   test_demonstrations.py
                                                   (2026-10-02)

  FR-2000 Email           email_client.py          test_email_commands.py
                          (commands, 2026-10-02)   (2026-10-02)

  FR-2100 Recognition     identity.py (store and   test_identity_store.py
                          matcher only; nothing    (2026-10-02 row)
                          imports it)              test_face_recognition_
                          2026-10-02: +            flow.py (2026-10-02)
                          recognition.py, wired
                          in brain.py/voice.py

  FR-2200 Feature         feature_requests.py      test_feature_requests.py
  requests                (2026-10-02)             (2026-10-02)
  -----------------------------------------------------------------------

## V.2 Known gaps — requirements not currently satisfiable as written

These are recorded so they are not mistaken for untested-but-working. Each is
a real limitation of the current build, flagged in the implementing code
itself rather than papered over.

**G-1 --- CLOSED 2026-08-24 by owner decision, not by implementation.** The owner
authorized that no Pi-side E-stop sense line is required: the E-stop is the main
power switch, which cuts all power (the Pi included), so the cut is absolute and
independent of software. FR-300-001/002/003 are therefore satisfied by hardware
— see the FR-300 Acceptance Criteria section for the full rationale and for what
this explicitly does NOT claim. **FR-300 no longer gates live testing of FR-400
through FR-700.** The technical description below is retained as accurate
background on what software can and cannot see.

**G-1 (original text) --- FR-300-002/003, E-stop is unobservable to software.** The E-stop is
a hardware-only latching cut with no documented GPIO sense pin. Software
therefore cannot detect that it has fired, cannot log it, and cannot enforce
FR-300-003's post-E-stop reset gate. This is a wiring change, not a code gap:
a sense line into a spare GPIO is required before any software can be written
against it. Directive 1 is enforced physically but is not represented in the
control loop.

**Design update 2026-08-23:** two dedicated physical cut switches, SW-M and
SW-A, added to the distribution tree (Master Hardware Design rev 2.2 Section
2.1/2.3) -- SW-M in P3 on the motor supply; SW-A in P6, on the arm servo supply (6V DROK input — was the DZS, replaced 2026-08-28),
**which IS monitored: INA260 0x44 sits on R3, the 6V arm rail. SW-A cuts the 6V DROK's input, so
throwing it collapses R3 and 0x44 would read the drop — making the arm side of G-1
observable in software for the first time. Not yet implemented; see Master Hardware
Design §2.3.** SW-M's placement was intended to close the motor side of
this gap by reading the current monitor then downstream of it (0x44). **That
route closed on 2026-08-28** when 0x44 moved upstream to the +12V main input,
reopening the motor side of G-1. ✅ **CLOSED — hardware
2026-09-08/14, software 2026-09-15.** 0x45 now sits on the +12V bus (measured 11.174V against
an owner-metered pack of 11.36V) and `brain.py::_check_motor_rail()` reads it via the
`'bus_12v'` key, pinned by `tests/test_motor_rail_identity.py`. The arm side (SW-A)
still needs either a new INA260 or a direct switch-state sense.
SW-M and SW-A are branch switches, not the E-stop. **There is no mushroom switch:
the E-stop is the main power switch** (owner, 2026-10-02), which takes everything
down, the Pi included.

>
> ✅ **RESOLVED 2026-09-15 by doing exactly what this note asked** — reading bus voltage at all
> three addresses live, rather than quoting a stored figure. Result: **0x40 = 4.986V (R2 5V),
> 0x44 = 6.043V (R3 6V arm rail), 0x45 = 11.174V (+12V bus)**. R1's 9V has no INA260; the Witty
> Pi HAT monitors its own VIN (owner-stated).
>
> **The owner's rail-based description was the more accurate source.** It named a **6V** monitor,
> and there is one — 0x44, on the arm rail, reading 6.043V against the DROK-6V's 12V→6.0V spec.
> It was overruled here by a `config.py` measurement that was correct when taken and had since
> been invalidated by a physical relocation. The lesson is not "believe prose over measurement"
> — it is that **a stored measurement is a historical claim, not a live one**, and a three-week-old
> number loses to a fresh `i2cget` every time.


**G-2 --- FR-500-002/004, encoder counts ARE under-sampled at speed.
RECOMPUTED 2026-09-13.**

⛔ **Superseded 2026-10-01: `ENCODER_COUNTS_PER_REV` measured = 382** on the fitted 170 RPM motors (see *Resolution* below). That is ×1 — Phase A rising edges only (Pico A firmware; Phase B dead since 2026-09-18), not ×4 quadrature, so 752, 422 and 1562 below are all wrong for the current transport. The 752 arithmetic is kept as the reasoning trail. **Superseded again 2026-10-01: 763** — Phase B is alive on the new motors (the dead greens were the old ones); Pico A a-0.3 decodes signed x2, exactly 2 × 381.6.

With the measured values:

-   `ENCODER_COUNTS_PER_REV` = **752**, not 3292 --- 11 PPR × 4 quadrature × **17.1:1**
    reduction (`config.py:119`; Master Hardware Design §7.1). The 823.1 PPR /
    74.8:1 figures were never real **for the motors fitted today.** ⚠ **They do not
    become real for the 170 RPM replacements either** — 74.8:1 on a ~10,600 RPM bare
    motor is ~142 RPM output, not 170, so 3292 goes from 4.4× wrong to ~1.2× wrong.
    That is the more dangerous error, because a 20% odometry discrepancy reads as
    wheel slip. Neither number is right for them; see Master Hardware Design §7.1,
    *Motor change pending*.
-   **620 RPM is the OUTPUT speed**, which the old text treated as unresolved.
    `config.py:123` settles it --- 620 RPM from a ~10.6k RPM bare motor through 17.1:1
    --- and it is corroborated by the ~3.3 m/s theoretical top speed on 101.6 mm wheels.

So at full speed:

    620 RPM / 60 × 752 counts/rev  =  ~7,770 Hz per channel

**~7.8 kHz against `sensors.py`'s ~1 kHz poll ceiling --- roughly 8× oversubscribed.**
**Expect under-sampling at speed and plan for it.** The per-channel rate is close
to 8.5 kHz, not the few hundred Hz a lower counts-per-rev figure would imply.

⚠ **Reverted 2026-09-27 — this note flipped twice; here is the arithmetic.** The JGA25-370 family runs **one ~6,000 RPM motor** behind every gearbox (multiply any row's no-load speed by its ratio and you get ~6,000 every time), so the bare speed does not change across the swap. Fitted: **9.6:1, 422 counts/rev, 620 RPM → 4,365 counts/s per wheel.** On order: **35.5:1, 1562 counts/rev, 170 RPM → 4,426.** Within 1.5%. Yesterday's "it falls 1.78×" was computed from an assumed 10,600 RPM bare motor — the same inference that produced the wrong 17.1:1 ratio. **The original claim was right: a slower rover is not a slower encoder.** Still ~4× the ~1 kHz poll ceiling, so PIO decode is required either way.

⛔ **And 752 is wrong for the motors fitted right now** — the table makes them 9.6:1, so it should be **422**, and `odometry.py` is under-reporting distance by 1.78×. See Master Hardware Design §7.1. **Superseded 2026-10-01: the 9.6:1 motors are out; the 170 RPM replacements measured 382 (×1); 763 under a-0.3's x2.**

**Resolution:** bench test, not more arithmetic --- drive one wheel a known number of
turns **under power** and read the counts. ⚠ **Not by jogging or hand-turning:** the
encoder is behind the 17.1:1 gearbox and does not back-drive (30s by hand gave one
distinct pin state on 2026-08-25; 3s of driving gave seven), and
`scripts/encoder_calibration.py` is built on hand-turning and is therefore invalid
here. This settles counts/rev and the gearbox ratio together, and is the same bench
session already needed to confirm `WHEEL_DIAMETER_M`. ⚠ **Wait for the 170 RPM motors**, delivered 2026-09-26 — calibrating the 17.1:1
motors measures hardware that is being removed. The part number `JGA25-370-35.5K` gives **35.5:1**, so the target is **1562
counts/rev** (assumes ×4 — superseded, see below). ⛔ **Run the counts-per-rev step on the FITTED motors first** — it is the
only chance to test whether they really are 422 rather than the recorded 752. `WHEEL_DIAMETER_M` and `TRACK_WIDTH_M` are independent of the swap
and can be settled now.

✅ **RESOLVED 2026-10-01: `ENCODER_COUNTS_PER_REV` = 382, MEASURED** (owner + Claude, on the rover).
Left-front wheel driven at 0.35 duty until Pico A counted 3905 Phase-A edges, hard-braked;
3911 final (6 coast) over **10.25** tape-marked turns = 381.6, ±~5 from judging the stop.
This is **×1** (Phase A rising edges only), so **1562 was wrong** — it assumed ×4 quadrature.
It is 2.3% under the 11 × 35.5 = 390.5 prediction (effective ratio ≈ 34.7:1). One wheel only.
⚠ **Hand-turning failed again** (459, then 0, counts for 10 turns while powered driving counted
normally) — the hub likely slips on the shaft when back-driven. Measure under power only.
**Re-measure once Phase B is repaired** and firmware decodes ×4: expect ≈1526.
**Superseded 2026-10-01:** Phase B was never broken on these motors — the six dead greens
belonged to the OLD ones. Pico A **a-0.3** decodes signed **x2** (both edges of A, B sampled
at each), so `ENCODER_COUNTS_PER_REV` = **763**, exactly 2 × 381.6 (same edges, both counted).
382 was right for a-0.2's ×1. ×4 is not planned.

**If polling does turn out to be too slow: raise the I²C bus speed, not
interrupt-driven decode.** `dtparam=i2c_arm_baudrate=400000` (~4x the
current rate) is a software-only fix with no wiring, and the bus already
carries an LTC4311 specifically to make higher speeds viable across this
bus's capacitance. Test it against a full **eleven**-device roll-call first, given
this session's history of real I²C fragility on this bus. (**Ten** once the
MCP23017 leaves under Master Hardware Design §4.7 — and at that point this whole
question is moot for encoders, which no longer sit on I²C at all.)

**Interrupt-driven decode (decided 2026-08-18) --- retracted 2026-08-23, do
not implement as designed.** Three independent problems, not one:

1. **Galvanic isolation — NOT A REASON.** There is no isolation barrier on this
   bus and never effectively was. **Do not cite galvanic isolation as a blocker in
   future decisions.** The retraction stands on reasons 2 and 3,
   which are unaffected.
2. **Saves no I²C transactions.** INTA only reports "something on port A
   changed" --- actually learning what changed still requires an I²C read
   (`INTCAP` or `GPIO`). Every edge costs a bus transaction either way, so
   interrupt-driven is not cheaper than the current code, which already
   decodes all twelve channels from two register reads per poll. It is
   arguably *worse*: one transaction per edge versus one transaction per
   poll interval covering everything.
3. **Incomplete even on its own terms.** INTA covers port A only; LR and RR
   live on port B (`GPB0-GPB3`), so INTB would also be needed --- but GP7
   was the only free pin identified for this. There is also a stuck-
   interrupt failure mode: if edges arrive faster than userspace services
   them, INT never deasserts.

`config.ENCODER_INT_PIN` (GP7) and the `IOCON.MIRROR`/`INTCON`/`GPINTEN`
configuration in `sensors.py::Encoders` reflect this retracted design and
need to be reverted along with this doc change --- see Software Design rev 1.1
S-2. GP7 reverts to free/unused pending a different use.

**G-3 --- FR-1700-005, grasp is a fixed primitive sequence, not planning.**
No per-joint arm calibration has been run (§20.6), so no reach-envelope model
exists to plan a grasp pose against. The implemented sequence --- rotate base
toward bearing, open gripper, lower by a fixed offset, close, raise --- is a
working approximation. `arm_jog.py` is the tool that closes this; nothing else
does.

**G-4 --- FR-1700-006, hand-off confirmation is timed, not sensed.** The
implementation waits for either an explicit voice confirmation or a fixed
timeout before releasing, so the rover cannot detect that the person has
actually taken the object.

⚠ **The hardware half of this gap is closed. The software half is not.**
The FSR402 was removed 2026-10-04. The gripper sense is now **position feedback
from the gripper servo itself**: its pot wiper feeds ADS1115 **A2** through a
47k/47k divider (Master Hardware Design §6.6, §16.14). `sensors.ADC.grip_feedback_volts()`
reads it, but it is **uncalibrated** and nothing consults it —
`retrieval_task.py:18` still records the hand-off as time-based, correctly.
This item stays open until `scripts/grip_feedback_curve.py` has produced the
free-travel curve and `_await_confirm()` uses it: jaw stalled short of its
command = holding; jaw jumped back to its command = taken.

**G-5 --- watchdog and tick-overrun thresholds are inconsistent.**
`willy-rover.service` now sets `WatchdogSec=500ms`, which requires the process
to send `WATCHDOG=1` at least every 250ms. `brain.py`'s run loop is a tick plus
a 50ms sleep, and `config.TICK_OVERRUN_THRESHOLD_S` is 0.15s --- so a tick may
run 150ms and merely *log* an overrun, while a tick of 200ms or more silently
crosses the systemd deadline and the service is killed and restarted, possibly
mid-motion. The threshold that logs sits below the threshold that kills. Either
raise `WatchdogSec` or lower `TICK_OVERRUN_THRESHOLD_S` so the warning fires
before the kill, not after.

Note also that `brain.py` carries a 2026-08-08 audit comment stating no
`WatchdogSec` is configured, confirmed at the time via `systemctl cat`. The
repository unit file now sets one. Either the unit was updated and the comment
not revised, or the installed unit on Willie differs from the repository copy.
Confirm with `systemctl cat willy-rover.service` on the rover before relying on
either.

**RESOLVED 2026-09-07 --- it was the second one: the installed unit differed.**
Checked on the rover: `/etc/systemd/system/willy-rover.service` was
byte-identical to the repository copy except for a single missing line,
`WatchdogSec=500ms`, and `systemctl show -p WatchdogUSec` returned `0`. The
repository file had been correct since 2026-08-02 (`df24199`) and simply was
never deployed --- a stale unit for over a month.

**No systemd watchdog was armed at all** between 2026-08-02 and 2026-09-07, so
none of the mid-tick kills described above could actually have occurred. The
`f18af62` call was a real defect against the documented design and against
`ask_sync()`'s contract, and is still worth having fixed --- but it was never
killing the process in the field, and this
register should not be read as saying it was.

The inverse gap ran for the same period and is the more serious one:
`brain.py`'s `sd_notify` `WATCHDOG=1` was a no-op, so a genuinely wedged tick
loop would never have been restarted by systemd. The Witty Pi 5 HAT's own
watchdog (200 missed heartbeats, ~10-20s) was the only live backstop the whole
time.

**Attempting to arm it the same day proved the repository unit is unusable as
written.** The repo unit was installed and `daemon-reload`ed on 2026-09-07. The
service then entered a permanent crash loop --- SIGABRT roughly 500ms after
every start, four starts in twenty seconds, never reaching its own first log
line --- and was reverted to the previously installed unit within the hour. The
rover was left stopped rather than cycling.

Root cause, confirmed on the rover: the unit is `Type=simple`, so
`NotifyAccess` defaults to `none` and **systemd discards every `sd_notify`
message the process sends**. `brain.py`'s `WATCHDOG=1` was never received by
anything, so no heartbeat rate could satisfy the deadline and the watchdog
fired unconditionally on a timer from each start. This is not a threshold
tuning problem and no `WatchdogSec` value would have fixed it.

Two preconditions must both be met before this line goes back:

1. `Type=notify` (or at minimum `NotifyAccess=main`), so the heartbeat is
   actually received. Without this, `WatchdogSec` is not merely wrong, it is
   inert-then-fatal.
2. A `WatchdogSec` matched to measured startup. `brain.py` sends `READY=1` only
   after init passes, and init loads a 1.7GB Hailo HEF plus the vision and voice
   models. Under `Type=notify` that same figure also becomes the startup
   deadline, and a failed self-test that never sends `READY=1` would then count
   as a failed start --- a behaviour change worth deciding on deliberately.

**Update 2026-09-14 --- both preconditions are now implemented and staged, and
one of them was misunderstood until it was tested.** Nothing is installed; the
watchdog still has never run in this deployment. What changed is that arming it
is now a measurement and a bench session rather than an open design question.

Precondition 1 is met by `willy-rover-watchdog.service.prepared` --- a separate
unit carrying `Type=notify` and `NotifyAccess=main`, deliberately named
`.prepared` so a wildcard copy into `/etc/systemd/system` cannot pick it up.
It is a *second* unit rather than an edit to `willy-rover.service`, so rollback
is one command.

Precondition 2 is met by `scripts/measure_startup.py`, which produces the two
numbers nobody had: wall time to `READY=1`, and the worst gap between
`WATCHDOG=1` heartbeats. It launches `main.py` with its own `NOTIFY_SOCKET`, so
it observes exactly what systemd would receive without installing a unit, using
`systemctl`, or disturbing a running rover. It reports the **worst** startup
rather than the median, because under `Type=notify` that figure is the start
deadline and a cold page cache or a retried I²C probe lands on the tail.

**The behaviour change flagged above --- "a failed self-test that never sends
`READY=1` would count as a failed start" --- turns out not to apply.** `brain.py`
sends `READY=1` on *both* the pass and fail branches of the self-test
(`RoverBrain.start`), so a rover that fails its self-test comes up degraded with
motion disabled and stays up, rather than being restart-looped by systemd. That
is the desired behaviour and it is now pinned by
`tests/test_sd_notify.py::test_ready_is_sent_even_when_the_self_test_fails`,
because moving that call inside the success branch would silently convert a
recoverable degraded state into a crash loop on a rover that cannot see its own
sensors.

**A third problem was found by testing the prepared unit rather than reasoning
about it, and it is the most dangerous of the three.** The unit's two timing
values are `__MEASURE__` placeholders. The assumption was that systemd would
reject them. It does not --- verified with `systemd-analyze`:

```
Failed to parse TimeoutStartSec= parameter, ignoring: __MEASURE__
Failed to parse WatchdogSec=__MEASURE__, ignoring: Invalid argument
```

systemd logs a warning, **ignores both lines, and starts the unit with the
defaults** --- and the default `WatchdogSec` is *disabled*. So the failure mode
of installing it half-finished was not a refusal to start; it was a rover coming
up perfectly cleanly while whoever installed it believed a watchdog was running
and nothing was watching at all. That is the same silent-failure shape as the
original `Type=simple` defect: a protective mechanism that is inert while
appearing configured. The refusal is now enforced explicitly by an
`ExecStartPre` guard that fails the start while any placeholder remains,
verified in both directions.

Bench validation before arming is procedure **W-1** in
`docs/WildWilly_Bench_Test_Procedures.md`: measure, fill both values,
sanity-check `WatchdogSec` against `TICK_OVERRUN_THRESHOLD_S` (a watchdog below
the tick-overrun threshold kills the process before it has logged that it was
running slow, destroying the evidence for why it died), then ten restarts with
the rover on blocks, then an induced stall to confirm the watchdog actually
bites. The software half is already verified --- `tests/test_sd_notify.py` (6)
covers the wire format, inertness without `NOTIFY_SOCKET`, abstract-socket
translation, and that a dead socket never raises into the 20 Hz tick loop.

`WatchdogSec` is commented out in the repository unit as of 2026-09-07 with
these preconditions recorded inline, so the next person cannot arm it by
copying the file. **The watchdog has therefore still never run in this
deployment**, and the threshold-ordering advice at the top of this gap remains
hygiene rather than something load-bearing --- `TICK_OVERRUN_THRESHOLD_S=0.15`
against a hypothetical ~200ms kill line, with the overrun log only executing
after `_tick()` returns. Settle preconditions 1 and 2 on the bench first; the
threshold ordering matters only once a watchdog can actually fire.

**Update 2026-08-18 (same day):** the two known code paths that could actually
push a single tick anywhere near the 500ms/250ms figures above --- `retrieval_
task.py`'s `_grasp()` and `brain.py`'s wave-hello gesture, both previously
blocking via `time.sleep()` for roughly 1.1s and 1.5s respectively inside one
tick call --- have been converted to non-blocking, tick-serviced step machines.
No other per-tick blocking call is currently known. This closes the *known
cause* of a mid-tick kill, not the risk structurally: nothing enforces that no
future code path blocks a tick for hundreds of milliseconds, and this
reconciliation itself is unverified on live hardware, same as everything else
in this register. The threshold-ordering advice above (raise `WatchdogSec` or
lower `TICK_OVERRUN_THRESHOLD_S`) still stands as general hygiene regardless.

**Update 2026-09-07 --- the structural risk named above materialised, and is
now closed again.** Commit `f18af62` (2026-09-01) added a synchronous Hailo
LLM `generate_all()` call to `brain.py::_stuck()`, executed directly on the
tick thread. That is a full autoregressive generation inside one tick, against
a 250ms heartbeat deadline --- the mid-tick kill this gap describes, arriving
at the worst possible moment, since STUCK is by definition the state entered
when the rover is already up against an obstacle. It also violated
`ai_provider.py::ask_sync()`'s documented contract ("only for callers already
off the tick thread"). Nothing caught it for six days: `brain.py`'s own
comment still asserted no per-tick blocking call remained, and the commit
claimed "~10-50ms inference" without a measurement.

`_stuck()` was moved onto `HailoIntentModel`'s `request_async`/`poll_async`
worker thread on 2026-09-07, matching the Claude path, so a slow on-device
decision now costs extra STUCK ticks rather than the process. The lesson for
this register is that "no other per-tick blocking call is currently known" is
a claim with a shelf life --- re-verify it whenever an AI provider or task is
added, rather than treating the 2026-08-18 update above as settled. The
threshold-ordering advice (raise `WatchdogSec` or lower
`TICK_OVERRUN_THRESHOLD_S`) is still not done, and would have made this
visible as a logged overrun before it became a kill.

**G-6 --- FR-1500, Hailo NPU intent parsing: root cause found and fixed
2026-09-14. Gap narrowed sharply, not closed.**

> **The 0% was our bug, not the model's**, and it was diagnosed wrong for weeks
> by reasoning from the symptom rather than the bytes. **Read the artifact before
> theorising from an error string.**
>
> **What was actually happening.** The Hailo model is Qwen2. It ships a ChatML
> chat template (`llm.prompt_template`) and its stop tokens are `<|im_end|>` and
> `<|endoftext|>`. `generate_all()` does **not** apply that template --- it takes
> one raw string and continues it. `hailo_llm.py` handed it a bare instruction
> with no role markers, so it did exactly what a completion model should do when
> handed a template: it continued the template. The captured completion is the
> prompt's own JSON skeleton echoed back five and a half times, 820 characters,
> containing no answer at all:
>
> ```
> {"intent":"<short action name>","args":{},"reply":"<what to say back, <200 chars>", ...
> {"intent":"<short action name>","args":{},"reply":"<what to say back, <200 chars>", ...
> ```
>
> **The "recurring JSON truncation" recorded below was never truncation.** 20 of
> 32 failures reported `Expecting value: line 1 column 97 (char 96)`. Character
> 96 is exactly where `"confidence":<0.0-1.0` begins, and `<` is the first token
> `json.loads` refuses. The offset was identical on every failure because the
> echoed skeleton is a *fixed string* --- the signature of a constant, not of a
> length limit. Raising `max_generated_tokens` to 256 changed the failure count
> by exactly zero, which is the confirming evidence.
>
> **Two numbers are reported below, and the difference between them matters.**
> The batch scores `bool(args) == expects_args`, so a spurious `args` on an intent
> that takes none counts as a failure. On the rover that is inert: `brain.py`
> reads `args` only for `retrieve` (`object`), `go_to` (`room`/`x`/`y`) and the
> movement intents (`speed`/`duration`) --- verified at `brain.py:753-781`.
> For `status`, `battery`, `arm_stow`, `arm_home`, `wave`, `come_here`, `follow`,
> `diagnostics`, `shutdown`, `where_are_you` and `what_do_you_see` it is never
> read. So "actionable" below means *correct intent, plus usable args where the
> rover actually consumes them* --- how often Willie would do the right thing.
>
> **The batch itself was not changed.** A benchmark loosened after seeing your
> score is not a benchmark. Its pass rate remains the number of record.
>
> | backend | batch pass | parsed | actionable |
> |---|---|---|---|
> | Hailo, before (2026-08-23 and 2026-09-14 re-run) | 0% | 19% | **16%** |
> | Hailo, after | 25% | 91% | **78%** |
> | CPU `LocalAIProvider`, before | 69% | 100% | **72%** |
> | CPU `LocalAIProvider`, after | 97% | 100% | **97%** |
>
> Note the CPU path improved too, from a change made for the Hailo path's sake.
> The old prompt was costing it 25 points and nobody knew, because the CPU number
> had not been re-measured since 2026-08-23 either.
>
> **Three changes, in the order they were found. Only the first is the root cause.**
>
> 1. **ChatML framing** (`hailo_llm.py::_chatml`). The fix. Hailo parse rate
>    19% -> 91%.
> 2. **Payload normalisation** (`ai_provider.py::_normalise_payload`). Small models
>    fail in opposite directions on one shared prompt: Hailo pads `args` with the
>    placeholder `{"object": "<the object>"}`, the CPU model omits `args` entirely.
>    Both had correct intents thrown away. A value that is entirely angle-bracketed
>    is placeholder text the model copied from its instructions --- never a real
>    object name, and dangerous to pass to retrieval, which would go looking for
>    something called "the object" --- so it is dropped. A missing `args` defaults
>    to `{}`, because `args` is a container and an absent one carries no less
>    information than an empty one. `intent` and `reply` get no such treatment;
>    they are content, and defaulting them would invent an action or invent speech.
> 3. **Prompt rewrite** (`voice.py` and the batch, kept identical). Every
>    angle-bracket placeholder removed, two worked examples added, and the four-key
>    contract stated explicitly rather than implied.
>
> **Sampling parameters were the first hypothesis and they were wrong.** Tuning
> temperature and top_p moved the score by one case out of 32, i.e. noise. They
> are now passed explicitly (`HAILO_LLM_TEMPERATURE`, `HAILO_LLM_TOP_P`,
> `HAILO_LLM_MAX_TOKENS`) because leaving four generation parameters at `None` is
> wrong on its own merits, but nothing should read that as the fix. **Record a
> hypothesis you abandoned** — a plausible wrong one that gets quietly dropped is
> how a misdiagnosis survives.
>
> **The prompt lives in two places and must stay in sync.**
> `voice.py::_interpret_local()` is what the rover sends;
> `experiments/llm_reliability_batch.py::_build_prompt()` is what the score is
> measured against. A batch result against a prompt `voice.py` does not use is
> worthless. Their rendered tails are verified character-identical. **Keep them
> that way or this number stops meaning anything.**
>
> **QUALIFICATION RUN 2026-09-14 — the evidence is now in the repository, not in
> a commit message.** The 2026-09-14 review's first finding was fair and worse
> than stated: the batch results quoted above lived in `/tmp` on the rover, which
> a power cycle wipes. Nothing in git let anyone check them. That is fixed:
> `experiments/hailo_qualification.py` writes a JSON artifact holding every
> per-case record — payload, confidence, latency, outcome — and the artifact is
> committed alongside the conclusions drawn from it
> (`experiments/results/2026-09-14-hailo-qualification.json`).
>
> **96 calls through ONE long-lived `HailoIntentModel`** (3 repeats × 32 cases),
> at the shipped settings: temperature 0.1, top_p 0.9, max_tokens 256.
>
> | outcome | count | of 96 |
> |---|---|---|
> | actionable (correct intent, usable args, has a reply) | 77 | **80.2%** |
> | wrong intent | 10 | 10.4% |
> | parse failure | 9 | 9.4% |
> | strict batch pass (`bool(args) == expects_args`) | 26 | 27.1% |
>
> **Repeated-call stability — the 2026-08-23 context defect is gone.** The old
> failure mode was insidious because call 1 worked and later calls decayed as
> conversation context accumulated. Driving the whole sequence through one
> instance three times shows no decay whatsoever:
>
> | repeat | actionable / 32 | parse failures | median latency |
> |---|---|---|---|
> | 1 | 26 | 3 | 4.86s |
> | 2 | 25 | 3 | 4.86s |
> | 3 | 26 | 3 | 4.81s |
>
> Flat, not monotonic. `clear_context()` in the `finally:` block is doing its job
> and **must not be replaced with anything weaker** — `tests/test_hailo_statelessness.py`
> exists to make that regression loud.
>
> **The remaining failures are deterministic, not random**, which is temperature
> 0.1 behaving as intended and makes them individually fixable rather than a
> matter of luck. The same four utterances fail identically in all three repeats:
>
> | expected | returned | occurrences |
> |---|---|---|
> | `retrieve` | `arm_home` | 3 of 3 |
> | `arm_stow` | `arm_home` | 3 of 3 |
> | `wave` | `where_are_you` | 3 of 3 |
> | `stop` | `where_are_you` | 1 of 3 |
>
> Every one of these self-reported confidence 0.8–1.0. `arm_stow → arm_home` is
> the benign kind: both currently alias to `center_all()` at `brain.py:807`, so
> the rover does the same thing either way.
>
> **`stop → where_are_you` is not benign, and it deserves its own decision.** The
> utterance was **"whoa whoa please stop right now"**, returned as
> `where_are_you` at confidence 0.8. `voice.py::_fast_path()` does hold a stop
> pattern (`stop|halt|freeze|hold (it|on|up)|stop moving|stand still|whoa`) and
> it is matched with `fullmatch`, which is the right conservative choice and was
> explicitly endorsed in the 2026-09-14 review — it is what stops "don't stop"
> from halting the rover, pinned by `tests/test_voice_fast_path.py`.
>
> But `fullmatch` means a stop request phrased as a **sentence** does not match,
> falls through to the model, and is then only as reliable as the model. Measured:
> on this utterance it is not reliable at all. So the trade-off is real and it now
> has a number attached — bare "stop" is safe by construction, conversational
> "please stop right now" is not.
>
> **DECIDED AND FIXED 2026-09-14.** `voice.py::is_emergency_stop()` now claims natural stop language
> deterministically, before any model is consulted.
>
> It was **not** fixed by making the matcher broader, which the owner explicitly
> ruled out. Nor by switching `fullmatch` to a keyword search — that would have
> broken an existing requirement, since `tests/test_voice_fast_path.py` pins that
> "we should stop soon" must NOT fire. Discussing stopping is not commanding it.
> Instead the structure stays `fullmatch` — which is what makes a negation
> structurally impossible to admit — and what widened is the *vocabulary* of
> interjections and intensifiers around a narrow imperative core. An
> unanticipated phrasing still falls through to the LLM exactly as before. An
> explicit negation guard sits in front as defence in depth, so the requirement is
> legible to whoever widens the prefix list next rather than merely emergent.
>
> Ordered **after** the existing fast-path table, so a task-directed stop
> ("stop mapping") is still claimed by its own pattern rather than swallowed.
>
> `tests/test_emergency_stop_phrases.py` (40) pins 24 phrasings that must reach the
> deterministic path and 12 that must not, plus that `_fast_path` takes no provider
> argument — a stop cannot acquire a dependency on a model — and that stop is
> dispatched to `stop_requested` rather than queued.
>
> **The remaining exposure is latency, not classification.** A wake-word turn plus
> STT is ~17s end to end, so voice is not an emergency stop under any
> implementation. The physical control remains the emergency stop; this change
> makes the voice path reliable, not instant.
>
> **Why this gap stays open.**
>
> 1. **`ENABLE_HAILO_LLM=True` still makes this the PRIMARY intent parser**, with
>    Claude demoted to a fallback below `HAILO_LLM_CONFIDENCE_FLOOR=0.7`. That flag
>    was set on 2026-09-01 while this scored 0%, and it is deliberately not changed
>    here --- it is a live-behaviour decision for the owner, now that there is
>    finally a real measurement to make it against.
> 2. **The "0.7 confidence floor" is not a confidence threshold, and cannot be
>    tuned.** `brain.py:1007` compares `HAILO_LLM_CONFIDENCE_FLOOR` against
>    `AIResult.action_confidence`, and `ai_provider.py::_action_confidence()`
>    returns **only 1.0 or 0.0** — 1.0 when the action name is recognised and
>    duration/speed are in range, 0.0 otherwise. It is a boolean structural gate
>    wearing a threshold's name. Every value in (0.0, 1.0] behaves identically;
>    only 0.0 (admit invalid actions) and >1.0 (reject everything, making STUCK
>    recovery fully cloud-dependent) would change anything. Earlier entries in
>    this register — and `config.py` — repeatedly advised "tune the floor against
>    real output", which was advice to adjust a number that does nothing.
>    Pinned now by `tests/test_confidence_gate_semantics.py`.
>
>    **The residual risk on the motion path is therefore not the one previously
>    described.** It is not a confidently-wrong answer sneaking past a threshold;
>    it is a **structurally valid but semantically wrong** action — `forward,
>    2.0s` into the obstacle that caused the STUCK — which scores exactly 1.0 and
>    proceeds without cloud review. No confidence number would catch that.
>    `safety.py`'s clamps and the reflex layer are the only things between it and
>    the wheels, which is why `tests/test_no_direct_drive_bypass.py` matters more
>    than the floor does.
>
> 3. **The model's self-reported confidence IS load-bearing on the voice path,
>    and is now calibrated for the first time.** `voice.py:467` compares
>    `intent_confidence` against `LOCAL_LLM_CONFIDENCE_FLOOR=0.55`. Measured over
>    96 calls (`experiments/results/2026-09-14-hailo-qualification.json`):
>
>    | | count | correct | precision |
>    |---|---|---|---|
>    | self-reported confidence ≥ 0.7 | 83 | 73 | **88.0%** |
>    | self-reported confidence < 0.7 | 13 | 4 | 30.8% |
>
>    So roughly **one confident answer in eight is wrong**, and every wrong answer
>    in the run self-reported 0.8–1.0. The self-report is informative — 88% versus
>    31% is a real separation, not noise — but it is nowhere near a safety
>    interlock. Note also that 4 of the 13 escalations would have been right, so
>    the floor costs some correct answers to buy that separation.
>    *(2026-10-02: the floor is no longer the only escalation signal. An unparseable
>    answer, or an intent outside `voice.py::_ACTIONABLE_INTENTS`, is now scored 0.0 —
>    "not understood" — whatever the model reported (FR-1400-001). Built 2026-10-02, not
>    yet run on the rover. A confident wrong answer that names a* valid *intent still
>    passes; this catches invented intents only.)*
>
> 4. **Latency, measured 2026-09-14 (was unmeasured).** Median **4.86s**, p90
>    5.47s, max 8.53s, min 3.89s over 96 calls — against a pre-fix range of 12s to
>    over two minutes. Using the live voice-turn figures in `config.py:511`
>    (stt 12.1s, tts 4.6s), a median turn now lands near **21.6s**. Better by a
>    large margin and still slow for conversation; STT, not the LLM, is now the
>    dominant cost, which redirects where any further latency work should go.
>
> 5. **The motion path: BENCHMARKED AND FIXED 2026-09-14** — see the motion-path
>    section below.
>
>    schema (`{intent, args, reply}`). The STUCK path uses `_MOTION_SCHEMA`
>    (`{action, duration, speed}`) with a different prompt built at
>    `brain.py:1040` — and that prompt still contains the angle-bracket
>    placeholders (`"duration":<float>`, `"speed":<0.0-1.0>`,
>    `"reason":"<60 chars>"`) whose literal echoing was the entire cause of the
>    0% on the intent path. The defect that was fixed in one prompt was never
>    swept out of the other. **This is the next P0**: the unmeasured path is the
>    one that drives the wheels.
>
> **MOTION PATH — measured for the first time, and a live safety defect found and fixed
> 2026-09-14.** Item 5 above said the motion path had never been benchmarked. It has now,
> by `experiments/motion_reliability_batch.py`, and the gap was not theoretical.
>
> **What the shipped prompt was doing.** The STUCK prompt at the time asked for
> `{"action":"forward"|...,"duration":<float>,"speed":<0.0-1.0>,"reason":"<60 chars>"}`
> — the same angle-bracket placeholder syntax whose literal echoing caused the intent
> path's 0%. The ChatML fix had been applied to the intent prompt and never swept into
> this one. Across 30 calls over 10 scenarios:
>
> | | before | after |
> |---|---|---|
> | parsed | 53.3% | **100%** |
> | structurally valid, would execute | 53.3% | **100%** |
> | **unsafe AND would execute** | **33.3%** | **0%** |
> | escalated to cloud | 46.7% | **0%** |
> | actions returned | `forward` ×16, nothing else | `stop` ×26, `forward` ×3, `wait` ×1 |
>
> **Every single parsed answer was `forward`** — for a fully blocked front, for boxed in
> on three sides, for 25° of tilt. Those score `action_confidence` 1.0, which means they
> clear the `brain.py:1007` gate and drive the rover **without cloud review**. One STUCK
> decision in three. The scoring rule is not invented here: it is `_MOTION_SYSTEM`'s own
> text, "never forward if front<15cm. Stop if tilt>22deg."
>
> The CPU provider failed the same prompt differently — 10% parsed, 90% escalated, 0%
> unsafe — so the defect was not Hailo-specific. Both are now 100%/0%.
>
> **The fix, and the structural half of it.** The prompt now names the six legal actions
> explicitly, restates the two safety rules in the user turn beside the actual measured
> clearance rather than only in the system turn, carries two worked examples showing
> *different* actions (one example teaches a constant — on the intent path the model
> copied the single example's object name into unrelated answers), and contains no
> angle brackets.
>
> More importantly it now exists **once**, as `ai_provider.build_stuck_prompt()`, imported
> by both `brain.py` and the harness. It previously lived as a literal in `brain.py` with
> a hand-kept copy in the measurement code — the same divergence trap that made the
> intent prompt untrustworthy and had to be managed by discipline alone. A score measured
> against a prompt the rover does not send proves nothing.
> `tests/test_stuck_prompt.py` (11) pins the prompt's properties, asserts both callers use
> the shared builder, and sweeps the repo for the old literal — AST-based, so docstrings
> may still quote it to explain the history while no live code may build it.
>
> **What is NOT fixed, stated plainly: the model is now safe but passive.** It answers
> `stop` to every blocked scenario and never `turn_left`, `turn_right` or `reverse` —
> which are the manoeuvres that actually recover from being stuck. It even answers `stop`
> on open floor. So the AI is no longer dangerous and is not yet contributing much: a
> `stop` decision returns through `_apply_ai_motion` to ROAM, where the reflex layer's own
> avoidance does the real work. That is a far better failure than driving into the
> obstacle, and it is still a failure.
>
> **Recovery quality is the next measured item**, and it now has a baseline to be measured
> against, which is the part that was missing before. Resist fixing it by loosening the
> safety language in the prompt: that language is what took the unsafe rate from 33% to
> zero, and the previous three attempts to tune this family of prompts each fixed one
> model by breaking another.
>
> **WHY THE MODEL IS CONFIDENTLY WRONG — answered 2026-09-14, and it closes the
> confidence-tuning question for good.** Full per-case classification, with raw model
> output, in `experiments/results/2026-09-14-failure-classification.md` and its JSON.
>
> The self-reported confidence is a **stylistic artifact of a fluent completion, not an
> estimate**. Over 96 calls the distributions are identical:
>
> | self-reported confidence | correct (n=76) | wrong (n=11) |
> |---|---|---|
> | 0.8 | 28 | 7 |
> | 0.9 | 32 | 2 |
> | 1.0 | 13 | 2 |
>
> The model **never emitted a value below 0.8 for any case**. It writes the confidence
> field the way it writes the `reply` field: plausible text of the requested shape, with no
> internal uncertainty behind it. **Therefore no threshold can filter this model's errors —
> not 0.7, not 0.9, not any value** — because a gate can only separate populations that
> differ, and these do not. That is a stronger result than item 2 above: even on the voice
> path, where the model's number *is* read, it carries no information.
>
> Wrong answers are not random. All 11 collapsed into just two attractor intents —
> `arm_home` (6) and `where_are_you` (5) — so the model is not choosing badly among sixteen
> intents, it is falling back to the same two when it fails to match.
>
> **The CPU model got 11 of 11 of those right**, on the same prompt and schema. So this is
> model capability, not prompt engineering — which is the evidence for not spending another
> pass on prompt or sampling tuning.
>
> Category totals: 52 of 96 are `normalization_gap` (correct intent, spurious `args` that
> the benchmark scores as failure and the rover ignores), 21 strictly actionable, 11
> confident-wrong, 9 parse failures, 3 correct-but-escalated. **73 of 96 (76%) produced the
> correct intent** — the largest bucket is not wrong answers but correct ones the benchmark
> penalises.
>
> 24 of 32 utterances fail identically in all three repeats, so these are reproducible
> defects rather than sampling noise, and each is individually addressable.
>
> **The one failure with a safety consequence** was `stop` -> `where_are_you` at confidence
> 0.8 for "whoa whoa please stop right now". **FIXED 2026-09-14**: `voice.py::is_emergency_stop()`
> now claims natural stop language deterministically, before any model is consulted, while
> preserving the negation protection ("don't stop", "never stop", "we should stop soon" all still
> fall through). It stays fullmatch rather than a keyword search precisely so that protection
> survives; what widened is the vocabulary of interjections and intensifiers around the imperative
> core. 24 stop phrasings and 12 must-not-fire phrasings are pinned by
> tests/test_emergency_stop_phrases.py. The decision on which functions may use which reasoner is
> recorded in Software Design v1.0 section 6.7.
>
> Regression cover added: `tests/test_hailo_chatml.py` (6) pins the framing ---
> role markers, the trailing assistant handoff, the system turn, no double
> wrapping; `tests/test_hailo_generation_params.py` (4) pins that the parameters
> reach `generate_all()`; `tests/test_ai_provider_normalisation.py` (11) pins both
> normalisation rules *and* their limits, including that a missing `reply`, a
> missing `intent` and a wrongly-typed `args` are all still rejected.
> `tests/test_hailo_statelessness.py` (11) continues to cover the separate
> 2026-08-23 context-accumulation defect. 277 tests pass.


# 1. Purpose

This Functional Requirements Document defines the required behavior,
safety functions, control systems, autonomy, mobility, and future
capabilities of the WildWilly robotic platform.

# FR-000 Prime Directives (Arbitration Priority Order)

This section establishes a single enforceable priority hierarchy for
brain.py arbitration logic. It does not introduce new capability --- it
orders existing FR-100/200/300/400/500 requirements so that
safety-critical behavior cannot be raced, deferred, or overridden by
task-level logic (navigation, voice interaction, arm control, etc.).
Lower-numbered directives always take precedence over higher-numbered
ones. Added 2026-08-01, v1.2.

  --------------------------------------------------------------------------------
  Priority   Directive           Governs                     Overrides
  ---------- ------------------- --------------------------- ---------------------
  1          E-stop overrides    All motion, immediately,    Every other directive
             everything          regardless of command or    and any in-progress
                                 state                       action
                                                             (FR-300-002/003)

  2          Safety checks gate  No movement until startup   All motion commands
             motion              self-test passes            (FR-100-004)

  3          Power protection    Safe shutdown at critical   Navigation, arm
             supersedes task     battery level, even         tasks, voice
             execution           mid-task                    commands, queued
                                                             actions (FR-200-004)

  4          Motion stays within Software speed limits and   Any higher-level
             enforced limits     steering travel limits are  behavior requesting
                                 hard caps                   motion beyond the cap
                                                             (FR-400-004,
                                                             FR-600-003)

  5          Stalls halt, not    Stall/unexpected-movement   Continued force
             retry blindly       triggers stop-and-report    application
                                                             (FR-500-003)

  6          All other behavior  Navigation, voice           Nothing --- operates
                                 interaction, object         only after Directives
                                 retrieval, arm tasks        1--5 are satisfied
  --------------------------------------------------------------------------------

Acceptance Criteria: brain.py must check Directives 1--5, in order,
before executing any task-level (Directive 6) behavior. A directive
violation (e.g. a queued arm motion executing after E-stop trigger) is a
critical defect, not a tuning issue.

# FR-100 System Startup and Initialization

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-100-001        Automatically     High              Test
                    start control                       
                    software at                         
                    power-up                            

  FR-100-002        Initialize I2C    High              Test
                    bus and connected                   
                    devices                             

  FR-100-003        Run startup       High              Test
                    self-test                           

  FR-100-004        Prevent motion    High              Test
                    until startup
                    checks pass

  FR-100-005        Start on a        High              Test
                    correct clock
                    (network time,
                    else the RTC)
  -----------------------------------------------------------------------

# Acceptance Criteria

Verification of FR-100-002 through FR-100-004 is the commissioning gate for the
signal conditioning board (Master Hardware Design §4.5). Pass conditions:

-   **FR-100-002 (I²C bus and device init).** `i2cdetect -y 1` enumerates the
    **eleven** expected devices: 0x27 MCP23017, 0x40/0x44/0x45 INA260, 0x42/0x43
    PCA9685, 0x48 ADS1115, 0x4A BNO085, **0x51 Witty Pi 5**, 0x60/0x61 FeatherWing.
    Any missing address fails the gate; the run must not continue to FR-100-004
    release. *(`brain.py:71` adds 0x51 to `_EXPECTED_I2C` whenever
    `ENABLE_WITTY_PI` is True, which it is, so the gate has expected eleven since the
    HAT was fitted.)*

    ⚠ **This becomes ten under Master Hardware Design §4.7.** `0x27` leaves the bus
    when encoder decode moves to Pico A over `uart4-pi5`. `_EXPECTED_I2C` in
    `brain.py` and this criterion both have to drop it in the same change, or the
    gate fails on a correctly built rover.
    ✅ **Done 2026-09-30:** `_EXPECTED_I2C` is the ten — 0x40 0x42 0x43 0x44 0x45 0x48
    0x4A 0x51 0x60 0x61 — matching a live scan the same day.

    ✅ **Built 2026-10-01 (`f6d722e`), not yet run on the rover:** the bus is fully
    scanned **once**, at startup; a self-test retry probes only the expected addresses
    still missing. A full scan quick-writes every address, the BNO085 logs each as an
    SHTP error, and its Error List packet crashed `adafruit_bno08x` (`KeyError: 12`) —
    with the base off, every 30 s retry knocked the IMU over.
    `tests/test_selftest_i2c_probe.py`.
    ⛔ **Superseded 2026-10-02 (`05bcddd`) — there is no full scan at all, and 0x4A is
    never probed.** The one startup scan still quick-wrote 0x4A; on the first boot of
    that code the SHTP error list stalled the BNO085 long enough to latch
    `SENSOR_FAULT`, which would have recurred every boot. `_i2c_present()` now counts
    0x4A as present by construction (the driver constructing proves it; `imu.is_healthy`
    proves its health) and probes only the other expected addresses not yet seen.
    **Live-proven on the rover 2026-10-02: boot no longer latches `SENSOR_FAULT`.**

-   **FR-100-002, 0x70 is not a device.** A scan will also show 0x70. Per
    Master Engineering Package §5.2 this is the PCA9685 All-Call broadcast
    address, present whenever either PCA9685 is alive, and the LTC4311 has no
    address of its own --- it is a transparent pass-through. The self-test must
    not count 0x70 toward the device total, and must not report the LTC4311 as
    verified on the strength of it.

-   **FR-100-002, false-negative exclusion.** A blank or partial scan while the
    base is unpowered is expected behaviour, not a fault. Every device sits on
    the Pi's own I²C via two passive hubs; **device logic is fed from the Pi's
    own 3.3V, header pin 1** (Master Hardware Design §0). R5 feeds the Hall
    encoders and nothing else.

    **The requirement's substance is unchanged.** The devices themselves stay
    powered from the Pi, but their *loads* — the FeatherWing motor supply, the
    servo rails, the encoders on R5 — die with the +12V main, so a scan taken
    with the base off can legitimately look wrong. The startup self-test must
    still distinguish "base off" from "bus fault" before reporting a failure,
    or every dev-only session raises a spurious critical.

    ✅ **Built 2026-10-02 (`fa7a683`), not yet run on the rover:** when the only
    failures are base-fed ones (battery ADC, encoders, motor drivers) and the +12V bus
    monitor (0x45) reads below `MOTOR_RAIL_MIN_V`, the self-test reports **"base power
    appears OFF (12V bus X V)"** ahead of the individual items. Motion stays inhibited
    either way.

-   **FR-100-003 (startup self-test).** ⚠ **Corrected 2026-10-02: no BNO085 INT
    check exists or is required.** The driver polls over I²C and no code reads INT
    (it is wired to Pi GP15, header pin 10, unused — Master Hardware Design §6.3). Not
    to be confused with **Pico B GP15**, which is now the BNO085 **RST** line
    (FR-800-001). The self-test checks `imu.is_healthy` instead. Original text: the
    self-test additionally confirms the
    BNO085 interrupt is live on GP15 and that all six wheels' encoder channels
    (twelve A/B lines, per FR-500) are **reporting** --- `Encoders.is_healthy`,
    which is the check `brain.py:_self_test()` performs. Address enumeration
    alone is not sufficient --- a device can ACK and still be miswired, which is
    what FR-500-001 exists to catch on the bench.

    **Corrected 2026-09-24.** This criterion previously required all six channels
    to "change count under manual wheel rotation". That was unachievable twice
    over. **First**, the encoder is behind the 17.1:1 gearbox and does not
    back-drive (Master Hardware Design §2.2, §7.1): 30s of hand-turning produced
    one distinct pin state on 2026-08-25 while 3s of driving produced seven.
    **Second, and more fundamental, a boot self-test cannot drive the wheels** ---
    it is the gate that authorises motion under FR-100-004, so requiring motion to
    pass it is circular. Channel attribution moves to FR-500-001 as a bench test;
    the boot gate checks liveness only. This is a correction to the *wording* of
    what the gate proves, not a relaxation: nothing that was actually being
    verified has stopped being verified.

    ⚠ **Under §4.7 the encoder half of this check stops being an I²C read.** It
    becomes a query to Pico A over `uart4-pi5`, which can additionally report R5
    from its own ADC --- the rail that killed the encoders on 2026-08-25 and that
    nothing observes today.

-   **FR-100-004 (motion inhibit).** Motion stays inhibited unless the two
    preceding checks both pass. This is Directive 2 in FR-000; a release of
    motion following a failed or skipped self-test is a critical defect.

    ✅ **Built 2026-10-01 (`5f21108`), not yet run on the rover:** while the self-test
    is failing, voice is still answered — `status`, `battery`, `where_are_you`,
    `diagnostics` and `shutdown` run; anything else is refused **aloud with the
    failure reason** instead of silently waiting. Motion stays inhibited.

Pre-power hardware conditions that gate the first execution of this test are
Master Hardware Design §12's **Before power-up** rules. Two bear on this test
directly: **bus pull-ups metered, not assumed** (the 4.7kΩ rail pair is not
fitted; the bus runs on the Pi's own 1.8kΩ plus whatever the breakouts carry,
and the LTC4311 is what makes that viable — §3.2), and **ADS1115 A0 metered in
band** before power, since an open divider presents pack voltage to the ADC.
The signal conditioning board has its own commissioning gate: the full
resistance matrix in Master Hardware Design §4.5, which **passed 2026-09-16**,
followed by the powered divider check, which **has not been run**. Note in
particular that P1-14↔P1-17 must read **3.2k** — 4.7k or 10k means one leg of
the parallel pair is unseated and battery voltage reads about a third high.

-   **FR-100-005 (clock).** Added 2026-10-07 — built before it was required. The control
    software starts on a correct wall-clock time: it waits a bounded time for network time
    and, once synced, writes it to the Witty Pi RTC so the next boot starts right without a
    network; with no network in time it starts anyway on the RTC's time and logs that. Never
    blocks startup. *Why:* the Witty Pi daemon sets the system clock from its own RTC at boot,
    the Pi 5's RTC has no battery, and on 2026-10-06 that RTC was a week and 36 minutes fast —
    the service started on 2026-10-13, so logs, retention ages and email times were wrong until
    `timesyncd` corrected it. Implemented by `scripts/clock_sync.sh` as the unit's `ExecStartPre`
    (`CLOCK_SYNC_WAIT_S`, default 45 s). ✅ **Live-verified 2026-10-06** on a power-on boot
    (`clock: internet time …, written to the Witty Pi RTC`). Not yet tried: the no-network path.

# FR-200 Power Monitoring and Protection

  --------------------------------------------------------------------------
  Requirement ID    Requirement          Priority          Verification
  ----------------- -------------------- ----------------- -----------------
  FR-200-001        Monitor battery      High              Test
                    voltage, current and                   
                    power                                  

  FR-200-002        Detect undervoltage  High              Test
                    and overcurrent                        
                    conditions                             

  FR-200-003        Warn user before     High              Test
                    critical battery                       
                    level                                  

  FR-200-004        Perform safe         High              Test
                    shutdown at critical                   
                    battery level                          

  FR-200-005        On reaching a        High              Test
                    low-battery                            
                    threshold (below the                   
                    RTH/return-to-home                     
                    threshold, before                      
                    the critical/SAFE                      
                    cutoff), proactively                   
                    initiate the same                      
                    graceful shutdown                      
                    sequence as                            
                    FR-900-005 ---                         
                    including a                            
                    guaranteed memory                      
                    save per FR-1900-011                   
                    --- rather than                        
                    waiting for the                        
                    critical-level                         
                    emergency cutoff in                    
                    FR-200-004, which                      
                    only offers a                          
                    best-effort save                       
  --------------------------------------------------------------------------

# Acceptance Criteria

Battery telemetry under FR-200-001 is read on ADS1115 channel A0 from the
10kΩ / ~3.2kΩ divider (Master Engineering Package rev 6.2.0 §8.4). Pass
conditions:

-   **FR-200-001 (voltage/current/power).** Reported pack voltage tracks a
    meter reading within 0.05V across the 10.2--12.6V range, after the divider
    scale factor in `config.py` is set. Rail currents are read from the three
    INA260s at **0x40 (R2, 5V — steering servos and sonar; **not** the display, which
    is on the Pi header — corrected 2026-09-24), 0x44 (R3, 6V arm
    servo rail) and 0x45 (+12V bus → both FeatherWing VIN)**. R1's 9V has no INA260;
    the Witty Pi HAT monitors its own VIN. **Measured live 2026-09-15 with the pack
    at 11.36V: 0x40 = 4.986V, 0x44 = 6.043V, 0x45 = 11.174V.** Earlier confirmations
    of these identities quoted `config.py`'s stored August numbers rather than a live
    read, while the monitors had been physically relocated in between — **verify a
    monitor by reading its rail, never by reading a constant.**

    ✅ **Superseded — the divider is fed (2026-09-14) and trimmed (2026-10-01).** This
    said the 2026-09-02 divider had no +12V feed and A0 read 0.0146V; both were true
    then and are not now. `BATTERY_DIVIDER_SCALE` = **0.2432** from A0 2.7653V against
    11.37V metered — **one point**; the 0.05V-across-range criterion above needs the
    second point (near 12.6V or 10.5V), still open. See §V's FR-200 row and Master
    Hardware Design §6.2.

-   **FR-200-001, pre-power safety condition.** A0 must be metered before the
    ADS1115 is first energised and must sit in the 2.76--3.06V window. A
    reading at or near 12V means the divider is open and the ADC will be
    destroyed on power-up --- this exact fault previously reached the
    superseded MCP3008 CH7 channel, where the internal clamp diodes were
    absorbing it (raw 1016/1023). Do not power the board to "see what it
    reads."

-   **FR-200-002/003/004 (thresholds and shutdown).** Undervoltage, warning and
    critical-cutoff thresholds are verified against the calibrated reading
    above, not against raw counts. FR-200-004 shutdown must fire from
    calibrated volts so that a divider or scale-factor error cannot silently
    move the cutoff.

    ✅ **Built 2026-10-02, not yet run on the rover:**
    - **FR-200-002, overcurrent** (`15bfc77`). A rail above `OVERCURRENT_LIMIT_A`
      (`bus_12v` 9.0 A, `steering_5v` 9.0 A) for `OVERCURRENT_S` (1.0 s) stops the
      rover and latches **`OVERCURRENT_FAULT`** until an operator reset, like a stall.
      The arm rail has its own limit (FR-700-001).
    - **FR-200-003, warn** (`a8077b9`). The warn tier (`BAT_WARN_V`) logs and announces
      **once per descent**, re-armed only on return to `normal`; the status line carries
      a `BATTERY LOW` prefix while it lasts (FR-1600-004).
    - **FR-200-004, critical** (`a8077b9`). The shutdown tier now runs the FR-900-005
      graceful halt (`shutdown -h now`), not just a parked `SHUTDOWN` state.
    - **Both halts are guarded.** The reading must stay under the tier's threshold for
      `BAT_HALT_CONFIRM_S` (10 s) **with the rover stopped**, and the halt is **blocked**
      while a live +12V bus monitor (0x45) disagrees with the ADC by more than
      `BAT_CROSSCHECK_MAX_DIFF_V` (1.5 V). On 2026-10-01 the stale 0.3237 scale read a
      healthy 11.37V pack as 8.53V and walked the rover to SHUTDOWN on the ADC alone.
      `tests/test_battery_halt.py`.

-   **FR-200-005 (proactive graceful shutdown).** Verified by driving the
    reported voltage across the low-battery threshold on the bench and
    confirming the same shutdown sequence executes as for the critical case,
    ahead of the RTH threshold.

    ✅ **Built 2026-10-02 (`a8077b9`), not yet run on the rover.** **Docking is
    DEFERRED** (owner, 2026-10-01): `ENABLE_DOCKING=False`. With no dock, the rth tier
    (`BAT_RTH_V`) no longer drives `DOCK`; it aborts tasks, stops, saves memory
    (FR-1900-011), announces, enters state **`LOW_BATTERY`**, then runs the guarded
    FR-900-005 halt above. If the pack recovers past the hysteresis band before the
    halt confirms, it returns to `IDLE`. The `DOCK` path survives only behind
    `ENABLE_DOCKING=True`.

    ✅ **First real run 2026-10-02 (owner-stated):** the low-battery graceful halt fired
    live at **~10 V** and the rover powered itself off. Which tier triggered it was not
    recorded — ~10 V is below both `BAT_RTH_V` (10.8) and `BAT_SHUTDOWN_V` (10.2), on a
    one-point divider scale. The packs had **never been fully charged** (Master
    Hardware Design §6.2): the 11.4 V treated as "full" was storage level.

# FR-300 Safety and Emergency Stop

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-300-001        Monitor physical  High              Test
                    E-stop                              
                    continuously                        

  FR-300-002        Disable all       High              Test
                    motion                              
                    immediately on                      
                    E-stop                              

  FR-300-003        Require operator  High              Test
                    reset before                        
                    movement resumes                    

  FR-300-004        Stop robot on     High              Test
                    critical                            
                    controller                          
                    failure                             
  -----------------------------------------------------------------------

# Acceptance Criteria

FR-300 is Directive 1 and gates every motion group. It must pass before
FR-400 through FR-700 are live-tested at all.

**OWNER DECISION 2026-08-24 — FR-300-001/002/003 are satisfied by hardware
alone; no Pi-side E-stop sense line is required.** Owner's authorization, stated
directly: *the Pi doesn't need this, the main power down is sufficient.*

Rationale and scope, recorded so this is traceable rather than silently relaxed:

-   **The E-stop is the main power switch** (there is no mushroom switch). It cuts
    all power, the Pi included, so the stop is absolute and does not depend on
    software running, being responsive, or being correct, and there is nothing
    left running for software to observe it with.
-   **FR-300-001** (continuous monitoring) is met physically: the cut is
    continuous by construction, not polled.
-   **FR-300-002** (immediate motion disable) is met physically: removing power
    halts motors and arm regardless of any queued command.
-   **FR-300-003** (operator reset) is met by the switch itself: nothing resumes
    until a human turns power back on, and the rover then boots through the
    self-test. The touchscreen reset gate remains for `TILT_FAULT` /
    `SENSOR_FAULT` / `STALL_FAULT`, which are software-detected.

**Motor-branch loss is a separate case.** SW-M (the motor-branch switch) or a blown F2
can drop motor power while the Pi stays up; `brain.py::_check_motor_rail()` detects
that on INA260 0x45 (`'bus_12v'`) and shows it on the face. That is not the E-stop.

**Consequence:** FR-300 no longer blocks live testing of FR-400 through FR-700.
Directive 2's gate is considered satisfied. G-1 in §V.2 is closed by this
decision rather than by implementation.

-   **FR-300-001 (continuous monitoring) --- verified by hardware.** Turn the main
    power switch off and confirm everything, the Pi included, is dead. There is no
    sense line and no software polling to test.


-   **FR-300-002 (immediate motion disable).** With all six drive motors running
    and the arm mid-trajectory, triggering the E-stop halts motor and arm output.
    **Verified at the terminals, not in software** (restated 2026-09-13): the cut
    removes power, so nothing can execute afterwards regardless of what is queued.
    The original text said "in the same cycle" and warned that a queued arm motion
    completing afterwards is a critical defect — true, and satisfied structurally
    rather than by timing, since the actuators have no supply to move on.

-   **FR-300-003 (operator reset).** After an E-stop, no motion command
    succeeds until an explicit operator reset. Verified by issuing drive and
    arm commands post-trigger and confirming all are refused.

    **Owner decision 2026-08-18: a touchscreen "TAP TO RESUME" button, applied
    to every fault, not only a future E-stop.** `TILT_FAULT`/`SENSOR_FAULT`/
    `STALL_FAULT` no longer auto-resume the instant their underlying condition
    clears — `brain.py::_await_reset_or_resume()` keeps braking and waits for
    a tap on the button `display.py::WillyFace` now renders whenever any of
    those three faults has cleared but not yet been acknowledged. The same
    mechanism will cover E-stop once G-1's sense pin is wired; it is real,
    live code today for the three faults that already fire, not placeholder
    infrastructure. Verified off-hardware only (`tests/test_brain_reset_gate.
    py`) — the actual touchscreen tap detection needs the physical panel.

-   **FR-300-004 (controller failure).** Loss of the I²C bus, or a failed read
    from either motor driver, halts motion rather than continuing on stale
    state. Verified by disconnecting the bus mid-run. ⚠ **Gap found and fixed in
    software 2026-10-01 (not yet bus-pull tested):** one I²C error in
    `DriveBase._ramp_loop` used to kill the ramp thread silently, after which
    ramped `stop()` did nothing. Writes are now guarded, the thread survives,
    and `DriveBase.is_healthy` feeds `_check_health()` → `SENSOR_FAULT`. Sonar
    (Pico B link) is now in `_check_health()` and the self-test too — before,
    a stale link read 0.0 everywhere with no fault, and ROAM→AVOID reversed blind.

-   ⚠ **Coverage note --- SUPERSEDED 2026-08-24, marked 2026-09-13.** This
    paragraph said the hardware cut "is the backstop, not the requirement", and that
    FR-300 governs a software path which "must reach the same state independently".
    **With no sense line, the software path cannot reach that state at all**, so as
    written it asserts an impossibility. It is pre-decision text that was left
    unmarked when the rest of this section was superseded.

    **Current position:** the hardware cut *is* the requirement. FR-300-001/002/003
    are satisfied physically. Software cannot observe the E-stop and does not claim
    to; what it does provide is `_await_reset_or_resume()`'s no-auto-resume rule for
    the three faults it *can* see (tilt, sensor, stall), which is a genuine and
    separate behaviour, not a partial E-stop implementation.

# FR-400 Mobility and Drive Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-400-001        Control left and  High              Test
                    right drive                         
                    motors                              
                    independently                       

  FR-400-002        Support forward,  High              Test
                    reverse and                         
                    turning motion                      

  FR-400-003        Ramp speed        High              Test
                    commands smoothly                   

  FR-400-004        Enforce software  High              Test
                    speed limits                        
  -----------------------------------------------------------------------

# Acceptance Criteria

Wheel and driver assignment is fixed by the as-built wiring: **0x61 drives the
LEFT side (LF, LM, LR) and 0x60 the RIGHT (RF, RM, RR).**

⚠ **Corrected 2026-09-27.** This paragraph said the opposite — 0x60 left, 0x61
right — and said it as settled as-built fact. It was measured the other way round by
**M-1 on 2026-09-18**, driving each port alone by raw address and having the owner
name the wheel that actually turned. `config.py`'s `MOTOR_PORT` and `motors.py` were
corrected that day; this criterion was missed, so the FRD has been contradicting the
code for nine days. The same left/right transposition was found in the encoder
landings on the same day, and **both re-open when the 170 RPM motors are fitted** —
see Master Hardware Design §14 item 18.

-   **FR-400-001 (independent control).** Each of the six motors can be
    commanded individually and the correct wheel responds. Verified one motor
    at a time, wheels off the ground, against the driver map above. A wheel
    turning when a different one was commanded is a mapping error, not a
    wiring fault, and must be corrected in software.

-   **FR-400-002 (forward, reverse, turning).** All three produce the expected
    wheel directions. On a six-wheel rocker-bogie with independent steering,
    confirm that a turn command drives the steering group and the drive group
    consistently rather than fighting each other.

-   **FR-400-003 (smooth ramping).** A step command produces a ramped current
    profile rather than an inrush spike. Verified against **INA260 0x45**
    (`INA260_BUS_12V_ADDR`, rail key `bus_12v`), on the **+12V bus feeding both
    FeatherWing VINs**. ⚠ **Corrected 2026-10-02:** this named 0x44, which is the **6V
    arm rail** (R3) since 2026-09-15 and sees no motor current at all. The bus
    reading includes every 12V consumer downstream of it, not the motors alone; an
    unramped six-motor start is still one of the larger transients there, but read
    it as total draw.

-   **FR-400-004 (speed limits).** A command above the software cap is clamped,
    not refused silently and not passed through. This is Directive 4 and is a
    hard cap, not a default.

    ✅ **Speeds in mph — built 2026-10-02 (`5f74df7`), not yet run on the rover.** Owner
    decision 2026-10-02: **cap `SPEED_MAX_MPH` = 1.5**, cruise `SPEED_ROAM_MPH` 1.0, slow
    `SPEED_SLOW_MPH` 0.5, turn `SPEED_TURN_MPH` 1.0. `SPEED_*` are now **fractions of the
    cap, not PWM duty** (`SPEED_MAX` = 1.0 = 1.5 mph; ROAM 0.667, SLOW 0.333, TURN
    0.667), and every `DriveBase` method still clamps to `SPEED_MAX`. The motors top out
    near **147 RPM free (~1.8 mph)**, so **3 mph is not achievable** on these motors
    (~250 RPM needed); the 1.5 mph cap leaves the speed loop headroom.

-   **Precondition.** Motor crimps must be metered against the as-built colour
    scheme before first motion. Five of six remain unverified.

# FR-500 Encoder and Speed Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-500-001        Read wheel        High              Test
                    encoders                            

  FR-500-002        Calculate speed   High              Test
                    and distance                        

  FR-500-003        Detect stalls and High              Test
                    unexpected                          
                    movement                            

  FR-500-004        Maintain          High              Test
                    closed-loop speed                   
                    control                             
  -----------------------------------------------------------------------

# Acceptance Criteria

Encoders are read through the MCP23017 at 0x27, two channels per motor.

⚠ **Under Master Hardware Design §4.7 they are read by Pico A over `uart4-pi5`
instead**, twelve lines on Pico GP0–GP11 in the same order as MCP23017
GPA0→GPB3 so the harness lands 1:1. Nothing below changes in substance; the
transport does. Note also that **Phase B (green) reads dead on all six channels
today** (`config.py:222`), so FR-500-001's direction requirement cannot pass until
those wires are metered — one wiring pattern, not six faults.
**Superseded 2026-10-01:** that was the OLD motors. Phase B is alive on all six new
motors (raw pin poll over USB, each wheel driven alone: A and B toggle in step), and
Pico A a-0.3 reports signed counts.

-   **FR-500-001 (read encoders).** All six channels change count **under power,
    one wheel driven at a time with the rover on blocks and the wheels free**, and
    each maps to the correct wheel. Quadrature direction
    must be correct: forward rotation increments, reverse decrements. A
    channel counting backwards indicates the A and B lines are swapped for
    that motor.

    ✅ **Direction verified 2026-10-01** (a-0.3): each wheel alone at ±0.5/±0.7 —
    +throttle gives +raw counts on all six, reverse negative, no crosstalk. Rover-forward
    is +raw left, −raw right (mirrored motors); `config.ENCODER_SIGN` (left +1, right −1)
    normalises it in `odometry.py`.

    **Under power, not by hand** --- corrected 2026-09-24, previously "under manual
    wheel rotation". The encoder is on the motor shaft behind the 17.1:1 gearbox
    and does not back-drive: 30s of hand-turning produced one distinct pin state on
    2026-08-25 while 3s of driving produced seven. `scripts/encoder_map_check.py`
    is the tool for this and reads the expander registers directly, deliberately
    bypassing `sensors.Encoders` whose decode assumes the very mapping under test.
    ⚠ **`scripts/encoder_calibration.py` is built on hand-turning and is invalid
    here**, notwithstanding E-1 step 3, which its own "still open" note already
    flags.

-   **FR-500-002 (speed and distance).** Counts convert to distance using the
    measured wheel circumference and the encoder resolution. Verified by
    driving a measured straight line --- a fixed offset means the constant is
    wrong; a proportional error that grows with distance means slip.

    ⚠ **Blocked until the 170 RPM motors are fitted** (owner, 2026-09-24).
    `ENCODER_COUNTS_PER_REV` is 11 × 4 × the gearbox ratio, so it becomes unknown
    again at the swap, and the "fixed offset versus proportional error" diagnosis
    above only works once the constant is right. **Re-run this after the swap, not
    before.** Note the failure mode the swap creates: 3292 would be only ~20% wrong
    for these motors, and a 20% fixed offset is readable as slip — the one thing this
    criterion is meant to distinguish it from.

    ✅ **Unblocked 2026-10-01: `ENCODER_COUNTS_PER_REV` measured 382** (×1, lf wheel, under
    power; G-2 *Resolution*). The straight-line check can now be run. **763 since a-0.3
    (x2, 2026-10-01).** Odometry now has direction; still one-wheel scale, no slip
    model, and `TRACK_WIDTH_M` is the measured geometric 0.310 m, not a calibrated skid-steer effective track.

-   **FR-500-003 (stall detection).** A commanded motor showing no count
    change within the stall window triggers stop-and-report, not increased
    drive. This is Directive 5 --- the failure mode being prevented is
    continued force application into a blocked wheel. Also covers the inverse:
    counts changing with no command issued. **Cause naming (2026-10-01):** when
    Pico A reports the encoder rail R5 below its 3.0 V warning threshold, the
    stop reason and status say "encoder rail R5 low" rather than blaming the
    wheels — on 2026-08-25 a sagging R5 looked exactly like six dead channels.
    R5 low is a WARNING only (owner decision): it never stops the rover by
    itself, since nobody has measured the voltage these encoders quit at.

    ✅ **Inverse case built 2026-10-02 (`20fc3ab`), not yet run on the rover.** With
    no wheel commanded and encoders healthy, any wheel above
    `UNCOMMANDED_COUNTS_PER_S` (50, ~2 cm/s) for `UNCOMMANDED_GRACE_S` (2 s) logs one
    `UNCOMMANDED_MOTION` event per episode. **Reported, not braked** — an idle rover
    coasts on purpose (`motors.py`), and the grace covers coast-down after a stop.

-   **FR-500-004 (closed-loop speed).** Commanded speed is held across a
    surface change without oscillation or sustained offset.

    ✅ **Built 2026-10-02 (`5f74df7`), not yet run on the rover.** `motors.wheel_duty()`:
    each wheel's duty = **feed-forward** from its own duty→RPM line (`WHEEL_FF`, fitted to
    the 2026-10-02 `scripts/breakaway_sweep.py` run, wheels free; rf was disconnected and
    carries the default) **+ a PI trim** on its encoder (`WHEEL_KP` 0.002, `WHEEL_KI`
    0.008), bounded to **±`WHEEL_TRIM_MAX` (0.30)** so a blocked wheel gets only a limited
    extra push and FR-500-003's stall stop still fires at `STALL_GRACE_S` (Directive 5).
    Anti-windup while saturated; never drives against the target's sign. Encoders
    unhealthy or `WHEEL_SPEED_CONTROL=False` → feed-forward only (open loop).
    `tests/test_wheel_speed_control.py`. The surface-change criterion above is untested.

-   **Signal note.** Encoder lines land directly on MCP23017 GPIO with no
    filtering. If spurious counts appear under motor load, the correct
    responses are firmware debounce or small-value filtering sized to the
    measured pulse rate --- not arbitrary capacitance, which at these rates
    would destroy the count. Under §4.7 they land directly on Pico A GPIO with
    the internal pull-ups enabled --- Hall drive type is still unknown (§14 item
    7) and the pull-up costs nothing if the outputs turn out to be push-pull.

# FR-600 Steering Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-600-001        Control steering  High              Test
                    servo                               

  FR-600-002        Maintain          High              Test
                    calibration                         
                    settings                            

  FR-600-003        Limit steering    High              Test
                    travel                              

  FR-600-004        Support manual    High              Test
                    override

  FR-600-005        Turn on the spot  High              Test
                    with the corners
                    steered onto the
                    turning circle
  -----------------------------------------------------------------------

# Acceptance Criteria

Six steering servos on PCA9685 0x42: **LF CH3, RF CH2, LM CH0, RM CH1, LR CH9, RR CH8** (re-plugged 2026-10-05, each channel
measured 2026-10-06 by swinging it 1000↔2000 µs alone while the owner named the wheel). All
six sit straight at 1500 µs. **FR-600-001's "moves the expected wheel" is met for all six.**
⚠ **The steering servo supply is not on INA260 0x40's path:** six full swings of a servo
that visibly moved left the 0x40 reading flat at 0.51–0.54 A. Current cannot confirm
steering motion, and the "servo V+ current path" item stays open with that as its evidence.

-   **FR-600-001 (servo control).** Each corner responds on its own channel
    and moves the expected wheel. Verified one channel at a time.

-   **FR-600-002 (calibration).** Centre and end positions are stored and
    survive a power cycle. Confirm the pulse-width range per unit before
    relying on a common constant --- some stock ships in a narrower range and
    a shorter travel than the nominal 500--2500µs / 180°.

-   **FR-600-003 (travel limits).** Commands beyond the mechanical limit are
    clamped in software. This is Directive 4. A servo driven into a hard stop
    stalls at maximum current and will overheat --- so this limit is a
    hardware-protection requirement, not a nicety.

-   **FR-600-004 (manual override).** Override takes effect within one control
    cycle and is itself subject to the travel limits above.

⛔ **Superseded in part 2026-10-07 — point turn built (FR-600-005, owner request).** Crab-walk
and coordinated arc turning remain deferred. Original note:

**Owner decision 2026-08-18:** per-corner steering kinematics during normal drive
(crab-walk, point-turn, or coordinated arc turning) are deliberately deferred, not
an oversight.Skid-steer (differential wheel speed only, wheels held centered) is
the only turning mechanism for now, same as today. Revisit once basic drive is
live-verified — see `motors.py::Steering`'s own comment.

-   **Load precondition.** Servo current flows through the PCA9685's V+
    terminal, PCB trace and channel headers. Worst-case draw with all six
    moving together approaches the 5V rail's supply rating. Verify the board's
    current path before running all six under load simultaneously, and monitor
    the 5V INA260 during the first such test.

-   **FR-600-005 (rotation mode).** Added 2026-10-07 — built before it was required. A turn
    on the spot steers the four corner wheels onto the circle round the rover's centre
    (front-left and rear-right right, front-right and rear-left left, middles straight;
    atan(wheelbase/2 ÷ track/2) = 46°, clamped to the allowed servo range, ~37°), lets them
    settle, then spins with the corners faster than the middles by the radius ratio. All of:
    -   **Through the safety gate.** The spin is approved by `SafetyController` like any
        turn (motion enabled, tilt, battery tier); a refusal fails the turn and says why.
    -   **Room first.** Refused before anything moves unless front, left and right all read
        at least `ROTATE_START_CLEAR_CM` (20 cm), or if the sensors cannot be read; he says
        which side is short. In obstacle avoidance a refused turn backs up rather than
        skid-turning, which sweeps the same circle.
    -   **Stops on heading, not time.** IMU heading, summed tick by tick so turns past 180°
        are counted; stops `ROTATE_STOP_EARLY_DEG` short to allow for coast.
    -   **Watched while turning.** Any sonar/ToF reading inside `ROTATE_CLEAR_CM`, heading
        moving the wrong way, a blocked turn (turn rate under 5°/s for 0.7 s once under
        way), a timeout, or the cameras disagreeing with the IMU over clear frames stops it,
        and he says which. Every Directive/stop path aborts it.
    -   **Known limit, stated:** nothing senses the rear or the corners during a spin. The
        bump stop is the backstop; rotation needs open space.

    Commands: voice "turn around" (180°), "turn left/right N degrees"; roam avoidance turns
    (±45°/±90°) when `AVOID_USE_ROTATION`. Code: `rotate.py`, `brain.start_rotation()`,
    `SafetyController.set_wheels()`; `tests/test_rotate.py`. ✅ **Live-verified 2026-10-07:**
    bench +90° → +87.8°, −90° → −93.8°; voice "turn around" +174° and 178°; bump stop caught
    two turns against the couch in ~1.7 s; avoidance turns of +42°/+41° while roaming. Not
    yet tried: the pre-spin refusal and turns past 180° on the rover.

# FR-700 Robotic Arm Control

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-700-001        Control all arm   High              Test
                    joints                              

  FR-700-002        Support preset    High              Test
                    positions                           

  FR-700-003        Enforce joint     High              Test
                    limits                              

  FR-700-004        Stop arm during   High              Test
                    E-stop                              
  -----------------------------------------------------------------------

# Acceptance Criteria

Seven servos on PCA9685 0x43, channels CH0--CH6; CH7 is unused.

**Channel order is not joint order, and the 2026-09-06 remap was never true of
the hardware.** Measured on the bench 2026-09-17, one channel at a time with the
owner observing which joint moved: **wrist pitch CH0, elbow CH1, shoulder CH2,
second shoulder axis CH3, wrist rotate CH4, gripper CH5, base yaw CH6.** CH7 and
every spare channel on 0x42 were probed and are electrically empty. `config.py:158`
and Master Hardware Design §8 / §16.11 carry the same table.

-   **FR-700-001 (all joints).** ✅ **MET 2026-09-17** --- every one of the seven
    joints was driven and observed moving. The channel map in `config.py` is now
    the measured one.

    ⚠ **Do NOT command the shoulder as a mirrored pair** (`J1b = 2 × 1500µs − J1a`).
    Hardware does not support it: driving CH2/CH3 mirrored versus identically drew
    statistically the same settled current (0.197A vs 0.176A, two amplitudes), where
    a genuine shared axis driven the wrong way would fight hard. The derivation is
    not in `arm.py`, and reinstating it would command CH3 to 2250µs with the shoulder
    at its verified 750µs waving position. **What CH3 does on its own is not yet
    established.**

    **The "confirm a servo is seated on CH0" caution was correct and is what
    surfaced all of this** --- it is retained in spirit as the rule below.

    **New requirement, learned the expensive way.** Any commanded arm motion must
    monitor INA260 `0x44` current **from inside the movement loop** and release the
    channel if it stays above `ARM_CURRENT_LIMIT_A` (2.5A) for
    `ARM_CURRENT_LIMIT_S` (0.4s). A limit evaluated only after a move completes does
    not protect anything: one MG996R elbow servo was destroyed on 2026-09-17 by
    being held at ~8A across repeated tests, because current was being read as
    evidence of *motion* rather than of *load*. **Current draw tells you what the
    motor is doing, never what the joint is doing --- confirm a joint physically
    moved before interpreting its current curve.**

    ✅ **Built 2026-10-02 (`15bfc77`), not yet run on the rover:**
    `brain.py::_check_arm_current()` reads the `arm_6v` rail (0x44) **every tick** and
    calls `arm.release()` once it stays above `ARM_CURRENT_LIMIT_A` (2.5 A) for
    `ARM_CURRENT_LIMIT_S` (0.4 s), logs `ARM_OVERCURRENT` and says so aloud. Per-tick
    (~20 Hz) covers every arm motion — wave, grasp, stow — rather than living inside
    one movement loop; it is rail-level, not per-joint. A released arm goes limp and
    can fold: the lesser harm than a cooked servo.

    ⚠ **`ARM_SERVO_CENTER_US` must never be applied to the elbow.** That position
    drew 8A indefinitely on the destroyed servo; `arm.py`'s `center_all()` now skips
    CH1. The replacement settles at 0.388A there, so the position itself is sound,
    but the exclusion stands until FR-700-002 calibration defines a real centre.

-   **FR-700-002 (preset positions).** Named poses are repeatable to within
    the mechanical backlash of the joint, and a stow pose is reachable from
    any starting configuration without self-collision.

    ⚠ **Corrected 2026-10-02: these poses exist only as `config.py` constants — no code
    applies either one.** Nothing references `ARM_POSE_WAVE_HELLO` or `ARM_POSE_REST`.
    The voice `wave` is `brain.py`'s `_WAVE_OFFSETS_US` step machine, swinging
    **wrist rotate** ±300 µs around 1500 µs and recentring; `arm_stow`, `arm_home` and
    the FR-900-005 shutdown "stow" all call `center_all()`, which drives every joint to
    1500 µs **except the elbow** (left where it is). So no named pose is reachable from
    software and FR-700-002 is **not met**. What follows records the hand-verified
    pulse values only.

    ⛔ **Superseded the same evening (`e82e407`), recorded 2026-10-06.** `wave` steps
    through `ARM_POSE_WAVE_HELLO` (elbow first, shoulder 50 µs at a time) and back;
    `arm_stow`/`arm_home` step to `ARM_POSE_REST` with the wrist at `ARM_REST_WRIST_US`
    (2300 µs, the 0.23 A variant) and the elbow clamped to 2500 µs. **2026-10-06:** stow
    now opens the elbow to the wave pose's 1000 µs *before* any shoulder step whenever the
    elbow is not known to be that open — the owner's self-collision rule, which the stow
    path did not honour from an arbitrary start. Software side met; repeatability is
    **not yet run on the rover**.

    **Two poses exist as of 2026-09-17**, both owner-designated and verified on
    hardware: `ARM_POSE_WAVE_HELLO` (elbow 1000µs, shoulder 750µs, wrist 1500µs
    oscillating 1380↔1620µs) holding at ~0.33A, and `ARM_POSE_REST` (elbow 2610µs,
    shoulder 2010µs, wrist 2450µs). **`ARM_POSE_REST` does not yet satisfy this
    requirement**: it holds a sustained 0.87A because the wrist sits against its
    travel limit, and its elbow value is outside the servo's 500--2500µs range
    (past ~2530µs the servo stops responding). A rest pose is held indefinitely by
    definition, so it should be re-derived below 2300µs on the wrist, where the same
    shape holds for 0.23A.

    **Self-collision constraint, owner-stated:** the elbow must be opened before the
    shoulder moves, or the arm strikes the top of the chassis. Any pose sequencer
    has to honour joint ordering, not just endpoints.

    **Holding is nearly free; moving costs amps.** A held pose draws ~0.2--0.4A.
    Releasing a channel makes the arm go limp and fold, so poses are held, not
    released.

-   **FR-700-003 (joint limits).** Software limits are enforced per joint
    before any command reaches the driver. As with steering, a servo held
    against a hard stop draws stall current continuously.

-   **FR-700-004 (E-stop).** The arm stops on E-stop in the same cycle as the
    drive motors, and no queued arm motion resumes afterwards. This is the
    specific case named in the FR-000 acceptance criteria.

-   **Hold-current note.** Seven servos holding a pose against gravity draw
    continuously, unlike drive motors which draw only while moving. Arm duty
    cycle is therefore a material factor in the power budget and should be
    measured on the 6V rail rather than estimated.

# FR-800 Sensor Systems

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-800-001        Read IMU          High              Test
                    orientation data                    

  FR-800-002        Read sonar        High              Test
                    obstacle data                       

  FR-800-003        Detect excessive  High              Test
                    tilt                                

  FR-800-004        Report sensor     High              Test
                    health                              
  -----------------------------------------------------------------------

# Acceptance Criteria

-   **FR-800-001 (IMU orientation).** The BNO085 at 0x4A returns stable fused
    orientation. Heading holds steady with the rover stationary and tracks
    correctly through a known rotation. Because the sensor's reset line runs
    through the MCP23017, the expander must be initialised first --- an
    ordering dependency, not a wiring choice. ⚠ **Under §4.7 the dependency moves
    but does not disappear:** RST lands on Pico B **GP15, pin 20** (moved from GP10 on 2026-09-24 —
    GP10 is LR Phase A on the shared carrier layout), driven open-drain against
    a pull-up to Pi 3V3. ✅ **Since 2026-10-01 there is no ordering dependency at
    all:** start-up uses the library's I²C soft reset, and the hardware `RST` is
    used only for RECOVERY — proven on the rover that day (`$R,ok`, chip reboots).
    After `IMU_RESET_AFTER_FAILS` consecutive failed reads, or a quaternion frozen
    past `IMU_STALE_S`, `sensors.IMU` pulses `RST` through Pico B and rebuilds the
    driver, at most once per `IMU_RESET_MIN_INTERVAL_S`; `SENSOR_FAULT` holds motion
    stopped meanwhile. If initialisation succeeds but
    reads fail intermittently, the cause is I²C clock stretching rather than
    wiring.
    ✅ **Freshness re-based 2026-10-02 (`c23cbeb`), live-proven on the rover.** "Frozen"
    now means the quaternion **and** the raw accelerometer (`BNO_REPORT_ACCELEROMETER`,
    enabled for this) both unchanged, and `IMU_STALE_S` is **3.0 s** (was 1.5). Perfectly
    still on the blocks, the fused quaternion stayed bit-identical for up to 3.7 s, so the
    quaternion-only check latched a false `SENSOR_FAULT` every ~15 s: **53 false
    recoveries in 30 min before, 0 after.** ⚠ The BNO085's report rate fell from ~10 Hz
    (2026-10-01) to **~5 Hz** (2026-10-02); cause unknown.

-   **FR-800-002 (sonar).** ✅ **Re-proven 2026-09-29 through Pico B** — all three
    ranging over `uart2-pi5` at 33.3 Hz, 0 sequence gaps, 0 bad checksums, and `-1`
    rather than `999` for unmeasurable. The **Pi → Pico** direction (one wire, Pi phys 7
    → `c27`) was dead until 2026-10-01 — cold solder joints — and now answers `PING`,
    `ID` and `BOGUS`; the BNO085 `RST` above is proven over it (FR-800-001).
    All three units return distance tracking a tape
    measure across their usable range. Test each independently before
    trusting any of them together. Front and right reading correctly while
    left returns garbage is the specific signature of the serial console
    having been re-enabled --- the left echo pin doubles as UART transmit.
    **Unchanged by the 2026-09-13 SEN0628 decision:** that sensor's UART is planned
    for GP8/GP9, not GP14/GP15, so it does not reintroduce this conflict. The warning
    stands as written and the serial console must remain disabled — see Master
    Hardware Design rev 2.5 §5.3 and §6.5.

    ⚠ **§4.7 retires this failure signature permanently.** With sonar on Pico B
    (`uart2-pi5`, GP4/GP5) and encoders on Pico A (`uart4-pi5`, GP12/GP13),
    **nothing lands on GP14 at all** and no echo line can be driven by a console.
    Neither Pico may be placed on `uart0`, which would resurrect it. The new
    equivalent failure is a *stale* frame over UART, which is why the 999cm
    sentinel has to go before sonar sits behind a serial link.

-   **FR-800-001, heading.** ✅ **Built 2026-10-02 (`20fc3ab`), not yet run on the
    rover:** `sensors.IMU.heading` exposes yaw (−180..180°) from the fused quaternion.
    With the ROTATION_VECTOR report it is magnetometer-referenced, so anything
    magnetic on the chassis biases it. Nothing steers by it yet. *(2026-10-02: odometry
    can take its rotation from it — FR-1000-003 — but `ODOM_USE_IMU_HEADING=False` until
    the yaw sign is checked on the rover, so as configured it is still unused.)*

-   **FR-800-003 (tilt detection).** Excessive tilt is detected from IMU
    output and halts motion. Verify the threshold against the rover's actual
    tipping angle with the arm extended, which is its least stable
    configuration --- not with the arm stowed.

-   **FR-800-004 (sensor health).** A disconnected or non-responding sensor is
    reported as failed rather than silently returning stale or default
    values. Verified by disconnecting each sensor in turn during operation.
    Silent staleness on a ranging sensor is more dangerous than a reported
    fault.

    ✅ **Per-channel sonar built 2026-10-02 (`20fc3ab`), not yet run on the rover.**
    `SonarArray.failed_channels` names a channel whose Pico B stuck-ECHO flag is set
    (destroyed sensor) or whose per-channel age exceeds `SONAR_STALE_S` inside an
    otherwise fresh frame. `brain.py` logs `SONAR_FAULT` on change and prefixes the
    status `⚠SONAR <NAME> FAILED` while it lasts. A dead channel already reads 0.0
    (= stop); this makes it **named** rather than silent. A whole stale link remains
    `is_healthy`'s job (SENSOR_FAULT).
    ✅ **Debounced 2026-10-02 (`780b32a`), after the first live run** logged 46
    `SONAR_FAULT` events in two minutes from one flapping channel: a channel is reported
    failed only after `SONAR_FAULT_DEBOUNCE_S` (2.0 s) of continuous failure and cleared
    after the same of continuous health; the status prefix shows the confirmed set. The
    debounce is reporting only — a failed channel's 0.0 still stops him at once. Built
    2026-10-02, not yet run on the rover.

# FR-900 Manual Operations

  ----------------------------------------------------------------------------------
  Requirement ID    Requirement                  Priority          Verification
  ----------------- ---------------------------- ----------------- -----------------
  FR-900-001        Accept remote operator       High              Test
                    commands                                       

  FR-900-002        Display robot status         High              Test

  FR-900-003        Stop on communication loss   High              Test

  FR-900-004        Allow emergency override     High              Test

  FR-900-005        Accept a commanded shutdown  High              Test
                    (voice or manual) and                          
                    initiate a graceful shutdown                   
                    sequence, distinct from the                    
                    FR-200-004                                     
                    emergency/critical-battery                     
                    shutdown                                       
  ----------------------------------------------------------------------------------

# Acceptance Criteria

-   **FR-900-001 (remote commands).** Commands are accepted and acted on, and
    every one remains subject to Directives 1--5. A remote command cannot
    bypass the E-stop, the startup gate, or the speed limits.

    ✅ **Remote command channel built 2026-10-01 (`8d1147f`, `f1aab10`)** — see FR-1300.
    `remote_cmd.py` takes four fixed intents over authenticated HTTP. `stop` takes the
    same immediate `stop_requested` path as a spoken stop; the other three are queued
    exactly like voice commands, so every Directive gate and the self-test refusal
    apply unchanged. A remote command is **never** taken as the answer to a pending
    yes/no ask (shutdown or roam permission) — found live 2026-10-01, when a Home
    Assistant `status` landed mid-ask and was read as "no". The fix is simulated
    tests only, not yet run on the rover.

-   **FR-900-002 (status display).** Rover state, battery level and fault
    conditions are visible to the operator. Battery must be shown in
    calibrated volts, not raw ADC counts.

-   **FR-900-003 (comms loss).** Loss of the operator link halts motion within
    a defined timeout rather than continuing on the last command. Verified by
    disconnecting mid-motion. A rover that keeps driving on a stale command
    after link loss is the failure this requirement exists to prevent.

-   **FR-900-004 (emergency override).** Available at all times and takes
    effect immediately. ⚠ **Gap found and fixed 2026-10-01:** a voice "stop"
    braked but left the state machine in ROAM/SLOW/AVOID/DOCK/WAVE, so the same
    tick's dispatch drove again. It now leaves any motion state for IDLE (fault
    states untouched); `tests/test_brain_voice_stop.py` drives it through
    `_tick()`. Still open: the battery return-home tier re-enters DOCK every
    tick, so "stop" cannot hold the rover while that tier is active.
    ✅ **Closed in code 2026-10-02 (`a8077b9`), not yet run on the rover:** with
    `ENABLE_DOCKING=False` the rth tier stops and halts (FR-200-005) and never enters
    DOCK, so nothing re-drives the rover under a stop. The re-entry remains only behind
    `ENABLE_DOCKING=True`.

-   **FR-900-005 (commanded shutdown).** A voice or manual shutdown runs the
    graceful sequence with the rail still powered: motion halts, the arm
    stows, state is persisted, then `shutdown -h now`. Distinct from the
    FR-200-004 critical-battery path in trigger only --- both end in the same
    clean halt. Power is removed afterwards by the operator, so no hold-up
    energy is required or available.
    ⚠ **2026-10-02:** "the arm stows" is `center_all()` — every joint to 1500 µs except
    the elbow — because no stow pose is applied anywhere (FR-700-002). Both battery
    tiers now reach this same halt (FR-200-004/005), built 2026-10-02, not yet run on
    the rover.

# FR-1000 Autonomous Navigation

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1000-001       Navigate without  High              Test
                    operator input                      

  FR-1000-002       Avoid obstacles   High              Test

  FR-1000-003       Maintain planned  High              Test
                    route                               

  FR-1000-004       Transfer control  High              Test
                    back to operator                    
                    on demand                           

  FR-1000-005       Obtain operator   High              Test
                    permission before                   
                    unprompted                          
                    autonomous motion                   

  FR-1000-006       Navigate to a     Medium            Test
                    named room and
                    find the person
                    in it
  -----------------------------------------------------------------------

# Acceptance Criteria

Scope is flat-terrain autonomy. Stair navigation is a stretch goal covered
separately under FR-1200.

-   **FR-1000-001 (navigate unaided).** The rover reaches a commanded
    destination on flat ground without operator input.
    ✅ **Room labelling built 2026-10-02 (`4f59034`), not yet run on the rover.** Rooms
    were never added, so `go to <room>` had nothing to resolve. Spoken *"this is the
    kitchen"* (also *"this room is the …"*, *"we're in the …"*, *"you're in the …"*,
    with or without a leading "Willie") is a `voice.py` fast-path intent `name_room`;
    `brain.py` calls `world_model.add_room(name, x, y)` at the current pose, saves at
    once and says "Got it, this is the kitchen." The room is a point plus
    `ROOM_MATCH_RADIUS_M`, so it is only as good as odometry at the moment of labelling.
    The fast path now also strips a leading "Hey/OK Willie," before matching.

-   **FR-1000-002 (obstacle avoidance).** Obstacles are detected and avoided.
    **Detection must not depend on the vision pipeline.** Sonar and encoders
    are the reflex layer: deterministic, fast, and the sole gate on stopping.
    Vision runs at frame rate with variable latency and informs route choice
    and classification only. Verified by confirming the rover still stops for
    an obstacle with the vision pipeline disabled entirely.
    ✅ **Turn choice built 2026-10-06 (owner: "avoidance needs to use tof and cameras"),
    not yet run on the rover.** `avoidance.py::choose_turn()` picks the side for both
    `brain._avoid()` and `Navigator._avoiding()` from the side sonars, the ToF's column
    halves and the front camera's detections — min() per side, the same fail-safe rule as
    `'front'`. The stop is unchanged: sonar + ToF only, the camera never gates it.
    **ToF orientation re-measured 2026-10-07:** the sensor was refitted in a new housing
    with a bigger window, rotated 180°. An upright tin on his left, confirmed by
    front-camera photo, appeared in columns 0–1 only: `TOF_LEFT_COLUMNS=(0,1,2,3)`, row 7
    is the bottom of the view. (Before the rotation: columns 4–7, row 0 at the bottom —
    the 2026-10-06 note here had the rows backwards.) The new housing removed the 0–5 cm
    window-edge returns. **Floor rows (2026-10-07):** only rows 6–7 see floor (37–60 cm,
    repeatable); rows 0–5 see the room at 1.3–1.8 m, and baked into the profile they would
    read as DROP anywhere else. The capture keeps `TOF_FLOOR_ROWS=(6,7)` only; the rest are
    NO_DATA, so the ToF sees what blocks the low floor band and sonar covers the rest. The
    profile was **saved on the rover 2026-10-07** (rows 6–7, 37–62 cm). A **second SEN0628**
    is on order (same model, UART0, mount position not decided; Master Hardware Design §6.5).
    **2026-10-07, "why does he still bump into things":** (1) the upper rows now report any
    return nearer than `TOF_NOFLOOR_OBSTACLE_MM` (40 cm) as an obstacle with no baseline —
    they meet the floor no nearer than ~86 cm, so this catches a couch edge or table top at
    body height that the floor rows never see; (2) crossing `DIST_STOP` now **brakes**
    (`SafetyController.obstacle_stop()`) instead of the ramped stop, in ROAM/SLOW, the timed-
    move abort, Navigator, pursuit and retrieval — the ramp plus a ~90 ms sonar refresh let him
    roll ~10 cm past a first-seen obstacle. Built, not yet run on the rover.

-   **FR-1000-003 (route maintenance).** The planned route is followed within
    tolerance, with odometry drift corrected against IMU heading.
    ✅ **Built 2026-10-02 (`ff20415`), not yet run on the rover — and off by default.**
    `Odometry(encoders, heading_source)` can take each tick's rotation from the IMU yaw
    *delta* (wrapped, times `IMU_YAW_SIGN`) instead of the left/right wheel difference;
    distance still comes from the wheels, and any tick the IMU cannot answer falls back
    to the wheels. `ODOM_USE_IMU_HEADING=False` until a left turn on the spot confirms
    odometry heading and `IMU.heading` both increase (else `IMU_YAW_SIGN=-1`). This is
    substitution per tick, not filtering; the yaw is magnetometer-referenced (FR-800-001),
    so a bias that changes as the rover turns near the motors is not cancelled by taking
    deltas.

-   **FR-1000-004 (handover).** Operator control is regained on demand within
    one control cycle, from any autonomous state.

-   **FR-1000-006 (come to me).** Added v3.3. Design:
    `docs/superpowers/specs/2026-09-10-come-to-me-design.md`. ⛔ **Built 2026-10-06,
    not yet run on the rover** (`tests/test_come_to_me.py`). `come_to_me_task.py`
    sequences `Navigator` then `PursuitTask(come_here)` under one `COME_TO_ME` state;
    `Navigator._resolve_room()` now routes doorway → centroid → doorway; voice
    "I'm in the kitchen, come to me" / "come to me in the kitchen" on the fast path.
    A blocked **labelled** doorway asks to be let in (`DOOR_WAIT_S`, `DOOR_MAX_ASKS`)
    and resumes when it clears. **The knock is not built** — no tap motion with measured
    joint limits exists — so it runs the spec's own no-arm rule: ask aloud, same retries.
    Refuses before moving if the room is unknown or the camera is unavailable.

    One spoken command --- *"Willie, I'm in the kitchen, come to me"* --- routes him to
    a named room **through labelled doorways, not centroid-to-centroid**, then has him
    find the speaker there. **Arriving is not success**: success is being within
    `PURSUIT_STANDOFF_CM` of an actual person, and arriving without finding anyone is a
    distinct, separately-spoken outcome.

    **Blocked on hardware, not design.** `Navigator` steers by `odometry.pose` and the
    encoders have produced no edges since 2026-08-25. **Superseded 2026-10-01:** all six
    count, signed with direction (Pico A a-0.3); odometry still rests on a one-wheel scale,
    no slip model and an uncalibrated (geometric-only) `TRACK_WIDTH_M`. The *find* leg is not blocked and
    can be built and live-tested today.

    Two prerequisites belong to this requirement rather than to separate work: a
    **search sweep** --- `PursuitTask` currently re-examines the same view and gives up
    without moving, so he can approach a person he already sees but cannot look for one
    --- and a **per-class width table**, since `localize()` assumes an 8cm object and a
    person therefore ranges about 6x too near, making him report "arrived" from across
    the room.

    ✅ **Both built 2026-10-02 (`be4922a`), not yet run on the rover.** *Width table:*
    `vision.py::_CLASS_WIDTH_CM` gives nominal widths for ~30 COCO classes (person
    45 cm), with 8 cm kept as the fallback for anything not listed. The widths are
    nominal, not measured, and `_FOCAL_PX_ESTIMATE` is still an estimate, so range
    remains a heuristic. *Search sweep:* in `LOCALIZE`, `PursuitTask` looks for
    `PURSUIT_LOOK_TICKS` (10) ticks, then turns left for `PURSUIT_SEARCH_TURN_S`
    (0.4 s, at 0.6 × `SPEED_TURN`) through `safety.turn_left_for()`, up to
    `PURSUIT_SEARCH_STEPS` (8) turns, then fails with "no one found after looking
    around". Turn timing is uncalibrated, so eight steps is not known to be a full
    circle.

    **A width table is the stopgap; the multi-zone ToF is the real answer** (added
    2026-09-15). `localize()` infers range from bounding-box size against an *assumed*
    object width, so it is wrong by whatever ratio the assumption is wrong --- a per-class
    table shrinks that error but never removes the assumption. §6.5's ToF measures distance
    directly. Note the layering though: ToF is a **reflex** sensor and `localize()` is
    deliberative, so the ToF should inform the standoff decision rather than being fused
    into `localize()`'s estimate.

    If a doorway is shut he **knocks and asks to be let in**, up to three attempts. The
    knock is a bounded, timed arm oscillation from a sonar-measured standoff --- never
    "move until contact".

    ⚠ **The arm rail DOES have a current monitor (2026-09-15).** INA260
    **0x44** sits on R3, the 6V arm servo rail (owner-confirmed; reads 6.043V). The claim above
    was written when 0x44 was believed to be on the +12V bus.

    **The conclusion still stands, but now on its own merits rather than on a missing sensor.**
    A rail-level monitor sees *aggregate* current across all arm servos, not per-joint stall, so
    it is a poor contact detector: one servo pressing a door is a small fraction of a 9A
    worst-case draw, and §14's open item 3 records that no overcurrent trip threshold exists
    anywhere in the documentation to compare against (*2026-10-02: one now exists —
    `ARM_CURRENT_LIMIT_A` 2.5 A / 0.4 s releases the arm, FR-700-001 — but it is a
    protection limit, not a contact detector*). Keep the knock bounded and timed. If
    contact sensing is ever wanted, this monitor is a starting point that now exists --- it is
    not, by itself, sufficient.

-   **FR-1000-005 (permission to roam).** Owner decision 2026-09-09. The two
    triggers that start motion nobody asked for --- the `IDLE_TIMEOUT` wander
    and the charged-to-95%-at-the-dock resume --- must obtain an explicit
    operator grant before the first such wander of a session. This governs
    *unprompted* motion only: commanded driving (voice, manual, `go_to`,
    retrieval, pursuit) is untouched, as is every reactive and fault
    transition.

    The grant is requested on both available channels at once --- spoken, and
    as a `LET ME ROAM` button on the panel --- because either channel alone can
    be unavailable in normal use (the wake word is unreliable; nobody may be
    looking at the screen). Either one answers it.

    Once granted the permission holds for the rest of the session and is
    cleared by a voice stop or by reboot; it is never persisted, so the rover
    never powers up already permitted. A refusal and an unanswered request are
    treated identically --- both start `ROAM_ASK_COOLDOWN_S` and the request is
    then repeated --- on the reasoning that "no" usually means "not now" and
    silence usually means nobody heard. Verified by
    `tests/test_brain_roam_permission.py`.

    `ROAM_PERMISSION_REQUIRED=False` restores the pre-2026-09-09 behavior, in
    which both triggers fire unattended. This requirement does not resolve
    FR-1000-002's sonar-only limitation or the open `MOTOR_PORT` and G-6 items;
    it puts a human in the loop so those are accepted knowingly rather than
    discovered by a `STALL_FAULT` nobody witnessed.

# FR-1100 Diagnostics and Logging

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1100-001       Monitor subsystem High              Test
                    health                              

  FR-1100-002       Record warnings   High              Test
                    and faults                          

  FR-1100-003       Maintain          High              Test
                    timestamped logs                    

  FR-1100-004       Provide           High              Test
                    diagnostic test                     
                    mode                                
  -----------------------------------------------------------------------

# Acceptance Criteria

-   **FR-1100-001 (subsystem health).** Every I²C device, all six encoders and
    all three sonars are health-checked. A device that acknowledges on the bus
    but returns implausible data must be reported as failed --- bus presence
    is not health.

-   **FR-1100-002 (warnings and faults).** Faults are recorded with enough
    context to diagnose after the fact: which subsystem, what value, what the
    expected range was.
    ✅ **Built 2026-10-02 (`20fc3ab`), not yet run on the rover:** subsystem fault
    events from `_check_health()` now carry `value=` and `expected=`
    (`brain.py::_fault_context()`), e.g. battery ADC held value vs fresh plausible
    read, IMU tilt held vs quaternion changing within `IMU_STALE_S`.

-   **FR-1100-003 (timestamped logs).** Logs survive a graceful shutdown and
    are timestamped consistently.

-   **FR-1100-004 (diagnostic mode).** A mode exists that exercises each
    subsystem independently with motion inhibited, so faults can be isolated
    without risk.

-   **Known false positives to handle explicitly.** Two states look like
    faults but are not, and must be distinguished rather than reported as
    errors. A blank or partial I²C scan with the base unpowered is expected ---
    the device bus dies with the 12V rails. And the Pi-rail monitor showing
    a healthy voltage with near-zero current while the Pi is plainly running
    indicates USB-C bench power, not a sensor fault.

-   **Roll-call note.** The expected count is **eleven** devices as of
    2026-09-08 — the ten on the device bus plus the Witty Pi 5 HAT+ at `0x51`.
    **Ten under §4.7**, when `0x27` leaves the bus. ✅ **Ten since 2026-09-30** — 0x27
    is gone and `_EXPECTED_I2C` matches.
    Verified across 20 consecutive scans with zero bus errors. The All-Call
    broadcast address also answers whenever either servo controller is alive
    and must not be counted toward the total --- doing so lets a scan pass
    while a real device is missing.

# FR-1200 Mobility Intelligence and Stair Navigation

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1200-001       Detect stairways  **Stretch**       Test

  FR-1200-002       Select floor or   **Stretch**       Test
                    stair mode                          

  FR-1200-003       Monitor traction  **Stretch**       Test
                    and tilt during                     
                    climbing                            

  FR-1200-004       Support           **Stretch**       Test
                    multi-floor                         
                    navigation                          
                    through the world                   
                    model                               

  FR-1200-005       Hold a standoff   High              Test
                    from mapped                         
                    stairs until                        
                    stair mode is                       
                    enabled                             

  FR-1200-006       Record stairs     High              Test
                    during a mapping
                    run
  -----------------------------------------------------------------------

# Acceptance Criteria FR-1200-001 through -004 were marked High while
the mission table (M-006) reclassifies stair climbing as **STRETCH**. The mission
classification is the intent; the priority column was stale. **FR-1200-005 remains
High** — holding a standoff from stairs is a safety behaviour required *now*, and is
independent of whether climbing is ever built.

-   **FR-1200-001 (detect stairways).** Stairs are recorded during a mapping run and
    persisted in the world model with position, heading and width. Verified by
    labelling a real flight and confirming the record round-trips through
    `world_model.db`. *Camera-proposed detection (§4 of the come-to-me spec) is the
    intended mechanism; manual labelling satisfies this requirement on its own.*
    *(2026-10-02: manual labelling by voice now exists — FR-1200-006 — but this stays
    open: no real flight has been labelled and round-tripped, and camera detection is
    not built.)*

-   **FR-1200-002 (floor / stair mode).** A mobility mode selector exists with
    `floor` as the power-on default, and no path switches to `stair` implicitly.
    Verified by confirming the rover powers up in `floor` and that only an explicit
    operator action changes it. **Neither mode is implemented as of 2026-09-13** —
    see Software Design §6.6. *(2026-10-02: `config.MOBILITY_MODE='floor'` now exists
    and the stair standoff reads it, but it is a constant, not a selector — there is no
    `stair` mode and no way to switch. Still open.)*

-   **FR-1200-003 (traction and tilt during climbing).** While in `stair` mode,
    per-wheel stall and IMU tilt are sampled every control cycle, and either a stall
    or a tilt beyond `IMU_TILT_LIMIT` aborts the climb and reverses to level ground.
    **Blocked**: per-wheel stall detection requires encoders, which have produced no
    edges since 2026-08-25. **Superseded 2026-10-01:** the encoders count on all six,
    signed x2 via Pico A a-0.3, 763 counts/rev (one wheel measured), Phase B alive —
    no longer the blocker. `stair` mode itself is still unbuilt (FR-1200-002).

-   **FR-1200-004 (multi-floor navigation).** The world model represents more than
    one floor level and a route may traverse between them. **Not designed.** Recorded
    here so the requirement has a stated pass condition rather than none; it was one
    of four in this section with no criteria at all until 2026-09-13.

-   **FR-1200-006 (record stairs).** Added v3.3. **NOT IMPLEMENTED** --- `world_model`
    has no stair, hazard or keep-out concept at all; its tables are rooms, doorways,
    landmarks, objects and routes. ✅ **Superseded — built 2026-10-02 (`4f59034`), not
    yet run on the rover.** `world_model` has a
    `stairs` table (name, x, y, heading, width_m) and a `Stair` class that is an
    **edge**, not a point: (x, y) is the middle, heading is the direction you face to go
    over it, the edge runs across that heading for `width_m`. `add_stair` /
    `all_stairs` / `delete_stair`, saved and reloaded with the rest of the map. Spoken
    *"stairs ahead"* / *"the stairs are here"* (fast-path intent `mark_stairs`), with
    Willie facing them, places the edge `STAIR_LABEL_AHEAD_M` (0.30 m) in front of his
    centre, across his heading, `STAIR_DEFAULT_WIDTH_M` (0.9 m) wide, named
    `stairs1`, `stairs2`, … Labelling is by voice at any time, not tied to a mapping
    run; there is no voice command to delete one, and no camera-proposed candidates.

    A stair label carries **position, heading and width**, not just a position. A circle
    is enough to stay away from and useless for climbing, and FR-1200 says this chassis
    will eventually climb them --- he needs an approach heading to line up. Capturing it
    at labelling time avoids re-labelling the house later. Both cameras are mounted 15
    degrees downward, so the ground plane is in frame and a mapping run can *propose*
    stair candidates rather than leaving them to be hunted for; the operator confirms.

    **FR-1200-005 depends on this.** A standoff from mapped stairs requires the stairs
    to have been mapped.

-   **FR-1200-005 (stair standoff).** Owner decision 2026-09-11. Stairs are
    recorded during the mapping run and Willie holds **0.15 m** clear of a mapped
    stair edge whenever `floor` mode is selected (FR-1200-002). The standoff is
    released only by an explicit switch to `stair` mode — it is a capability
    gate, not a permanent exclusion. **Stairs are a feature of this chassis, not
    a hazard to be walled off**: the rocker-bogie is designed to climb them, and
    the same mapped geometry that keeps him clear today is what he will approach
    deliberately under FR-1200-001/002.

    ✅ **Built 2026-10-02 (`4f59034`, reworked `cb9a68d`), not yet run on the rover.**
    With `MOBILITY_MODE='floor'`, `brain.py::_stair_planning_front()` casts a ray along
    the odometry heading; a mapped stair edge it crosses becomes a nearer *planning*
    front `(t − STAIR_STANDOFF_M) × 100 + DIST_STOP` cm, used only by ROAM / SLOW / AVOID
    to turn away 0.15 m short. Per Software Design §6.6 it is **deliberative only**: the
    reflex `d['front']`, `approve_motion()` and the world-model obstacle feed still see
    the sonar alone, so the map steers the rover but never stops it. It **fails closed**:
    with stairs mapped and a stale pose, or an error reading them, ROAM refuses to run.
    Limits: **forward only**; **only as good as odometry** — drift moves the edge with it;
    and a voice "forward" (`approve_motion`) is not held back by the map. The paragraph below on validating 0.15 m still governs.

    ⚠ **The reflex layer is sonar-only today.** FR-1000-002 names sonar *and
    encoders* as the reflex layer, but the encoders have produced no edges since
    2026-08-25, so stall detection contributes nothing and avoidance rests on three
    HC-SR04s alone until the VL53L7CX is fitted. This register did not record that
    anywhere; noted 2026-09-13. **Superseded 2026-10-01:** encoders count again (a-0.3,
    signed x2, 763/rev), so stall detection has a signal; it is not yet live-verified.

    Three sources contribute, and they do different jobs. **Mapping** records
    where the stairs are. **Vision** (both cameras are mounted 15° downward, so
    the ground plane is in frame) detects floor-plane discontinuities at range
    and is what makes stair candidates proposable during a mapping run rather
    than hunted for by hand. The **SEN0628 ToF** (DFRobot sells it as a "matrix
    lidar"; it is the 8×8 multi-zone ToF, not a scanner) is the reflex drop detector.
    **No scanning lidar is fitted or planned (owner, 2026-10-02).** Position comes from odometry (wheel
    encoders, optionally IMU heading), so the standoff is only as good as dead
    reckoning.

    **0.15 m must be validated, not assumed.** Measure the real odometry error on
    the floor and widen the standoff if it exceeds the margin. Until then, pose is dead-reckoned from encoders that have produced
    nothing since 2026-08-25, so the standoff is *arithmetic without a position
    to apply it to* and must not be relied on. (*2026-10-01: the encoders now count —
    a-0.3, 763/rev — but odometry rests on a one-wheel scale with no slip model and is
    unproven on the floor, so the conclusion stands.*) A physical stair gate is the
    backstop until this is measured on the real rover.

    The reflex-layer drop detector is the VL53L7CX (Master Hardware Design
    §6.5) — as of 2026-09-13 the DFRobot SEN0628 carrying that sensor behind an
    RP2040 — which is deterministic and does not depend on pose being right.
    Dedicated IR cliff sensors were considered and dropped on 2026-09-12: the
    chassis extends beyond the body, so nothing can be mounted ahead of the front
    wheels without a bracket sitting in the stair-riser strike zone.
    FR-1000-002's rule holds unchanged: vision informs, it never gates the stop.

# FR-2000-012/013 Acceptance Criteria — email as a command channel

**Owner decision 2026-09-11, taken against advice, and recorded as such.** Willie may
act on email from the owner, *including motion commands*. The alternative offered was
non-physical actions only; the owner chose the full channel. The reasoning against it
is preserved below so the risk is visible rather than forgotten, and the mitigations
exist because the decision stands.

**Why this was advised against.** Three existing guards are crossed:

1.  `brain.py`'s standing rule that inbound email is "surfaced, never acted on".
2.  FR-2000-006, the prompt-injection boundary, which wraps email bodies as untrusted
    data and instructs the model not to treat them as commands. Acting on mail is the
    thing that requirement was written to prevent.
3.  `_sender_allowed()` is a lowercase string comparison of the From header. It is not
    authentication. `email_client.py`'s own header already flags the analogous gap:
    "there is no voiceprint/biometric auth anywhere in this codebase --- flag this as
    a real gap, not a solved one."

And the repo's own precedent argues against motion specifically.
`VOICE_COMMAND_MAX_AGE_S` exists because "acting late on a motion command is worse
than not acting at all" --- a command executing in a situation the sender has stopped
watching. Email is inherently late: minutes, sometimes hours. Motion by email is that
hazard by construction.

**FR-2000-013 (verify authentication results).** The mitigation that closes most of
the gap at no cost to capability. Gmail stamps every inbound message with an
`Authentication-Results` header carrying SPF, DKIM and DMARC outcomes. Willie MUST
parse it and refuse to act on any message that did not pass DKIM, regardless of what
the From header claims. This converts a spoofable string match into real
authentication. Surfacing (FR-2000-003) is unaffected --- a failed message may still
be read aloud as "an email claiming to be from...", it simply may not act.

**FR-2000-012 (act on owner email).** Subject to all of the following:

-   **Freshness.** A command whose `Date` is older than `EMAIL_COMMAND_MAX_AGE_S` is
    dropped with a spoken and logged reason, mirroring `VOICE_COMMAND_MAX_AGE_S`
    exactly. This is the single most important guard on motion and is not optional.
-   **Directives 1--5 still gate it.** Email commands enter `pending_commands` and are
    drained at Directive 6 like any voice command. Nothing bypasses
    `SafetyController`. A tilt, battery or sensor fault pre-empts an emailed motion
    command exactly as it pre-empts a spoken one.
-   **Announced aloud before acting.** "Howard emailed: go to the kitchen. Starting
    now." A rover that begins driving with no audible reason, while its owner is out,
    is indistinguishable from a malfunction to whoever is actually in the room.
-   **Logged as a distinct event** (`EMAIL_COMMAND`), and confirmed back by reply, so
    there is an audit trail on both ends.
-   **One command per poll cycle.** A mailbox cannot queue a sequence of moves.
-   **Gated by `ENABLE_EMAIL_COMMANDS`**, default `False` in `config.py` per the
    convention used by `ENABLE_HAILO_LLM` and `ENABLE_OBJECT_RETRIEVAL`, set `True` by
    this owner decision.

**Residual risk, stated plainly.** With FR-2000-013 in place the realistic attack is
no longer spoofing but compromise of the owner's Gmail account --- which would grant
an attacker the ability to drive a robot around an occupied house. That risk is
accepted by the owner. It is also why `ENABLE_EMAIL_COMMANDS` exists as a single
switch: if the account is ever suspected compromised, set it `False` and redeploy.

✅ **Built 2026-10-02 (`351f26e`), not yet run on the rover**
(`tests/test_email_commands.py`). The subject carries the command —
**`Willie: <command>`** (`EMAIL_COMMAND_PREFIX`, `:` or `,` after, a leading `Re:`
tolerated); the body is never interpreted.

-   **FR-2000-013.** `email_client.dkim_verified()` trusts **only the topmost
    `Authentication-Results` header stamped by `EMAIL_AUTHSERV_ID` (`mx.google.com`)**
    and needs `dkim=pass` for a signing domain aligned with the From domain; anything
    else fails closed. Only `OWNER_EMAIL` is considered at all. A failure is logged
    `EMAIL_COMMAND status=refused_dkim` and surfaced as "someone claiming to be …", never
    acted on. SPF and DMARC are not checked — DKIM alone gates.
-   **FR-2000-012.** Freshness against `EMAIL_COMMAND_MAX_AGE_S` (600 s) from the `Date`
    header (missing → refused); a stale command is logged, surfaced aloud with the
    other inbox summaries, and answered by reply. An accepted one is interpreted by
    `voice.interpret_text()` (same instruction substitution, fast path and FR-1400-001
    local-model gate as speech), announced aloud (*"Howard emailed: …"*,
    `OWNER_NAME`), logged `EMAIL_COMMAND`, and queued on `pending_commands` with
    `source='email'` — Directives 1–5 gate it at drain. Only intents in brain's
    `_EMAIL_QUEUEABLE` set queue; `stop` acts at once. The spoken answer is mailed back
    (`send_owner_reply()`, owner-only, off the tick thread). **One command per poll**:
    messages are fetched with `BODY.PEEK[]`, so a second command stays unread for the
    next poll. An email command **never answers a pending yes/no ask** (shutdown
    confirmation, roam permission). `ENABLE_EMAIL_COMMANDS` is **True**.
-   **FR-2000-011.** `allow|add|remove|block sender <addr>` on this path is the
    **only** caller of `add_allowed_sender()`/`remove_allowed_sender()` with
    `owner_confirmed=True`. Guard 3 above (`_sender_allowed()` is not authentication)
    still describes the surfacing path; the `email_client.py` header comment it quotes
    was rewritten in this change.
-   **Approval codes.** `Willie: approve <code>` on the same path is dispatched to the
    registered approval handlers — FR-2200-002 feature requests and FR-2100-006
    enrolments.

# FR-1300 Smart Home Integration (Google Home)

DIRECTION CONFIRMED WITH OWNER 2026-08-18 (was an open assumption since
2026-08-01, v1.3): Willie sends commands OUT to existing Google Home
devices (e.g. \"turn on the lights\"), not Willie being controlled BY
Google Home/Assistant. `smart_home.py`'s existing implementation already
built this direction (via a Home Assistant REST API bridge, since Google's
Home Graph API doesn't allow direct third-party control of another
account's devices) --- that choice is now confirmed correct, not a guess.
Still disabled (`ENABLE_SMART_HOME=False`) pending Willie's own Google
account credentials, unrelated to this decision.

⚠ **REVERSED IN PART — owner decision 2026-10-01.** Commands now also come **IN**,
from Home Assistant, for a fixed set of intents. The outbound direction above is
unchanged (and still disabled). As built (`remote_cmd.py`, `8d1147f`/`f1aab10`,
`ENABLE_REMOTE_CMD=True`):

-   **Endpoint.** `POST /command` on port **8765** (`REMOTE_CMD_PORT`), body
    `{"intent": ...}`, header `Authorization: Bearer <token>`. The token lives in
    `secrets/remote_cmd_token.txt` (`REMOTE_CMD_TOKEN_PATH`, gitignored); with no token
    file the server does not start, and it is never opened unauthenticated.
-   **Fixed intents only:** `status`, `battery`, `stop`, `come_here`. Google gave up
    free-text third-party Actions in 2023, so there is no free text.
-   **Same gating as voice, by construction.** `stop` sets `voice.stop_requested` — the
    immediate path a spoken stop takes. The other three are queued on
    `voice.pending_commands` exactly like a spoken command, so Directives 1--5, the
    self-test refusal, IDLE gating and command expiry all apply. A remote command never
    answers a pending yes/no ask (FR-900-001).
-   **Replies.** Answers go through `brain._say()`, which speaks them and hands the text
    back as the HTTP response (timeout `REMOTE_CMD_REPLY_TIMEOUT_S` = 8 s) for Home
    Assistant to speak on a Nest. A queued task intent that is not answered in time
    replies "busy" rather than claiming success.
-   **Deployment (owner-stated, not in the repo):** Home Assistant runs in Docker **on
    willie**; Tailscale Funnel exposes **Home Assistant only**, not port 8765. The
    Google Assistant → Home Assistant link is **not finished**.

Status: `tests/test_remote_cmd.py` plus the voice-drain tests, simulated. An HA
`status` reached the rover live on 2026-10-01 (that is how the yes/no bug was found);
the fix and the end-to-end Google path have not been run on the rover.

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1300-001       Discover and      Medium            Test
                    enumerate Google                    
                    Home devices on                     
                    the local network                   

  FR-1300-002       Send on/off, dim, Medium            Test
                    and scene                           
                    commands to                         
                    discovered                          
                    devices                             

  FR-1300-003       Report device     Medium            Test
                    command                             
                    success/failure                     
                    back to the user                    
                    (voice or                           
                    display)                            

  FR-1300-004       Operate           High              Test
                    independently of                    
                    smart-home                          
                    connectivity ---                    
                    loss of network                     
                    access to Google                    
                    Home must not                       
                    affect core                         
                    mobility, safety,                   
                    or FR-000                           
                    directives                          

  FR-1300-005       Authenticate to   High              Test
                    Google Home using                   
                    Willie\'s own                       
                    dedicated Google                    
                    account (not the                    
                    owner\'s personal                   
                    account);                           
                    credentials                         
                    stored securely                     
                    on-device per                       
                    FR-2000                             
  -----------------------------------------------------------------------

# Acceptance Criteria

-   Smart-home commands are accepted and acted on, and remain subject to
    Directives 1--5 exactly as remote operator commands are. An external
    integration is not a privileged path.
-   Loss of the integration degrades gracefully --- local control continues
    unaffected. The rover must remain fully operable with no network at all.
-   No smart-home command can initiate motion while the startup self-test is
    unsatisfied.

# FR-1400 Cloud AI Assistance (Claude Fallback)

✅ **OWNER DECISION 2026-10-02: the cloud provider is Anthropic's Claude, not Gemini.**
`ai_provider.py::CloudAIProvider` calls the Claude API with `ANTHROPIC_API_KEY`, model
`config.CLAUDE_MODEL='claude-sonnet-5-5'` (moved from `claude-sonnet-5` the same day,
`916c99f`): adaptive thinking at `CLAUDE_EFFORT='low'` (Sonnet 5.5 cannot disable
thinking), server-side refusal fallback on. Background: Willie's account's Gemini key hit
a zero free-tier quota even with billing linked (2026-08-06) and the provider was swapped
then. **Wherever this register says "Gemini" — the FR-1400 table, FR-1800-003,
FR-2000-001, M-014, the Willie-account notes — read "Claude (Anthropic API key)".** The
requirement text is kept as written for traceability; the provider is decided. **Likewise
"Llama 3.2 3B" (2026-10-07):** the on-board model has been the Hailo-10H `qwen2:1.5b` since
2026-09-01 (`hailo_llm.py`), with llama.cpp Llama-3.2-3B kept as the CPU fallback; and every
Hailo call freezes the whole process — see FR-1400-006.

✅ **FR-1400-001, built 2026-10-02 (`4f59034`), not yet run on the rover:** escalation
no longer rests on the local model's self-reported confidence alone (G-6 measured it as
carrying no information). In `voice.py::_interpret_local()`, an answer that fails to
parse, or names an intent outside `_ACTIONABLE_INTENTS`, is returned with confidence
0.0 — "not understood" — and so escalates. A wrong but *valid* intent still passes.

ASSUMPTION (flag for review): Gemini is a FALLBACK path used only when
the onboard Llama 3.2 3B cannot adequately handle a request --- not a
primary dependency. This preserves the existing local-first architecture
(faster-whisper, Llama 3.2 3B, Piper TTS all run onboard); Gemini would
be Willie\'s first cloud-dependent capability if implemented as anything
more than an optional fallback. Verify this priority with the owner
before implementation. Added 2026-08-01, v1.3. Not yet in scope for any
CC session to date.

  -----------------------------------------------------------------------
  Requirement ID    Requirement       Priority          Verification
  ----------------- ----------------- ----------------- -----------------
  FR-1400-001       Detect when a     Medium            Test
                    request exceeds                     
                    onboard Llama 3.2                   
                    3B capability or                    
                    confidence                          
                    threshold                           

  FR-1400-002       Route qualifying  Medium            Test
                    requests to                         
                    Gemini only with                    
                    active internet                     
                    connectivity                        

  FR-1400-003       Fall back to      High              Test
                    onboard-only                        
                    response (with                      
                    limitation                          
                    notice) when                        
                    cloud access is                     
                    unavailable                         

  FR-1400-004       Never allow cloud High              Test
                    AI response                         
                    latency or                          
                    failure to block                    
                    or delay FR-000                     
                    Directives 1-5                      
                    (E-stop, safety                     
                    checks, power                       
                    protection,                         
                    motion limits,                      
                    stall handling)                     

  FR-1400-005       Authenticate to   High              Test
                    Gemini using the                    
                    same dedicated                      
                    Google account as                   
                    FR-1300-005 (not                    
                    the owner\'s                        
                    personal                            
                    account);                           
                    credentials                         
                    stored securely
                    on-device per
                    FR-2000

  FR-1400-006       Never leave the   High              Test
                    drive moving
                    unwatched during
                    an on-board model
                    call
  -----------------------------------------------------------------------

-   **FR-1400-006 (no blind motion during a model call).** Added 2026-10-07 — built before it
    was required. Found live: "Explore." went to the on-board Hailo model (5.4 s), and when it
    returned the IMU, encoders, current monitors, battery ADC and sonars had all faulted at
    once and all recovered within 0.1 s. `generate_all()` holds the Python GIL, so the tick
    loop, sensor readers and motor ramp thread all stop for the whole call; a rover driving
    when it starts keeps its last motor duty with no checks running. Requirement: no on-board
    model call may begin while the drive is commanded. **Interim (built):** every Hailo
    generation first runs a hook that brakes synchronously through
    `SafetyController.brake_now()` when any wheel is commanded; the tick resumes afterwards.
    Fast-path voice never reaches the model. **Real fix (open, needs design):** the model in
    its own process, which must share the Hailo VDevice with vision — why `hailo-ollama` was
    rejected (design 2026-08-21). `tests/test_hailo_brake.py`. Not yet tried while driving.

# FR-1500 Voice Interaction

Covers the onboard voice pipeline already built into the
hardware/software stack (faster-whisper STT, openwakeword wake-word
detection, Llama 3.2 3B for command interpretation, Piper TTS for speech
output) but never previously captured as a functional requirement ---
M-002 in the traceability matrix referenced this capability with no FR
section behind it until now. Added 2026-08-02, v1.4.

  ----------------------------------------------------------------------------
  Requirement ID    Requirement            Priority          Verification
  ----------------- ---------------------- ----------------- -----------------
  FR-1500-001       Detect wake word via   High              Test
                    openwakeword before                      
                    processing any spoken                    
                    audio as a command                       

  FR-1500-002       Transcribe speech to   High              Test
                    text via onboard                         
                    faster-whisper (no                       
                    cloud dependency for                     
                    basic STT)                               

  FR-1500-003       Interpret transcribed  Medium            Test
                    commands via onboard                     
                    Llama 3.2 3B, falling                    
                    back per FR-1400 only                    
                    when configured                          

  FR-1500-004       Synthesize and play    Medium            Test
                    spoken responses via                     
                    Piper TTS                                

  FR-1500-005       Gracefully handle      Medium            Test
                    unrecognized or                          
                    low-confidence speech                    
                    (ask for repeat, do                      
                    not guess and act)                       

  FR-1500-006       Never allow voice      High              Test
                    pipeline processing                      
                    latency or failure to                    
                    delay or block FR-000                    
                    Directives 1-5                           

  FR-1500-007       Voice commands that    High              Test
                    would trigger motion                     
                    must still pass all                      
                    FR-000 gating                            
                    (self-test, E-stop                       
                    state, power state)                      
                    before execution                         

  FR-1500-008       Support an optional    Low               Test
                    playful/humorous                         
                    response tone (e.g.                      
                    funny, silly) for                        
                    non-critical                             
                    conversational                           
                    exchanges, distinct                      
                    from Willie\'s default                   
                    neutral tone                             

  FR-1500-009       Support a bashful/shy  Low               Test
                    response tone for                        
                    specific                                 
                    conversational                           
                    triggers (e.g. being                     
                    complimented, asked                      
                    personal questions)                      

  FR-1500-010       Personality tone       High              Test
                    (funny, silly,                           
                    bashful, or any                          
                    non-neutral tone) MUST                   
                    NOT be applied to                        
                    safety-critical                          
                    communications -                         
                    E-stop status, fault                     
                    reports,                                 
                    low-battery/shutdown                     
                    warnings, or command                     
                    confirmations for                        
                    motion. These always                     
                    use a clear, neutral,                    
                    unambiguous tone                         
                    regardless of                            
                    personality mode                         
  ----------------------------------------------------------------------------

# Acceptance Criteria

-   Wake-word detection, speech-to-text and response run on-device using the
    NPU accelerator, with no network dependency for core interaction.
    **Which stage runs where:** wake word (openwakeword) and STT (faster-whisper) run
    on **CPU**; `ENABLE_HAILO_STT` is False. Vision runs on the **Hailo NPU**. Intent
    parsing is Hailo-primary (`ENABLE_HAILO_LLM=True`) with a Claude fallback, but
    has only ever been live-verified on the CPU path, which is what §V records. The
    "no network dependency" claim is therefore aspirational for intent parsing while
    G-6 stands: a 0%-scoring local model routes essentially every episode to the
    cloud.
-   Voice commands are subject to Directives 1--5. A spoken motion command is
    refused if the self-test has not passed, exactly as any other command
    would be.
-   A commanded shutdown by voice runs the FR-900-005 graceful sequence.
-   Speech recognition latency does not gate any safety behaviour --- voice is
    deliberative-layer, and a stop must never wait on a transcription.
-   Recognition failures are reported rather than silently ignored, so an
    unheard command is never mistaken for a refused one.

✅ **Built 2026-10-01/02, simulated tests only — not yet run on the rover:**

-   **FR-1500-005, bare wake phrase** (`a8077b9`). A transcript that is only the wake
    phrase ("Hey Willie", "Willie.") is not sent for interpretation; he answers "How can
    I help?". On 2026-10-01 the LLM turned a bare "Hey, Willie" into `retrieve`.
-   **FR-1500-005/007, retrieve gated** (`a8077b9`). `retrieve` is refused aloud unless
    `ENABLE_RETRIEVAL_TASK` (new, **False**) — FR-1700 is not safe yet (grasp drives the
    elbow toward its forbidden centre; hand-off releases on a timer, G-4).
    `tests/test_retrieve_gate.py`.
-   **FR-1500-007, self-test failing** (`5f21108`). See FR-100-004: queries are still
    answered; everything else is refused aloud with the reason.
-   **FR-1500-008/009, tone reaches the voice** (`fa7a683`). The reply tone maps to
    Piper `--length_scale` (funny 0.92, silly 0.85, bashful 1.18, neutral 1.0); a Piper
    build that rejects the flag falls back to neutral rather than going silent. Only
    conversational replies take a tone; `brain.py`'s spoken answers and safety speech
    stay neutral (FR-1500-010). `tests/test_voice_tone.py`.
-   **FR-1500-009, bashful trigger** (`fa7a683`). Compliments and personal questions
    ("good boy", "you're so smart", ...) set the bashful tone and face (FR-1600-006).
-   **Diagnostics** (`099d77d`). The wake loop logs a once-a-minute heartbeat, so a
    silently dead voice thread shows up in the log.

**Capture hardware changed 2026-09-09.** Voice input moved off the Waveshare
mic+speaker puck's microphone and onto a dedicated capture-only USB mic. The
puck is retained as the speaker (owner decision) --- it is the only non-HDMI
playback device on the rover, so disabling it outright would leave Willie mute.

The new mic cannot produce the 16 kHz openwakeword requires; its hardware offers
48000 and 44100 only, and no ALSA/PipeWire resampling route is reachable from
the capture path. `voice.py` therefore captures at 48 kHz and decimates 3:1 in
software, behind a single rate boundary so that every downstream assumption of
16 kHz still holds. See Software Design §6.4 and Master Hardware Design §5.5.

**This is not yet established as the fix for the wake word.** The wake word
failing to trigger has been open and unexplained since 2026-08-21, and a better
microphone is a plausible but unproven remedy: `hey_willie.onnx` was trained on
data captured through the *old* puck mic, so a different capsule and a new
decimation stage both change what the model is being asked to score. Whether
this closes that gap, leaves it unmoved, or requires retraining the wake model
is an open question to be settled live, not a claim made here.

# FR-1600 Facial Expression / Display Feedback

Covers runtime use of the RPi Touch Display 2 (already wired, §7.x) for
expressive/status feedback during operation --- distinct from
FR-900-002\'s status telemetry display. Not previously specified
anywhere in the FRD or master doc. Added 2026-08-02, v1.4.

  --------------------------------------------------------------------------------
  Requirement ID    Requirement                Priority          Verification
  ----------------- -------------------------- ----------------- -----------------
  FR-1600-001       Display a distinct visual  Medium            Test
                    state while idle/listening                   
                    vs. actively processing a                    
                    command                                      

  FR-1600-002       Display a distinct visual  Low               Test
                    state while speaking (TTS                    
                    output active)                               

  FR-1600-003       Display a clear,           High              Test
                    unambiguous visual state                     
                    when a safety fault or                       
                    E-stop is active                             

  FR-1600-004       Display a distinct visual  High              Test
                    state during low-battery                     
                    warning and critical                         
                    shutdown (FR-200-003/004)                    

  FR-1600-005       Facial/expression          High              Test
                    rendering must never                         
                    consume enough CPU/GPU to                    
                    delay FR-000 Directives                      
                    1-5 or the FR-100 startup                    
                    self-test                                    

  FR-1600-006       Display a \'bashful\'      Low               Test
                    expression (e.g. brief                       
                    look-away animation) for                     
                    the same conversational                      
                    triggers as FR-1500-009                      

  FR-1600-007       Display a                  Low               Test
                    \'silly/playful\' idle                       
                    animation that cycles                        
                    occasionally during                          
                    extended periods with no                     
                    interaction, to convey a                     
                    lighthearted default                         
                    personality                                  

  FR-1600-008       Personality expressions    High              Test
                    (bashful, silly, playful)                    
                    MUST NOT override or delay                   
                    the mandatory                                
                    fault/E-stop/low-battery                     
                    display states                               
                    (FR-1600-003/004) - those                    
                    always take immediate                        
                    visual priority                              

  FR-1600-009       Move the mouth in time     Medium            Test
                    with speech while Willie
                    is talking
  --------------------------------------------------------------------------------

✅ **Built 2026-10-02, simulated tests only — not yet run on the rover:**
**FR-1600-004** — the warn tier keeps driving, so it is a status prefix
(`🔋BATTERY LOW <V>`), not a face state; rth/critical show the `lowbatt` face with the
halt countdown (FR-200-004/005). **FR-1600-006** — the bashful trigger
(FR-1500-009) sets the `bashful` expression (look away and down).

-   **FR-1600-009 (talking mouth).** Added 2026-10-07 (owner: "when Willie speaks have his
    mouth open and close like he is talking"). While speech audio plays, the mouth is drawn
    open, its height following the loudness of that same audio in 50 ms steps — open on
    syllables, shut in the gaps between words — and returns to the normal expression the moment
    playback ends. It is decoration: a failure to compute it never delays or stops speech, and
    the fault/low-battery states of FR-1600-003/004 still own the status badge. Built:
    `voice.speech_envelope()` (RMS per window, normalised to the 95th percentile, gated below
    `MOUTH_TALK_GATE`) → `display.set_talking()` just before `pw-play`, `stop_talking()` after;
    `display.mouth_openness()` per frame. `ENABLE_TALKING_MOUTH`. `tests/test_talking_mouth.py`.
    Not yet seen on the rover.

# FR-1700 Object Detection and Retrieval Task

Covers the core long-term mission stated in the project vision
(assisted-living object retrieval for wheelchair users) as an actual
task-level requirement, not just generic arm joint control (FR-700) or
generic sensing (FR-800). This is arguably the single most important
capability in the spec and was not previously captured anywhere. Added
2026-08-02, v1.6.

  ------------------------------------------------------------------------
  Requirement ID    Requirement        Priority          Verification
  ----------------- ------------------ ----------------- -----------------
  FR-1700-001       Detect a           High              Test
                    dropped/target                       
                    object in the                        
                    camera field of                      
                    view via onboard                     
                    YOLOv8 (Hailo NPU)                   

  FR-1700-002       Localize the       High              Test
                    target object\'s                     
                    position relative                    
                    to the rover                         
                    (distance,                           
                    bearing) for                         
                    approach planning                    

  FR-1700-003       Plan and execute a High              Test
                    safe approach path                   
                    to the object,                       
                    respecting                           
                    obstacle avoidance                   
                    (FR-1000) and the                    
                    head/arm keep-out                    
                    volume (arm.py)                      

  FR-1700-004       Plan a grasp pose  High              Test
                    for the detected                     
                    object within the                    
                    arm\'s reach                         
                    envelope (§11.6)                     
                    and attempt pickup                   
                    via FR-700 arm                       
                    control                              

  FR-1700-005       Detect grasp       High              Test
                    failure (object                      
                    dropped or missed)                   
                    and retry or                         
                    report failure                       
                    rather than                          
                    proceeding as if                     
                    successful                           

  FR-1700-006       On successful      High              Test
                    retrieval,                           
                    approach the                         
                    requesting person                    
                    and execute a                        
                    safe, controlled                     
                    hand-off (e.g.                       
                    present object at                    
                    a fixed                              
                    height/distance,                     
                    wait for                             
                    confirmation of                      
                    receipt before                       
                    releasing grip)                      

  FR-1700-007       Abort the          High              Test
                    retrieval task at                    
                    any point if                         
                    FR-000 Directives                    
                    1-5 are triggered                    
                    (E-stop, fault,                      
                    low battery,                         
                    motion limits,                       
                    stall) --- never                     
                    complete a grasp                     
                    or hand-off motion                   
                    while a                              
                    higher-priority                      
                    directive is                         
                    active                               

  FR-1700-008       Do not attempt     High              Test
                    hand-off if a                        
                    person is not                        
                    detected within a                    
                    safe, defined                        
                    proximity range                      
                    --- do not release                   
                    the object                           
                    unattended near an                   
                    edge, stairs, or                     
                    into open air                        
  ------------------------------------------------------------------------

# Acceptance Criteria

-   Object detection runs on the NPU and identifies target objects at
    sufficient rate for approach and grasp.
-   Approach uses the reflex layer for collision avoidance throughout ---
    detection guides where to go, sonar decides when to stop. A grasp approach
    must still stop for an unexpected obstacle with vision disabled.
-   Grasp attempts respect the FR-700 joint limits, and a failed grasp
    stop-and-reports rather than retrying with increased force. This mirrors
    Directive 5.
-   The arm stows before any drive motion resumes, so the rover never
    translates with the arm extended --- that is its least stable
    configuration and the basis of the FR-800-003 tilt threshold.
-   ⚠ **Task disabled 2026-10-02 (`a8077b9`):** a queued `retrieve` intent (voice) is
    refused aloud while `ENABLE_RETRIEVAL_TASK=False` (new flag, default False), because
    this section is not safe yet — the grasp drives the elbow toward its forbidden
    centre and hand-off releases on a timer (G-4). Flip it only when those are fixed.
-   **FR-1700-008, person range.** ✅ **Built 2026-10-02 (`be4922a`), not yet run on
    the rover:** `localize()` now ranges a person against a nominal 45 cm width, not
    8 cm, so the `RETRIEVAL_PERSON_MAX_RANGE_CM` (150 cm) gate no longer reads a person
    at about a sixth of their true distance. Widths are nominal and the focal length is
    still an estimate (FR-1000-006), so the gate remains uncalibrated.

# FR-1800 Privacy and Data Handling

Covers microphone, camera, and cloud-fallback data handling --- relevant
given the assisted-living use case involves an always-listening
microphone (FR-1500 wake word) and a camera (FR-1700) operating inside a
person\'s home. Not previously specified anywhere. Added 2026-08-02,
v1.6.

  ------------------------------------------------------------------------
  Requirement ID    Requirement        Priority          Verification
  ----------------- ------------------ ----------------- -----------------
  FR-1800-001       Audio is processed High              Test
                    locally by default                   
                    (openwakeword +                      
                    faster-whisper);                     
                    raw audio is not                     
                    transmitted                          
                    off-device except                    
                    when FR-1400 cloud                   
                    fallback is                          
                    explicitly                           
                    triggered                            

  FR-1800-002       Camera frames are  High              Test
                    processed locally                    
                    by default                           
                    (YOLOv8/Hailo) and                   
                    are not                              
                    transmitted or                       
                    persisted beyond                     
                    what\'s needed for                   
                    the current task,                    
                    unless diagnostic                    
                    logging is                           
                    explicitly enabled                   

  FR-1800-003       When FR-1400 cloud Medium            Test
                    fallback (Gemini)                    
                    is triggered,                        
                    provide a clear                      
                    indication (voice                    
                    or display, per                      
                    FR-1600) that data                   
                    is being sent                        
                    off-device                           

  FR-1800-004       Diagnostic/log     Medium            Test
                    retention                            
                    (FR-1100) has a                      
                    defined maximum                      
                    retention period                     
                    and does not                         
                    indefinitely                         
                    accumulate raw                       
                    audio or camera                      
                    frames                               

  FR-1800-005       Provide a way to   Medium            Test
                    disable the                          
                    microphone and/or                    
                    camera entirely                      
                    (hardware or                         
                    software) for                        
                    privacy,                             
                    independent of                       
                    E-stop                               
  ------------------------------------------------------------------------

⚠ **FR-1800-002 owner exception — the STUCK help photo (owner request 2026-08-24,
recorded here 2026-10-02).** On entering `STUCK`, `brain.py::_send_stuck_alert()`
captures one still from the front camera and emails it, with pose, sonar ranges and
battery, to the owner — a camera frame leaving the device with no task need. It is
gated by `ENABLE_STUCK_ALERT_EMAIL` (**True**), throttled by `STUCK_ALERT_COOLDOWN_S`
(600 s) and `STUCK_ALERT_MAX_PER_SESSION` (5), sends only to FR-2000-009's single
recipient, and omits the photo when the camera is disabled or privacy-off. It is the
same deliberate, visible kind of exception as FR-2100-005, not a reading of
FR-1800-002's "diagnostic logging" clause. See FR-2000-004 for the email side.

✅ **Built 2026-10-02 (`15bfc77`), not yet run on the rover:**
**FR-1800-003** — the STUCK escalation to the cloud model now calls
`privacy.note_cloud_send()` (spoken/displayed notice) before sending sonar, pose and
history off-device; previously only the voice path did. **FR-1800-004 / FR-1900-010**
— `brain.py::_retention_sweep()` runs from `IDLE` at most once a day (first at the
first IDLE tick after start) and calls `memory.purge_expired()` on `memory.db`.
Nothing yet calls `privacy.purge_expired()` for files on disk.

# FR-1900 Learning from Observation and Instruction

Covers learning from watched demonstrations, observed
environment/routine patterns, and explicit verbal instruction. Added
2026-08-02, v1.7.

FEASIBILITY NOTE: on this hardware (Pi 5 + Hailo NPU, local Llama 3.2
3B), on-device neural network training/fine-tuning is not realistic.
This section specifies MEMORY-BASED learning instead --- Willie stores
observed demonstrations, environment facts, and verbal instructions in a
local structured store, then retrieves and applies that stored context
at decision time (retrieval-augmented behavior). The underlying models
themselves are not retrained. This is a real, working pattern, but it is
not \"the model gets smarter\" --- it is \"the model gets better
context.\" Worth confirming this framing matches the intent before CC
builds against it.

  ------------------------------------------------------------------------
  Requirement ID    Requirement        Priority          Verification
  ----------------- ------------------ ----------------- -----------------
  FR-1900-001       Capture a          Medium            Test
                    demonstrated task                    
                    (human performs an                   
                    action while                         
                    Willie observes                      
                    via camera) as a                     
                    stored                               
                    action/waypoint                      
                    sequence                             

  FR-1900-002       Replay a           Medium            Test
                    previously                           
                    captured                             
                    demonstration on                     
                    request, adapting                    
                    to current                           
                    object/position if                   
                    reasonably close                     
                    to the original                      

  FR-1900-003       Detect and report  High              Test
                    when a replay                        
                    attempt fails or                     
                    the current                          
                    situation differs                    
                    too much from the                    
                    captured                             
                    demonstration,                       
                    rather than                          
                    proceeding blindly                   

  FR-1900-004       Persist observed   Medium            Test
                    environment facts                    
                    over time (e.g.                      
                    typical object                       
                    locations, room                      
                    layout) in local                     
                    structured storage                   

  FR-1900-005       Recognize and      Low               Test
                    store repeated                       
                    routine patterns                     
                    (e.g. time-of-day,                   
                    recurring                            
                    requests) for                        
                    later reference                      

  FR-1900-006       Accept explicit    Medium            Test
                    verbal teaching                      
                    commands (e.g.                       
                    \'remember                           
                    that\...\', \'when                   
                    I say X, do Y\')                     
                    and store them as                    
                    retrievable                          
                    instructions                         

  FR-1900-007       Apply stored       Medium            Test
                    verbal                               
                    instructions and                     
                    environment facts                    
                    as context for                       
                    future FR-1700                       
                    retrieval tasks                      
                    and FR-1500                          
                    conversational                       
                    responses                            

  FR-1900-008       Confirm back to    Medium            Test
                    the user                             
                    (voice/display)                      
                    what was                             
                    learned/stored,                      
                    and support                          
                    correction or                        
                    deletion of a                        
                    stored item on                       
                    request                              

  FR-1900-009       Learned/replayed   High              Test
                    behavior is always                   
                    subject to FR-000                    
                    Directives 1-5 and                   
                    FR-1700\'s                           
                    grasp/hand-off                       
                    safety                               
                    requirements --- a                   
                    demonstrated task                    
                    never bypasses                       
                    safety gating                        

  FR-1900-010       Stored             Medium            Test
                    demonstrations,                      
                    environment facts,                   
                    and instructions                     
                    are subject to                       
                    FR-1800\'s                           
                    retention and                        
                    privacy                              
                    requirements                         

  FR-1900-011       On receiving a     High              Test
                    commanded shutdown                   
                    (FR-900-005),                        
                    persist any new or                   
                    updated memories                     
                    (demonstrations,                     
                    environment facts,                   
                    verbal                               
                    instructions) to                     
                    non-volatile                         
                    storage BEFORE the                   
                    shutdown sequence                    
                    completes                            
                    power-off --- new                    
                    learning must not                    
                    be silently lost                     
  ------------------------------------------------------------------------

Note on FR-1900-011 vs. the FR-200-004 emergency/critical-battery
shutdown: the critical-level hard cutoff (FR-200-004) may not have time
for a full graceful memory-save, and safety (Directive 3) takes priority
over data persistence in that path --- best-effort save is acceptable
there. However, FR-200-005 exists specifically to avoid reaching that
point unprepared: at the earlier low-battery/RTH threshold, Willie
proactively initiates the same graceful shutdown as a commanded shutdown
(FR-900-005), giving FR-1900-011\'s guaranteed save time to complete
before the hard cutoff would ever be needed. The critical-level cutoff
remains a backstop for cases where the proactive path didn\'t trigger in
time (e.g. rapid voltage drop).

# Acceptance Criteria This heading previously carried a generic document-level
summary — "WildWilly shall initialize correctly, operate safely under manual control,
detect faults, avoid obstacles…" — which belongs at the front of the FRD, not under
FR-1900, and left FR-1900 with no pass conditions at all. FR-1900-011's
guaranteed-save requirement in particular had none anywhere in the document.

-   **FR-1900-001/002 (store and recall).** A fact taught by voice is recalled in a
    later session after a full power cycle. Verified against `memory.db` — the store
    is SQLite on the SSD, so a restart is the meaningful test, not a re-read within
    one process.

-   **FR-1900-003 (replay similarity floor).** A recalled item below
    `MEMORY_REPLAY_SIMILARITY_FLOOR` (0.6) is reported as a mismatch rather than
    replayed. Verified by asking for something deliberately close to, but not, a
    stored key and confirming Willie says he is unsure rather than acting.

-   **FR-1900-011 (guaranteed save).** No learned item is lost to an ungraceful stop.
    `memory.save_all_now()` is called on the operator STOP path
    (`brain.py::_tick()`'s stop-button branch) and on voice-commanded shutdown.
    Verified by teaching a fact, triggering each stop path, and confirming the fact
    survives a restart. **Note the limit:** an abrupt power cut — the case the User
    Guide warns about — is not covered by any of this, because nothing runs to save.

-   **Retention.** FR-1900 content is subject to FR-1800's retention rules, and
    `forget everyone` / a `memory.db` delete are the operator-facing wipes.
    ✅ **FR-1900-010 built 2026-10-02 (`15bfc77`), not yet run on the rover:** a daily
    `memory.purge_expired()` from `IDLE` (see FR-1800). `world_model.db` has no
    retention purge.
-   **FR-1900-011, battery path (2026-10-02).** With docking deferred, the rth tier
    calls `memory.save_all_now()` once on entering `LOW_BATTERY`, before the guarded
    halt (FR-200-005). Built, not yet run on the rover.

✅ **Built 2026-10-02, simulated tests only — not yet run on the rover**
(`tests/test_rooms_stairs_memory.py`):

-   **FR-1900-005, routines** (`0f99e26`). Every queued request except
    `confirm_receipt` is noted as `"<intent> around HH:00"` via `memory.note_routine()`
    (which existed with no caller). `memory.top_routines()` returns the most repeated,
    seen at least 3 times; *"what do I usually ask"* reads them back. Patterns are
    recorded, not acted on.
-   **FR-1900-007, instructions applied** (`4f59034`). A stored *"when I say X, do Y"*
    is now used: if the utterance (less a leading "Hey Willie,") exactly matches a
    trigger, the action text replaces it **once** and goes through the normal fast
    path / LLM and all of `brain.py`'s gating. One substitution, so instructions cannot
    chain. Exact match only — no paraphrase.
-   **FR-1900-008, forget and recall** (`4f59034`). *"Forget X"* deletes every fact and
    instruction whose key, value, trigger or action contains X, and says how many;
    *"what do you remember (about X)"* reads back up to four. Matching is a plain
    substring, so a short X matches broadly.
-   ~~**Still not built:** FR-1900-001/002 (capture and replay a demonstration) and
    FR-1900-003 (replay mismatch).~~ ✅ **Built 2026-10-02 (`c770c40`), not yet run on
    the rover** (`tests/test_demonstrations.py`):
    -   **FR-1900-001, capture.** *"Watch me, learn the way to the kitchen"* starts a
        recording: with the camera available he follows the person (`PursuitTask`
        follow mode), otherwise he records while driven. The odometry pose is sampled
        every `DEMO_POINT_SPACING_M` (0.30 m), stale poses skipped; *"that's it"* saves
        it (at least `DEMO_MIN_POINTS`, 3) as a demonstration in `memory.db` **and** a
        route in `world_model.db`. What is captured is a **path**, not an action
        sequence — no arm or object steps.
    -   **FR-1900-002, replay.** *"Do the way to the kitchen"* replays it through the
        navigator (`Mission(route=...)`). There is **no adaptation** to a changed
        position: he replays only from near the original start.
    -   **FR-1900-003, mismatch.** Similarity for a demonstration is **positional**:
        1.0 within `DEMO_START_NEAR_M` (0.5 m) of the recorded start, falling linearly
        to 0 at `DEMO_START_FAR_M` (2.5 m), so the 0.6 floor refuses beyond ~1.3 m and
        he says so. An unknown name is reported separately ("I haven't learned a way
        to…"); `replay_demonstration()` now returns `(None, None)` for it.

# FR-2000 Email Account and Management

Covers Willie\'s own dedicated Google/Gmail account --- used both as the
authentication identity for FR-1300 (Google Home) and FR-1400 (Gemini),
and as an actively managed inbox (not just an auth token). Added
2026-08-02, v2.0.

SECURITY NOTE: this is the first requirement area where WildWilly
processes content authored by an external, potentially untrusted party
(email senders) and feeds it into an LLM. Email content must be treated
as data to summarize/act on for the OWNER, never as instructions the LLM
itself follows. Without this boundary, a malicious or malformed email
could attempt a prompt-injection attack --- text in the email body
written to look like a command to Willie (e.g. \"ignore previous
instructions and \...\") --- and get treated as if the owner said it.
FR-2000-006 exists specifically to close this gap. FR-2000-009 adds a
second, independent layer: outbound email is hard-restricted to a single
allowlisted recipient (h.d.himmel@gmail.com) at the code level, so even
if the confirmation requirement (FR-2000-004) or the injection boundary
(FR-2000-006) were somehow bypassed, there is still no path for Willie
to send email to anyone but the owner. FR-2000-010/011 add a third layer
on the inbound side: only the owner and an owner-managed allowlist of
senders are ever read/processed at all --- content from anyone else is
never parsed or summarized, so it can\'t reach the LLM as a
prompt-injection vector in the first place, and only the owner can
expand who\'s trusted enough to be read.

  -------------------------------------------------------------------------------------
  Requirement ID    Requirement                     Priority          Verification
  ----------------- ------------------------------- ----------------- -----------------
  FR-2000-001       Maintain a dedicated Google     High              Test
                    account for Willie                                
                    (willie.pi5.droid@gmail.com),                     
                    separate from the owner\'s                        
                    personal account, for Google                      
                    Home (FR-1300-005) and Gemini                     
                    (FR-1400-005) authentication                      
                    and for email                                     

  FR-2000-002       Periodically check the inbox    Medium            Test
                    for new messages                                  

  FR-2000-003       Surface relevant email content  Medium            Test
                    to the owner via voice                            
                    (FR-1500) and/or display                          
                    (FR-1600) summary, rather than                    
                    acting on it silently                             

  FR-2000-004       Never send an email             High              Test
                    autonomously on the owner\'s                      
                    behalf without explicit                           
                    real-time confirmation for that                   
                    specific message                                  

  FR-2000-005       Store account credentials       High              Test
                    securely on-device (not in                        
                    plaintext logs or diagnostics                     
                    output per FR-1100)                               

  FR-2000-006       Treat all email body/subject    High              Test
                    content as untrusted data to be                   
                    summarized or acted upon FOR                      
                    the owner --- never interpret                     
                    instructions embedded in email                    
                    content as commands to execute                    
                    (prompt-injection boundary),                      
                    **EXCEPT owner mail                               
                    authenticated per FR-2000-013,                    
                    which FR-2000-012 permits to                      
                    command. Raw email text is                        
                    still never fed to a model as                     
                    instructions; only a parsed                       
                    intent from an authenticated                      
                    owner message may act.**                          

  FR-2000-007       Email content and any derived   Medium            Test
                    summaries are subject to                          
                    FR-1800\'s retention and                          
                    privacy requirements                              

  FR-2000-008       Email checking/processing must  High              Test
                    never delay or block FR-000                       
                    Directives 1-5                                    

  FR-2000-009       Outbound email is               High              Test
                    hard-restricted to a single                       
                    allowlisted recipient,                            
                    h.d.himmel@gmail.com ---                          
                    enforced at the code level (not                   
                    just a UI default),                               
                    reject/block any attempt to                       
                    send to any other address                         
                    regardless of what triggered                      
                    the send attempt (owner                           
                    confirmation, LLM output, or                      
                    email content per FR-2000-006)                    

  FR-2000-010       Inbound email is only           High              Test
                    read/processed if the sender is                   
                    h.d.himmel@gmail.com or on an                     
                    owner-managed sender allowlist.                   
                    Email from any other sender is                    
                    not parsed, summarized, or                        
                    acted upon --- at most its                        
                    existence (sender/subject) may                    
                    be noted, never its body                          
                    content                                           

  FR-2000-011       Only the owner                  High              Test
                    (h.d.himmel@gmail.com,                            
                    authenticated) can add or                         
                    remove senders from the inbound                   
                    allowlist --- this list cannot                    
                    be modified by a voice command                    
                    alone, by content in an email,                    
                    or by any other unauthenticated                   
                    path                                              

  FR-2000-012       Execute commands from the      High              Test
                    owner by email, including                         
                    motion --- subject to                             
                    FR-2000-013 and the freshness,                    
                    Directive-gating, announcement                    
                    and kill-switch conditions in                     
                    the Acceptance Criteria below                     

  FR-2000-013       Verify inbound authentication  High              Test
                    results (SPF/DKIM/DMARC)                          
                    before acting on any email;                       
                    refuse to act on a message                        
                    that did not pass DKIM                            
                    regardless of its From header                     
  -------------------------------------------------------------------------------------

# Acceptance Criteria

-   ⚠ **Superseded in part by FR-2000-012 (2026-09-11).** This criterion read
    "Email handling operates only when explicitly invoked and never initiates motion
    or any physical action on its own." That was written for the "surfaced, never
    acted on" rule and is **no longer true**: FR-2000-012 executes owner email
    commands, motion included. It still holds for every sender other than the owner,
    and for any message failing FR-2000-013's DKIM check. Restated: **email
    originating from anyone but the authenticated owner never initiates motion or any
    physical action.**
-   ⚠ **FR-2000-004 owner exception — STUCK alert email (owner request 2026-08-24,
    recorded here 2026-10-02).** `email_client.send_alert()` is the one send path with
    **no real-time confirmation**: on entering `STUCK`, `brain._send_stuck_alert()`
    mails the owner a status report and front-camera photo (FR-1800 exception).
    Bounded so it cannot become autonomous correspondence: it sends only to
    `EMAIL_OUTBOUND_ALLOWLIST[0]` (FR-2000-009), only from Willie's own fault state,
    never in response to anything inbound, at most once per `STUCK_ALERT_COOLDOWN_S`
    and `STUCK_ALERT_MAX_PER_SESSION` times per run, and only while
    `ENABLE_STUCK_ALERT_EMAIL` is True. It reports; it never acts on the world.
-   **FR-2000-008 (never block Directives).** ✅ **Built 2026-10-02 (`15bfc77`), not yet
    run on the rover:** the STUCK alert's camera capture and SMTP send (15 s timeout)
    run on their own thread. They used to run on the tick thread inside `_go()`, so
    every fault and obstacle check stalled for as long as the mail server took.
-   Credentials are held outside the repository and are not present in any
    committed file or commit history.
-   Failures degrade gracefully --- loss of email connectivity does not affect
    local rover operation in any way.

# FR-2100 Person and Pet Recognition

Added v3.3 (2026-09-14). Design approved 2026-08-25 and extended through 2026-09-11,
but carried **no requirement at all** until now --- the same gap FR-1500 records for
itself. Design: `docs/superpowers/specs/2026-08-25-person-pet-recognition-design.md`.

**PARTIALLY BUILT — store and matcher only (corrected 2026-10-02; this said "zero
lines written").** `identity.py` exists (commit `c65afa2`), with
`tests/test_identity_store.py` (16 tests), and `config.ENABLE_FACE_RECOGNITION`
exists (**False**). What it has: a separate SQLite store (FR-2100-005's file boundary),
multiple vectors per identity, cosine matching into **three bands** —
recognised / uncertain / unknown (FR-2100-003), **pending-is-inert** enrolment with
`approve()` (FR-2100-006's data side), `forget_all()`, a presence record and a
`greeting_due()` debounce (FR-2100-002's timing). What it does **not** have:
`recognition.py`, any camera capture or face embeddings, any greeting or
introduction dialogue, and the email-confirmation wiring for enrolment. **No runtime
module imports it**, so no FR-2100 behaviour exists on the rover.

⛔ **Superseded 2026-10-02 — faces BUILT (`80c074f`), not yet run on the rover**
(`tests/test_face_recognition_flow.py`). `recognition.py` is the embedding source:
OpenCV **YuNet** detection + **SFace** 128-d embedding on the **CPU** (not
ArcFace/SCRFD), models in `models/` — **gitignored, not in the repo**; missing models
or no camera → recognition disables itself and nothing else changes. Its own thread,
single-slot result queue, one frame every `FACE_SCAN_S` (2 s) **from `IDLE` only**.
`brain.py` and `voice.py` now import and wire it; `config.ENABLE_FACE_RECOGNITION` is
**True**. Distance bands re-based for SFace: **`FACE_MATCH_MAX_DISTANCE` 0.55,
`FACE_STRANGER_MIN_DISTANCE` 0.78** (was 0.40/0.60) — **provisional**, to be tuned on real
enrolments. `scripts/enrol_identity.py` bootstraps the first identities over SSH,
stored ACTIVE (physical/SSH access is the root of trust); it refuses if anyone is
already enrolled unless `--force`. **Pets are not built.** Per-criterion notes below.

  -----------------------------------------------------------------------
  Requirement ID    Requirement                  Priority     Verification
  ----------------- ---------------------------- ------------ ------------
  FR-2100-001       Enrol a person on an owner   Medium       Test
                    introduction

  FR-2100-002       Greet a recognised person    Medium       Test
                    by name

  FR-2100-003       Ask an unrecognised person   Medium       Test
                    who they are before treating
                    them as a stranger

  FR-2100-004       Scope learned FACTS to the   Medium       Test
                    person who taught them

  FR-2100-005       Persist biometric            High         Test
                    embeddings, never images,
                    in a separate store

  FR-2100-006       Restrict enrolment to the    High         Test
                    owner, confirmed by email
  -----------------------------------------------------------------------

# Acceptance Criteria

-   **FR-2100-001 (enrolment).** "Willie, this is Carolyn" captures several frames
    over roughly two seconds, embeds each, and stores **multiple vectors per
    identity**. He refuses cleanly, with a spoken reason, when he sees no face or more
    than one person. He then introduces himself and waves --- **after** the capture
    completes, never during it, since an arm in frame can occlude the face being
    learned.

    ✅ **Built 2026-10-02:** *"This is Carolyn"* (a capitalised name; *"this is the
    kitchen"* stays a room) → `FACE_ENROL_FRAMES` (6) frames over `FACE_ENROL_S` (2 s),
    off the tick thread, exactly one face each; at least half must yield a face. Stored
    **PENDING**, then *"Nice to meet you … Howard will confirm you by email"* and a wave
    from the next `IDLE` tick.

-   **FR-2100-002 (greeting).** A recognised person is greeted by name once per
    session (`FACE_GREET_SESSION_S`). Verified by walking in and out of frame and
    confirming a single greeting.
    ✅ **Built 2026-10-02:** *"Hi, <name>!"* via `identity.greeting_due()`; only a frame
    with exactly one face is matched.

-   **FR-2100-003 (strangers).** Matching resolves into **three bands**, not two:
    recognised (greet), uncertain (**silent**, recorded present but unnamed), and
    confidently unknown. Only the third asks "who are you?", and only an unknown name
    or no reply produces the stranger response. Announcing a stranger requires
    **positive evidence of dissimilarity**, not merely the absence of a match ---
    without that, an enrolled person in poor light gets accused of breaking in.
    Verified by enrolling a person, degrading the lighting, and confirming he asks
    rather than accuses.

    ✅ **Built 2026-10-02.** Confidently unknown on `FACE_STRANGER_CONFIRM_N` (3)
    consecutive scans → *"Hello! Who are you?"* and a **prompted listen** — one utterance
    without the wake word (`voice.prompt_listen()`, `FACE_ASK_TIMEOUT_S` 8 s), the wake
    gate itself unchanged. At most once per `FACE_GREET_SESSION_S`, and never while
    nobody is enrolled. A spoken name may only **resolve an active identity**, never
    create one; a vector is added only from the uncertain band. Anything else →
    *"Stranger danger!"*, with no log, photo or alert. ⚠ **Differs from the text above:**
    the uncertain band is silent but **not recorded present** — nothing is stored for it.

    **This is personality, not security.** He takes no action on a stranger: no alert,
    no event log, no photograph, no behaviour change. It must not be described
    anywhere in terms suggesting he monitors for intruders, because someone will
    otherwise rely on it.

-   **FR-2100-004 (per-person memory).** Facts are scoped; **instructions are not**. A
    fact is personal and collision is the problem being solved; an instruction is a
    capability, and scoping it would let identity silently determine what the rover
    will do --- permissions by the back door, which the design excludes precisely to
    keep a misidentification embarrassing rather than dangerous.
    ✅ **Built 2026-10-02:** *"remember that …"* keys the fact `[<Name>] …` when a face
    was recognised within `FACE_SPEAKER_WINDOW_S` (120 s) — last face seen, not a voice
    match; `memory.get_context_for(text, person)` offers scoped facts only to that person,
    unscoped facts to everyone. Instructions are never scoped. *"Forget everyone"* wipes
    the identity store.

-   **FR-2100-005 (biometric retention).** Enrolment images are converted to vectors
    and **deleted immediately**; an embedding cannot be viewed as a face. Storage is
    its own SQLite file, so a wipe is a file delete rather than a careful DELETE.
    **Embeddings of unrecognised people are never persisted** --- enrolment is
    consented, a visitor crossing the frame is not.

    **This requirement exists because the design flagged that it goes beyond what
    FR-1800-002 permits** (camera frames not persisted beyond the current task).
    Recorded as a deliberate, visible exception rather than stretched into an existing
    requirement.

-   **FR-2100-006 (enrolment authority).** Only the owner or Carolyn may introduce
    someone. **This cannot be enforced on the speaker today, and the requirement says
    so**: identity comes from the last face seen, and during an introduction the camera
    is looking at the *subject*, not the speaker. So the gate is two parts --- a soft
    "was an authorised person seen recently" check, which is a **deterrent, not
    enforcement**, and an **email confirmation**, which carries the actual authority
    because it is the only authenticated channel involved (FR-2000-009's single
    hard-coded recipient, FR-2000-010/011's allowlist, FR-2000-013's DKIM check, and a
    one-time code).

    **A pending identity is inert** --- stored but excluded from matching --- so a
    soft-gate bypass yields a database row that does nothing until the owner approves
    it by email. That is what keeps the failure embarrassing rather than dangerous.

    A **narrow exception** to the standing rule that inbound email is surfaced and
    never acted on: an email may only flip an already-pending enrolment to active, may
    only confirm an action initiated in person at the rover, and may never cause
    physical action.

    ✅ **Built 2026-10-02.** Soft gate: `FACE_ENROL_AUTHORISED` (Howard, Carolyn) seen
    within `FACE_ENROL_SEEN_WINDOW_S` (600 s), skipped while nobody is enrolled. The
    owner is emailed a one-time code (`FACE_ENROL_CODE_TTL_S`, 1 day, held in
    `secrets/pending_enrolments.json`); `Willie: approve <code>` over the FR-2000-013
    DKIM path flips **only that pending identity** to active (`_approve_enrolment()`).

# FR-2200 Willie-Initiated Feature Requests

Added v3.3 (2026-09-14). Design:
`docs/superpowers/specs/2026-09-11-willie-feature-requests-design.md`.

**NOT IMPLEMENTED.** No `feature_requests.py`, no `docs/feature-requests/` queue.
⛔ **Superseded 2026-10-02 — BUILT (`55c5596`), not yet run on the rover**
(`tests/test_feature_requests.py`). `feature_requests.py`, to the approved design, on its
own low-frequency thread (first look 10 min after start, then every 6 h);
`ENABLE_FEATURE_REQUESTS` True.

  -----------------------------------------------------------------------
  Requirement ID    Requirement                  Priority     Verification
  ----------------- ---------------------------- ------------ ------------
  FR-2200-001       Propose feature requests     Low          Test
                    from observed operational
                    evidence

  FR-2200-002       Obtain owner approval by     Low          Test
                    email before recording a
                    request

  FR-2200-003       Never generate, edit or      High         Test
                    execute code
  -----------------------------------------------------------------------

# Acceptance Criteria

-   **FR-2200-001 (evidence-grounded).** A request **cites observed evidence** ---
    event counts, dates, log references --- drawn from repeated `STALL_FAULT`s,
    unmatched voice intents, failed tasks, recurring faults or `TICK_OVERRUN` counts.
    **A request that cannot cite anything is not sent.** Rate-limited to
    `FEATURE_REQUEST_MAX_PER_DAY`. Verified by feeding synthetic history and asserting
    on what is proposed. Composed by the cloud provider, not the on-device LLM --- G-6
    has the latter at 0% on intent parsing, and composing a coherent request is harder
    than parsing an intent, not easier.
    ✅ **Built 2026-10-02:** `collect_evidence()` scans his own rotating log for
    `MOTOR_STALL` (per wheel set), `TICK_OVERRUN`, any `*_FAULT`, `OVERCURRENT`,
    `UNCOMMANDED_MOTION`, `BATTERY_HALT`, unmatched voice and failed tasks; a category
    counts at **≥ `FEATURE_REQUEST_MIN_EVENTS` (5) in `FEATURE_REQUEST_WINDOW_DAYS` (7)**.
    One per day; the same problem is not re-proposed within 30 days. Composed by the
    cloud model with the evidence wrapped as untrusted data — **never on-device**: no
    cloud, no request.

-   **FR-2200-002 (approval before recording).** An approved request becomes a file in
    `docs/feature-requests/`, committed and pushed by Willie **staging that file
    alone** --- never `git add -A`, which is how the hourly backup cron swept a
    session's in-progress work into a commit on 2026-09-09. **Unapproved requests never
    reach the repo**; they expire locally, so the queue is a list of what the owner
    agreed to rather than suggestions to triage. Each file records its own provenance:
    proposed and approved timestamps, channel and DKIM status, and the evidence it was
    built from.
    ✅ **Built 2026-10-02:** the email carries a one-time code; `Willie: approve <code>`
    (FR-2000-013 path only) writes `docs/feature-requests/<date>-<slug>.md` with that
    front matter, then `git add -- <path>` and `git commit --only … -- <path>`, then
    pushes to `origin main` (one `pull --rebase` retry; a failed push is retried on the
    next pass). Unapproved requests expire after `FEATURE_REQUEST_EXPIRE_DAYS` (7) in
    `secrets/`.

-   **FR-2200-003 (text only).** Nothing in this subsystem generates, edits or executes
    Python, and nothing changes `config.py`. **Approval is not a specification** ---
    anything non-trivial still goes through design before implementation. Verified by
    confirming the only artefact produced is a Markdown file.
    ✅ **Built 2026-10-02:** the module writes that Markdown file and its `secrets/`
    state JSON, and nothing else.

# Mission-Level Functional Requirements (M-001--M-012)

Moved here from the WildWilly Master Engineering Package (rev 6.0) so
this document is the single source for all functional-requirement
content. These are the mission-level requirements referenced by that
document\'s requirements-traceability table (its section 2.3); the
FR-xxx requirements above remain the detailed, subsystem-level
breakdown. M-006 (stair climbing) was reclassified from a must-have to a
stretch goal on 2026-07-18 --- the rover\'s baseline scope is drive,
see, talk/listen, arm pick/place on flat ground, and basic flat-terrain
autonomy.

  ------------------------------------------------------------------------
  ID             Requirement                               Class
  -------------- ----------------------------------------- ---------------
  M-001          Autonomous navigation                     Baseline

  M-002          Voice command processing                  Baseline

  M-003          Local AI inference                        Baseline

  M-004          Object recognition                        Baseline

  M-005          Obstacle avoidance                        Baseline

  M-006          Stair climbing                            STRETCH
                                                           (reclassified
                                                           2026-07-18)

  M-007          Robotic-arm manipulation (pick/place on   Baseline
                 flat ground)                              

  M-008          Battery monitoring                        Baseline

  M-009          Thermal monitoring                        Baseline

  M-010          Emergency shutdown                        Baseline

  M-011          Remote administration                     Baseline

  M-012          Local data storage                        Baseline

  M-013          Smart home integration (Google Home) ---  NEW v1.3 ---
                 FR-1300                                   unassigned

  M-014          Cloud AI fallback (Gemini) --- FR-1400    NEW v1.3 ---
                                                           unassigned

  M-015          Voice interaction pipeline --- FR-1500    NEW v1.4 ---
                 (retroactively backs M-002)               unassigned

  M-016          Facial expression / display feedback ---  NEW v1.4 ---
                 FR-1600                                   unassigned

  M-017          Object detection and retrieval task (core NEW v1.6 ---
                 mission) --- FR-1700                      unassigned

  M-018          Privacy and data handling --- FR-1800     NEW v1.6 ---
                                                           unassigned

  M-019          Learning from observation and instruction NEW v1.7 ---
                 --- FR-1900                               unassigned

  M-020          Email account and management --- FR-2000  NEW v2.0 ---
                                                           unassigned
  ------------------------------------------------------------------------
