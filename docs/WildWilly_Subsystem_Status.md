# WildWilly — Subsystem Implementation Status

Per §22 of `WildWilly_Claude_Fix_Implementation_Plan.md`: every subsystem tagged
`IMPLEMENTED` / `HARDWARE REQUIRED` / `SIMULATION ONLY` / `PARTIALLY IMPLEMENTED` / `PLANNED`.
This is the software-architecture companion to `WildWilly_Claude_Fix_Gap_Analysis.md` (which
tracks status against the fix plan's own section numbers) — this doc instead organizes by actual
Python module, for someone asking "what can this specific piece of code do today."

**Snapshot date: 2026-08-08, last updated 2026-08-18.** Update this table whenever a subsystem's
status actually changes — stale tags here are worse than no tags.

## Capability caution (§22's own instruction)

**Do not describe this robot as having SLAM, autonomous house navigation, persistent spatial
memory, or stair climbing.** None of those are implemented and tested, even though several
modules below sound adjacent to them:

- `world_model.py`/`mapping.py`/`navigation.py` (added 2026-08-08) are explicitly **milestone-1,
  not SLAM** — dead-reckoning odometry only (no slip correction, no IMU fusion), no
  obstacle-aware global path planning (straight-line fallback when no room graph is known), no
  room-identification heuristic. See each module's own docstring for the exact scope.
- Persistent spatial memory exists (`world_model.db`) but has never round-tripped across a real
  power cycle on hardware — only in unit tests and `WILLY_SIMULATE=1`.
- Stair-climbing has **zero code** — §17 is intentionally unimplemented, deferred pending
  hardware/testing support per the plan's own instruction.
- Nothing below has been **live-verified** (see the standing note at the bottom) — every status
  tag here describes what the code does when it runs, not that it has been confirmed running on
  the physical rover with this session's changes.

## Subsystem table

| Module | Status | Note |
|---|---|---|
| `brain.py` (core FSM) | **PARTIALLY IMPLEMENTED** | Phase 1 safety rewrite + all subsequent phases are code-complete and off-hardware tested, but not live-verified — see standing note below. |
| `safety.py` (SafetyController) | **IMPLEMENTED** | Sole motion gate, unchanged since Phase 1. 25 tests (`test_safety.py`+`test_safety_controller.py`). Not live-verified. |
| `motors.py`/`steering.py`-equiv (`motors.py`) | **PARTIALLY IMPLEMENTED** | Ran successfully during the 2026-08-02 baseline pass; not re-verified against this session's Phase 1+ rewrite on real hardware. |
| `sensors.py` (Sonar/ADC/Encoders/CurrentMonitor) | **PARTIALLY IMPLEMENTED — open regression** | IMU reset-timing bug root-caused and fixed live 2026-08-14 (see below), verified via standalone construction and through the real `IMU`/`SonarArray`/`ADC` classes. **Since 2026-08-16, a different, undiagnosed fault has `willy-rover.service` crash-looping again**: BNO085 doesn't ack at all at 0x4a (vs. the 08-14 bug, which acked but NACK'd the first write) — the 08-14 patch is confirmed still present and unmodified, so this is a new fault, not a regression of that fix. Not yet diagnosed as of the last commit touching this doc; see the standing note at the bottom. Sonar/ADC portions unaffected by this fault. |
| `arm.py` | **HARDWARE REQUIRED, not re-verified this session** | Resolved 2026-08-08 (arm PCA9685 VCC had been disconnected — power issue, not bus/software); `willy-rover.service` reached `active (running)` that day for the first time since Phase 1. Not touched again 2026-08-14 — session paused before restarting the service, pending battery charge (see standing note). |
| `odometry.py` | **PARTIALLY IMPLEMENTED** | Dead-reckoning math is solid and unit-tested; `WHEEL_DIAMETER_M`/`TRACK_WIDTH_M` are unconfirmed placeholder measurements (flagged in `config.py`) — do not trust absolute distances. |
| `world_model.py` | **PARTIALLY IMPLEMENTED** | Milestone 1 — see Capability caution above. 8 tests, fully off-hardware. |
| `mapping.py` | **PARTIALLY IMPLEMENTED** | Milestone 1. Room-identification not attempted. 11 tests. |
| `navigation.py` | **PARTIALLY IMPLEMENTED** | Milestone 1. Straight-line fallback when no room graph known; obstacle avoidance is a self-contained reactive copy, not a global planner. 16 tests. |
| `ai_provider.py` | **IMPLEMENTED** | Unified `CloudAIProvider`/`LocalAIProvider`, 27 tests, all off-network. Real Anthropic API connectivity is exercised in production (`ANTHROPIC_API_KEY`) but not by the automated test suite. |
| `vision.py` (`ObjectDetector`) | **HARDWARE REQUIRED, disabled by default** | `ENABLE_OBJECT_RETRIEVAL=False` — CPU-only YOLOv8. Hailo-10H AI HAT+2 driver/firmware bring-up completed 2026-08-16 (`/dev/hailo0` live, `hailortcli` confirms HAILO10H fw 5.1.1) — root cause was a Hailo-8-only package line installed instead of `hailo-h10-all`, not a hardware fault; see `CLAUDE.md`. `vision.py` itself not yet ported to use the NPU. Bearing/range are explicitly heuristic, not calibrated. |
| `voice.py` (`VoicePipeline`) | **PARTIALLY IMPLEMENTED, enabled** | `ENABLE_VOICE=True` — the real trained "Hey Willie" wake model (`models/hey_willie.onnx`, trained 08-07) has been deployed since 2026-08-16, replacing the earlier "Hey Jarvis" placeholder this row used to describe. Audio I/O (pipewire conflict) and an acoustic feedback loop (TTS leaking into the mic and self-triggering) were fixed the same day. Command vocabulary since expanded (shutdown, status/battery/diagnostics, arm poses, come_here/follow, wave, time query). Not yet live-verified end-to-end with real voice input. |
| `retrieval_task.py` | **PARTIALLY IMPLEMENTED** | Grasp is a fixed primitive sequence (no per-joint IK calibration), hand-off confirmation is timeout-based (no tactile sensor). `_grasp()`'s pulse sequence was non-blocking-ized 2026-08-18 (was blocking the tick thread ~1.1s, during which a tilt/battery/sensor-fault abort() couldn't run) — see `arm.py`'s FR-700-004 note. 7 new tests (`tests/test_retrieval_task.py`), had zero coverage before. |
| `pursuit_task.py` (`PursuitTask`) | **PARTIALLY IMPLEMENTED** | FR-1000 "come here"/"follow me". Same shape as `retrieval_task.py` (LOCALIZE/APPROACH sub-states, one authoritative `SafetyController` gate, same Directive 1-4 abort() preemption points). `mode='come_here'` approaches to `PURSUIT_STANDOFF_CM` and stops (`DONE`); `mode='follow'` continues into a `FOLLOWING` state with no built-in end condition — only exits via abort(). No dedicated test file exists for this module. Voice-triggered (`come_here`/`follow` intents), so blocked on the same voice live-verification gap as `voice.py` above. |
| `memory_store.py` | **IMPLEMENTED** | Corrupted-database recovery added 2026-08-08 (verified against a real garbage file, not just unit tests). |
| `storage.py` | **IMPLEMENTED** | Configurable roots exist and are tested; this unit has no physical SSD/SD split to actually tier across yet (confirmed via `df`/`mount`). |
| `smart_home.py` | **PLANNED / disabled** | `ENABLE_SMART_HOME=False` — needs Willie's own Google account credentials, not yet provisioned. |
| `email_client.py` | **IMPLEMENTED** | `ENABLE_EMAIL=True`, Gmail app-password login verified working 2026-08-06. |
| `display.py` (`WillyFace`) | **PARTIALLY IMPLEMENTED** | Works live; known non-fatal pygame/Wayland init issue under `WILLY_SIMULATE=1` (daemon thread, doesn't block startup) — display hardware itself, not simulation, is out of scope for that gap. |
| E-Stop | **PLANNED / HARDWARE REQUIRED** | No GPIO sense pin wired — software has no way to observe it. Not a code gap. |
| Stair-climbing | **PLANNED** | Zero code, intentionally — per the plan's own instruction not to build this without hardware/testing support. |

## Architecture (as actually wired, not aspirational)

```text
Voice (ENABLE_VOICE=False, disabled)         Vision (ENABLE_OBJECT_RETRIEVAL=False, disabled)
        |                                              |
        v                                              v
  ai_provider.py (AIProvider: Cloud/Local)      world_model.py (update_observation)
        |                                              |
        v                                              v
  brain.py STUCK state (motion-decision       mapping.py / navigation.py
  queries only, via build_world_state())      (Mission -> global route -> local planner)
        |                                              |
        +---------------------+-----------------------+
                              v
                     safety.py SafetyController
                     (sole authoritative gate --
                      approve_motion(), unchanged
                      by every phase above it)
                              |
                              v
                     motors.py DriveBase (real I2C/PWM,
                     or hw_sim.py under WILLY_SIMULATE=1)
```

Every arrow into `SafetyController` is a *request*, never a bypass — §25's rule ("Willy's AI may
decide what it wants to accomplish, but it may never decide whether it is safe to move") holds
structurally: nothing added since Phase 1 gained a second path to the motors.

## Standing note: nothing below Phase 1 is live-verified

**Update 2026-08-14: the I2C hardware fault arc referenced below is now closed** (arm PCA9685 VCC
fix 2026-08-08 + IMU reset-timing fix same day as this note — see `sensors.py` row above). IMU,
sonars, and battery ADC are now live-verified reading real values through the actual sensor
classes. Motors/full `RoverBrain.run()` still not attempted — session paused with
`willy-rover.service` stopped because the battery read 9.5V (below `BAT_SHUTDOWN_V`); user
confirmed the packs have never been charged, so this is expected first-use state, not a fault.
Resume with a service restart once the packs are charged above `BAT_WARN_V` (11.4V).

Every "PARTIALLY IMPLEMENTED" tag above that predates this update was blocked by the same
underlying gap: an I2C hardware fault (symptom shifted across sessions — noisy bus, then BNO085
IMU `enable_feature` failure, then the arm's PCA9685@0x43 not answering, then the IMU reset-timing
bug fixed today) that prevented running a real `RoverBrain.run()`. Update the per-row tags above
the moment each subsystem gets its own live-verification pass — don't let this doc's tags drift
stale in the optimistic direction.

**2026-08-16 regression, not yet diagnosed:** `willy-rover.service` found crash-looping (91+
restarts) since the prior night's boot (18:47 EDT 08-15), dying in `sensors.py IMU.__init__` with
`ValueError: No I2C device at address: 0x4a` — the BNO085 does not ack at all on a fresh
`i2cdetect -y 1` (0x27/0x40/0x42/0x43/0x44/0x45/0x48/0x60/0x61/0x70 all present, 0x4a missing).
This is a different symptom from the reset-timing bug closed in
[[project_rover_imu_reset_timing_fix]] (that one acked on `i2cdetect` but NACK'd the first write;
this one doesn't ack at all) — the reset-timing patch in `sensors.py` was confirmed still present
and unmodified, so this is not a regression of that fix. Not yet investigated further (found
incidental to unrelated Hailo AI HAT work this session) — start from a physical power/connection
check on the IMU's rail, same as the arm PCA9685 precedent in
[[project_rover_i2c_bus_fault]], before re-chasing software.
