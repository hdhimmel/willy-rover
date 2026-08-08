**Willy Functional Requirements Document (FRD)\
Version 1.0**

# 1. Purpose

This Functional Requirements Document defines the required behavior, safety functions, control systems, autonomy, mobility, and future capabilities of the WildWilly robotic platform.

**As-built status pass added 2026-08-08.** This document originally carried no implementation-status column — every requirement below now has a short "Implementation status" note verified directly against the current `/home/hhimmel/rover` code (not carried over from any other document), added the same day as a matching as-built pass on `WildWilly_Master_Engineering_Package_rev6.0.7.md` §§13-14. See `docs/WildWilly_Claude_Fix_Gap_Analysis.md` and `docs/WildWilly_Subsystem_Status.md` for the software-architecture detail behind these notes.

# FR-100 System Startup and Initialization

  --------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                        Priority          Verification
  ----------------- -------------------------------------------------- ----------------- -----------------
  FR-100-001        Automatically start control software at power-up   High              Test

  FR-100-002        Initialize I2C bus and connected devices           High              Test

  FR-100-003        Run startup self-test                              High              Test

  FR-100-004        Prevent motion until startup checks pass           High              Test
  --------------------------------------------------------------------------------------------------------

**Implementation status (2026-08-08): DONE, live-verified.** `willy-rover.service` (systemd, `WantedBy=multi-user.target`) auto-starts `main.py`; `RoverBrain.__init__`/`_self_test()` initializes and probes every I²C device before `INIT→IDLE`; `_motion_enabled` stays `False` (all motion commands rejected) until self-test passes. Live-verified 2026-08-08 when the arm PCA9685 fault cleared and the service reached `IDLE` for the first time since Phase 1.

# Acceptance Criteria

# FR-200 Power Monitoring and Protection

  -------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                       Priority          Verification
  ----------------- ------------------------------------------------- ----------------- -----------------
  FR-200-001        Monitor battery voltage, current and power        High              Test

  FR-200-002        Detect undervoltage and overcurrent conditions    High              Test

  FR-200-003        Warn user before critical battery level           High              Test

  FR-200-004        Perform safe shutdown at critical battery level   High              Test
  -------------------------------------------------------------------------------------------------------

**Implementation status (2026-08-08): PARTIAL.** FR-200-001/003/004 DONE and live-verified: `ADC` (ADS1115 @0x48) reads battery voltage; three `INA260`s log current/power per rail (§8.3); the tier ladder (`config.BAT_WARN/RTH/SAFE/SHUTDOWN_V`) warns then controlled-shuts-down, confirmed live 2026-08-08 (`battery_volts=3.16V` correctly forced `SHUTDOWN`). FR-200-002 is **half-missing**: undervoltage detection works (the ladder above); overcurrent detection does not exist — `CurrentMonitor.is_healthy` is read-recency only, and `sensors.py`'s own comment confirms no numeric overcurrent trip threshold exists anywhere in the documentation to hardcode against. Do not treat overcurrent protection as implemented.

# Acceptance Criteria

# FR-300 Safety and Emergency Stop

  ------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                      Priority          Verification
  ----------------- ------------------------------------------------ ----------------- -----------------
  FR-300-001        Monitor physical E-stop continuously             High              Test

  FR-300-002        Disable all motion immediately on E-stop         High              Test

  FR-300-003        Require operator reset before movement resumes   High              Test

  FR-300-004        Stop robot on critical controller failure        High              Test
  ------------------------------------------------------------------------------------------------------

**Implementation status (2026-08-08): PARTIAL, with a real gap.** FR-300-001 is **not satisfiable in software today** — no GPIO sense pin exists for the physical E-stop, so nothing in `brain.py` can observe it; the latching NC mushroom switch cuts the 12V motion bus directly in hardware (real, but outside software's visibility), which does incidentally satisfy FR-300-002/003 (immediate cut, manual-latch reset) at the hardware layer only. FR-300-004 is partial: a process crash/exit triggers `Restart=on-failure`/`RestartSec=5` (motors de-energize when the process exits) — but there is no configured `WatchdogSec` in the deployed unit, so a *hang* (not a crash) would not be caught by anything. Do not describe the physical E-stop as software-observable, and do not describe the systemd watchdog as configured — it isn't.

# Acceptance Criteria

# FR-400 Mobility and Drive Control

  ---------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                         Priority          Verification
  ----------------- --------------------------------------------------- ----------------- -----------------
  FR-400-001        Control left and right drive motors independently   High              Test

  FR-400-002        Support forward, reverse and turning motion         High              Test

  FR-400-003        Ramp speed commands smoothly                        High              Test

  FR-400-004        Enforce software speed limits                       High              Test
  ---------------------------------------------------------------------------------------------------------

**Implementation status (2026-08-08): DONE.** `motors.py`'s `DriveBase` (Adafruit MotorKit, 2× FeatherWing #2927) controls left/right independently; forward/reverse/turn all implemented; `_ramp_loop()` slew-rate-limits throttle changes (explicitly cited as FR-400-003 in the code's own comment); `safety.py::approve_motion()` clamps every commanded speed to `config.SPEED_MAX` before it reaches the motors — the single authoritative gate, not a per-caller check.

# Acceptance Criteria

# FR-500 Encoder and Speed Control

  ---------------------------------------------------------------------------------------------
  Requirement ID    Requirement                             Priority          Verification
  ----------------- --------------------------------------- ----------------- -----------------
  FR-500-001        Read wheel encoders                     High              Test

  FR-500-002        Calculate speed and distance            High              Test

  FR-500-003        Detect stalls and unexpected movement   High              Test

  FR-500-004        Maintain closed-loop speed control      High              Test
  ---------------------------------------------------------------------------------------------

**Implementation status (2026-08-08): PARTIAL.** FR-500-001/002 DONE: `Encoders` (MCP23017 @0x27 polling) reads quadrature counts; `odometry.py::Odometry.update()` converts them into speed/distance (`Pose.linear_velocity`/`angular_velocity`). FR-500-003 is a **real gap, not just untested**: `Encoders.stalled(wheel, commanded)` exists but is never called anywhere in production code (repo-wide grep, confirmed) — stall detection is dead code today. FR-500-004 is **not implemented**: odometry is a passive, dead-reckoning read logged every tick (`brain.py`) with no motor consequence — nothing feeds it back into drive control; there is no closed-loop speed control anywhere in the codebase. Encoder counts should be treated as best-effort telemetry only (no dedicated interrupt, ~1kHz I²C poll ceiling per `sensors.py`'s own comment, can miss edges at speed) — see the Claude Fix audit's own encoder-risk note.

# Acceptance Criteria

# FR-600 Steering Control

  -------------------------------------------------------------------------------------
  Requirement ID    Requirement                     Priority          Verification
  ----------------- ------------------------------- ----------------- -----------------
  FR-600-001        Control steering servo          High              Test

  FR-600-002        Maintain calibration settings   High              Test

  FR-600-003        Limit steering travel           High              Test

  FR-600-004        Support manual override         High              Test
  -------------------------------------------------------------------------------------

**Implementation status (2026-08-08): PARTIAL.** FR-600-001/002/003 DONE: `Steering` (PCA9685 @0x42) controls all 6 channels; `config.py` holds per-servo pulse-width calibration (narrowest documented range by default, per-unit bench-check needed before widening); travel is limited to the configured pulse-width range. FR-600-004 (manual override) is **not built** — there is no teleop/RC input path anywhere in the codebase (see FR-900 below); the only external control surface is voice commands, which is not the same thing as a manual override during autonomous operation.

# Acceptance Criteria

# FR-700 Robotic Arm Control

  --------------------------------------------------------------------------------
  Requirement ID    Requirement                Priority          Verification
  ----------------- -------------------------- ----------------- -----------------
  FR-700-001        Control all arm joints     High              Test

  FR-700-002        Support preset positions   High              Test

  FR-700-003        Enforce joint limits       High              Test

  FR-700-004        Stop arm during E-stop     High              Test
  --------------------------------------------------------------------------------

**Implementation status (2026-08-08): PARTIAL, with a real gap.** FR-700-001/002 DONE: `arm.py`'s `Arm` (PCA9685 @0x43) controls all joints; `retrieval_task.py` sequences fixed preset positions (`center_all()`, grasp/deliver primitives) — not full inverse kinematics (no per-joint calibration exists yet, an honestly-documented gap in `retrieval_task.py`'s own comments). FR-700-003 (joint limits) is enforced via configured pulse-width ranges, same mechanism as steering. **FR-700-004 is not implemented**: no fault path in `brain.py` (tilt fault, sensor fault, battery shutdown, or the physical E-stop even if it were software-observable) repositions or freezes the arm — only `safety.py::SafetyController.emergency_stop()` brakes the *drive base*; the arm holds whatever PWM position it was last commanded to, unchanged by any safety event.

# Acceptance Criteria

# FR-800 Sensor Systems

  ---------------------------------------------------------------------------------
  Requirement ID    Requirement                 Priority          Verification
  ----------------- --------------------------- ----------------- -----------------
  FR-800-001        Read IMU orientation data   High              Test

  FR-800-002        Read sonar obstacle data    High              Test

  FR-800-003        Detect excessive tilt       High              Test

  FR-800-004        Report sensor health        High              Test
  ---------------------------------------------------------------------------------

**Implementation status (2026-08-08): DONE, live-verified.** `sensors.py::IMU` (BNO085 @0x4A, 100Hz) reports orientation; `SonarArray` (3× HC-SR04) reports obstacle ranges; `TILT_FAULT` FSM state trips at `config.IMU_TILT_LIMIT`; `brain.py::_check_health()` reports IMU/encoder/current/battery-ADC health every tick and escalates a sustained (>1s) fault to `SENSOR_FAULT` + `emergency_stop()`. IMU construction and the RST-pin hardware reset were both live-verified 2026-08-08 (§8.2 of the master doc).

# Acceptance Criteria

# FR-900 Manual Operations

  ---------------------------------------------------------------------------------------
  Requirement ID    Requirement                       Priority          Verification
  ----------------- --------------------------------- ----------------- -----------------
  FR-900-001        Accept remote operator commands   High              Test

  FR-900-002        Display robot status              High              Test

  FR-900-003        Stop on communication loss        High              Test

  FR-900-004        Allow emergency override          High              Test
  ---------------------------------------------------------------------------------------

**Implementation status (2026-08-08): MOSTLY MISSING.** This entire requirement group describes a remote-operator capability that does not exist in the codebase — no teleop/RC/remote-command receive path was found anywhere (repo-wide grep). FR-900-002 (display status) is the one partial exception: `display.py` shows live state/status on the rover's own local screen, but that's a local HUD, not remote operator display. FR-900-001/003/004 are unbuilt: no remote commands to accept, no communication-loss detection (nothing to lose), no remote emergency-override path (voice commands and the physical E-stop are the only external controls that exist). This matches M-011 (Remote administration) below, also not built.

# Acceptance Criteria

# FR-1000 Autonomous Navigation

  ---------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                   Priority          Verification
  ----------------- --------------------------------------------- ----------------- -----------------
  FR-1000-001       Navigate without operator input               High              Test

  FR-1000-002       Avoid obstacles                               High              Test

  FR-1000-003       Maintain planned route                        High              Test

  FR-1000-004       Transfer control back to operator on demand   High              Test
  ---------------------------------------------------------------------------------------------------

**Implementation status (2026-08-08): DONE at milestone-1 scope, not live-verified for motion.** `navigation.py::Navigator` resolves and drives routes (known waypoints, room-graph shortest-path via `networkx`, or straight-line fallback) through a `NAVIGATE` FSM state; obstacle avoidance exists both in the base reactive FSM (`ROAM`/`AVOID`) and as `Navigator`'s own self-contained copy of that logic. Explicitly milestone-1, not SLAM: dead-reckoning odometry only, no room-identification heuristic, no obstacle-aware global planner beyond the straight-line fallback (all honestly documented in the code's own comments). Voice `stop`/similar commands return control to the operator. **Caveat:** as of 2026-08-08, init/safety/battery-shutdown have been live-verified on hardware for the first time, but nothing has yet commanded the drive base live — `NAVIGATE`/obstacle avoidance remain sim-tested only, not yet hardware-verified in motion.

# Acceptance Criteria

# FR-1100 Diagnostics and Logging

  ------------------------------------------------------------------------------------
  Requirement ID    Requirement                    Priority          Verification
  ----------------- ------------------------------ ----------------- -----------------
  FR-1100-001       Monitor subsystem health       High              Test

  FR-1100-002       Record warnings and faults     High              Test

  FR-1100-003       Maintain timestamped logs      High              Test

  FR-1100-004       Provide diagnostic test mode   High              Test
  ------------------------------------------------------------------------------------

**Implementation status (2026-08-08): DONE.** `brain.py::_check_health()` monitors IMU/encoders/current/battery-ADC every tick; `logsetup.py::log_event()` tags real fault/abort sites with structured `EVENT=<NAME>` markers (`IMU_FAULT`, `LOW_BATTERY`, `OBSTACLE_STOP`, `NAVIGATION_ABORT`, `AI_TIMEOUT`, etc. — grep-able, added 2026-08-08); a rotating file handler keeps timestamped persistent logs; `diagnostics.py` provides the self-test mode. `ESTOP_ACTIVE`/`WATCHDOG_FAULT` are deliberately untagged — the first has no GPIO sense pin to observe, the second can't self-log since the process is being killed by the time it would fire (moot anyway, since no watchdog timeout is actually configured — see FR-300).

# Acceptance Criteria

# FR-1200 Mobility Intelligence and Stair Navigation

  --------------------------------------------------------------------------------------------------------------
  Requirement ID    Requirement                                              Priority          Verification
  ----------------- -------------------------------------------------------- ----------------- -----------------
  FR-1200-001       Detect stairways                                         High              Test

  FR-1200-002       Select floor or stair mode                               High              Test

  FR-1200-003       Monitor traction and tilt during climbing                High              Test

  FR-1200-004       Support multi-floor navigation through the world model   High              Test
  --------------------------------------------------------------------------------------------------------------

**Implementation status (2026-08-08): NOT IMPLEMENTED, correctly and deliberately.** No `STAIR_*` states exist. This matches `docs/WildWilly_Claude_Fix_Implementation_Plan.md` §17, which explicitly says not to build stair-climbing without hardware/testing support in place first — this is Priority 2, lowest, and its absence is intentional, not a gap to close now. Matches M-006 below (reclassified from must-have to stretch goal 2026-07-18).

# Acceptance Criteria

WildWilly shall initialize correctly, operate safely under manual control, detect faults, avoid obstacles, support autonomous navigation, and enter a safe state when power, communications, or safety conditions become invalid.

# Mission-Level Functional Requirements (M-001--M-012)

Moved here from the WildWilly Master Engineering Package (rev 6.0.7 --- corrected 2026-08-08, the referring copy had drifted to the superseded rev 6.0) so this document is the single source for all functional-requirement content. These are the mission-level requirements referenced by that document\'s requirements-traceability table (its section 2.3); the FR-xxx requirements above remain the detailed, subsystem-level breakdown. M-006 (stair climbing) was reclassified from a must-have to a stretch goal on 2026-07-18 --- the rover\'s baseline scope is drive, see, talk/listen, arm pick/place on flat ground, and basic flat-terrain autonomy.

  ---------------------------------------------------------------------------------------------------------
  ID             Requirement                                            Class
  -------------- ------------------------------------------------------ -----------------------------------
  M-001          Autonomous navigation                                  Baseline --- DONE, milestone-1 (FR-1000)

  M-002          Voice command processing                               Baseline --- DONE (voice.py)

  M-003          Local AI inference                                     Baseline --- DONE (ai_provider.py::LocalAIProvider)

  M-004          Object recognition                                     Baseline --- DONE (vision.py; CPU inference, no Hailo NPU installed on this unit)

  M-005          Obstacle avoidance                                     Baseline --- DONE (FR-1000)

  M-006          Stair climbing                                         STRETCH (reclassified 2026-07-18) --- correctly not implemented, hardware-gated (FR-1200)

  M-007          Robotic-arm manipulation (pick/place on flat ground)   Baseline --- PARTIAL: works as fixed primitive sequence, no per-joint IK (FR-700)

  M-008          Battery monitoring                                     Baseline --- DONE, live-verified 2026-08-08 (FR-200)

  M-009          Thermal monitoring                                     Baseline --- **MISSING**: no thermal/temperature code exists anywhere in the repo (repo-wide grep, confirmed 2026-08-08)

  M-010          Emergency shutdown                                     Baseline --- PARTIAL: hardware E-stop real but not software-observable; software battery-shutdown DONE (FR-300/FR-200)

  M-011          Remote administration                                  Baseline --- **MISSING**: no remote command/teleop path exists (FR-900)

  M-012          Local data storage                                     Baseline --- DONE (storage.py, SQLite via memory_store.py/world_model.py)
  ---------------------------------------------------------------------------------------------------------

**Summary (2026-08-08):** 7 of 12 mission-level requirements are DONE, 2 PARTIAL (M-007 arm IK, M-010 E-stop software-observability), 2 MISSING (M-009 thermal, M-011 remote administration), 1 correctly deferred (M-006 stair climbing). M-009 and M-011 were already flagged as open in prior session notes; this pass confirms both are still fully unbuilt, not just untested.
