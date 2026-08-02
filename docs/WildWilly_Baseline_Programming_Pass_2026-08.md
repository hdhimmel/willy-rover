# WildWilly — hardware/safety baseline programming pass (2026-08-02)

Companion to `WildWilly_Functional_Requirements_Document_v1.1.md` and the master engineering
package. Tracks what this pass implemented against the FRD, and what's still open — see the
plan this pass followed for the original scoping decisions (hardware/safety baseline only, no
voice/vision/AI/remote-admin/storage; steering and arm get driver-level code, not autonomous
kinematics/presets, since the master doc itself flags those as undesigned).

## Why

The code had fallen behind several hardware revisions: `motors.py` still drove raw GPIO
H-bridge pins (real hardware is 2x FeatherWing MotorKit boards over I2C at 0x60/0x61), and
`sensors.py`'s `IMU` class read a chip address (0x68) that no longer exists on the bus — this
was **actively crash-looping `willy-rover.service` in production** at the start of this pass
(confirmed via `journalctl`, `OSError: [Errno 121] Remote I/O error`). There was no code at all
for steering, the arm, encoders, or current monitoring, despite all of that hardware being
physically installed and bus-confirmed.

## What changed this pass

- **IMU**: dead MPU6050@0x68 → BNO085@0x4A via `adafruit-circuitpython-bno08x`. This was the
  active crash. Fixed first, verified via a clean service restart.
- **Environment**: none of the Adafruit CircuitPython stack was installed, and pip is
  externally-managed on this OS — created `venv/` (`--system-site-packages`) and pointed
  `willy-rover.service`'s `ExecStart` at it. Captured `requirements.txt` since `venv/` is
  gitignored. Also discovered and fixed: the classic `RPi.GPIO` (pulled in as a Blinka
  dependency) doesn't support the Pi 5's RP1 chip at all — swapped for the system's
  `rpi-lgpio` drop-in (same import name, zero code changes, this would have broken sonar too).
- **Sonar bug** (independent, caught auditing GPIO pins against the master doc): front/left
  echo pins were on GP11/GP19 in config, not the documented GP26/GP14. Front and left obstacle
  detection have likely been silently returning "no obstacle" (999cm) on every read since
  whenever that drifted. Fixed.
- **`config.py`**: rebuilt the hardware-constants section end to end against the master doc's
  §5.2 authoritative address map (was stale/wrong in several places — e.g. `PCA_ADDR_1=0x40`
  collided with the real INA260 address).
- **`motors.py`**: `DriveBase` rewritten for I2C MotorKit (was GPIO H-bridge), same public API.
  Added slew-rate-limited speed ramping (FR-400-003). Added `Steering` (PCA9685@0x42) —
  centers and holds only, no kinematics.
- **`sensors.py`**: added `Encoders` (MCP23017@0x27, best-effort polling, no interrupt line
  exists) and `CurrentMonitor` (INA260 x3, read-only).
- **`arm.py` + `arm_jog.py`** (new): PCA9685@0x43 driver + interactive bench-calibration tool.
  No IK, no presets, no autonomous motion.
- **`brain.py`**: INIT self-test gate (I2C roll-call + first-reading checks, blocks motion on
  failure), battery voltage ladder with hysteresis (replaces the old flat two-tier check),
  hand-rolled systemd watchdog (`WatchdogSec=500ms` added to the service file), formalized
  priority arbitration, renamed `ESTOP`→`TILT_FAULT` (it was never the physical E-stop, which
  software cannot observe — see gaps below).

## FRD coverage after this pass

| FR | Status | Note |
|---|---|---|
| FR-100 Startup/self-test | Implemented | INIT gate in brain.py; auto-start already existed via systemd |
| FR-200 Power monitoring | Partial | Voltage + current all readable; no overcurrent auto-cutoff (no threshold values exist to set one) |
| FR-300 E-stop | **Gap** | Hardware-only latching cut, no GPIO sense pin documented anywhere — software cannot observe it. Flagged in code, not solved. |
| FR-400 Mobility/drive | Implemented | Real I2C drive, ramped speed, software speed limit |
| FR-500 Encoders/speed | Partial | Reading + stall-detection primitive exist; no closed-loop speed control wired in (interrupt-less polling resolution is a real limit); no distance-in-meters (wheel diameter unknown) |
| FR-600 Steering | Driver-only | Centers and holds; kinematics undesigned in the master doc itself |
| FR-700 Arm | Driver-only | No limits/presets/IK — §20.6 bench calibration hasn't been run |
| FR-800 Sensors | Implemented | IMU/sonar working; `is_healthy` added for FR-800-004 |
| FR-900 Manual ops | **Out of scope** | No remote-control comms channel exists or was built this pass |
| FR-1000 Autonomous nav | Unchanged | Existing sonar-based obstacle avoidance + Claude escalation, not touched this pass |
| FR-1100 Diagnostics | Partial | Current/encoder data available; no persistent timestamped log store beyond systemd journal |
| FR-1200 Stairs | Out of scope | M-006 is a stretch goal per the FRD's own text |
| M-002/003/004/011/012 | Out of scope | Voice, local AI inference, object recognition, remote admin, local data storage — need entirely new subsystems, explicitly deferred this pass |

## Known gaps / open items

- **E-stop sensing (FR-300-001)**: no GPIO tap exists. Recommend wiring the switch's spare
  contact to a spare GPIO or MCP23017 pin as a future hardware task — not done this pass.
- **Battery divider re-cal**: done in an earlier session this same day (0.2481→0.2865,
  verified against a multimeter to 1mV) — see `WildWilly_ADS1115_Bringup_Checklist.md`.
- **Charge-sense divider**: still not wired (AIN0 only) — `is_charging` hardcoded `False`.
- **Overcurrent thresholds**: no numeric trip values exist anywhere in the documentation.
  Current is monitored/logged only.
- **Encoder counts/rev (3292)** is a "starting value" from the motor listing, not
  bench-confirmed per the master doc's own caveat. Distance-in-meters needs wheel diameter,
  which wasn't in the gathered doc material.
- **Steering/arm servo range mode** unconfirmed per-unit (500-2500 vs 1000-2000 vs 900-2100µs)
  — steering defaults to the narrowest range as a conservative clamp; widen only after a bench
  check.
- **Pi-rail INA260 (0x44) reads ~11.4V**, not the ~5V the master doc's power table implies for
  that tap point — closer to the battery pack voltage. Worth checking whether it's actually
  wired pre-buck rather than post-buck as documented, or whether the Pi wasn't drawing through
  that path during this test. Not a code issue — the driver reports the chip's real register
  value faithfully.
- **Controlled shutdown (10.2V tier)** is software-side only (brake + halt) — no actual OS
  poweroff is wired up, since that needs elevated privileges and an explicit decision this
  pass didn't cover.
- **Steering/arm kinematics** remain fully undesigned per the master doc — this pass is
  driver-level only, matching the scoping decision going in.

## Verification status

Every new hardware class (IMU, DriveBase, Steering, Encoders, CurrentMonitor, Arm) was
construction-tested and read-only-tested against the real board this session. Live actuation
(driving, steering centering, arm jogging) has **not** been run yet — deferred to a supervised
session per this pass's safety plan, since motors.py now genuinely drives real wheels and
Steering.center_all() genuinely moves real servos (unlike before this pass, when motors.py's
GPIO pins were disconnected). `brain.py`'s battery-ladder hysteresis logic was verified by
manual trace of a full discharge/recharge sequence (not live-executed) — see the review that
caught and fixed a real bug where SAFE_MODE/SHUTDOWN could never release if voltage recovered
past the intermediate 'rth' tier in one hysteresis step.

## Next steps

1. Supervised live test: drive at low speed, confirm steering centers cleanly, confirm
   encoders report counts while driving, confirm the self-test gate actually blocks motion
   when a device is unplugged.
2. Run `arm_jog.py` to get real per-joint limits and record them in `config.py`/`arm.py`.
3. Design steering kinematics once per-corner clearance is measured on the bench.
4. Wire the charge-sense divider; investigate the Pi-rail INA260 voltage anomaly.
5. Scope voice/vision/AI/remote-admin/storage as separate work when ready.
