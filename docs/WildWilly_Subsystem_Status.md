# WildWilly — Subsystem Implementation Status

Per §22 of `WildWilly_Claude_Fix_Implementation_Plan.md`: every subsystem tagged
`IMPLEMENTED` / `HARDWARE REQUIRED` / `SIMULATION ONLY` / `PARTIALLY IMPLEMENTED` / `PLANNED`.
This is the software-architecture companion to `WildWilly_Claude_Fix_Gap_Analysis.md` (which
tracks status against the fix plan's own section numbers) — this doc instead organizes by actual
Python module, for someone asking "what can this specific piece of code do today."

**Snapshot date: 2026-08-08.** Update this table whenever a subsystem's status actually changes —
stale tags here are worse than no tags.

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
| `sensors.py` (Sonar/ADC/Encoders/CurrentMonitor) | **IMPLEMENTED** | IMU root-caused and fixed live 2026-08-14: `adafruit_bno08x.hard_reset()`'s stock 10ms post-RST-release delay was too short for the BNO085 to boot its SH-2 firmware, causing every `soft_reset()` I2C write to NACK (`OSError: Errno 121`) — patched in `sensors.py` to hold reset 300ms. Verified via standalone cold construction (service stopped) and again through the real `IMU`/`SonarArray`/`ADC` classes: quaternion streaming, sonars reading live distances, ADC reading live battery voltage. Not yet re-verified through a full `willy-rover.service` restart. |
| `arm.py` | **HARDWARE REQUIRED, not re-verified this session** | Resolved 2026-08-08 (arm PCA9685 VCC had been disconnected — power issue, not bus/software); `willy-rover.service` reached `active (running)` that day for the first time since Phase 1. Not touched again 2026-08-14 — session paused before restarting the service, pending battery charge (see standing note). |
| `odometry.py` | **PARTIALLY IMPLEMENTED** | Dead-reckoning math is solid and unit-tested; `WHEEL_DIAMETER_M`/`TRACK_WIDTH_M` are unconfirmed placeholder measurements (flagged in `config.py`) — do not trust absolute distances. |
| `world_model.py` | **PARTIALLY IMPLEMENTED** | Milestone 1 — see Capability caution above. 8 tests, fully off-hardware. |
| `mapping.py` | **PARTIALLY IMPLEMENTED** | Milestone 1. Room-identification not attempted. 11 tests. |
| `navigation.py` | **PARTIALLY IMPLEMENTED** | Milestone 1. Straight-line fallback when no room graph known; obstacle avoidance is a self-contained reactive copy, not a global planner. 16 tests. |
| `ai_provider.py` | **IMPLEMENTED** | Unified `CloudAIProvider`/`LocalAIProvider`, 27 tests, all off-network. Real Anthropic API connectivity is exercised in production (`ANTHROPIC_API_KEY`) but not by the automated test suite. |
| `vision.py` (`ObjectDetector`) | **HARDWARE REQUIRED, disabled by default** | `ENABLE_OBJECT_RETRIEVAL=False` — CPU-only YOLOv8 (no Hailo NPU on this unit), bearing/range are explicitly heuristic, not calibrated. |
| `voice.py` (`VoicePipeline`) | **PLANNED / disabled** | `ENABLE_VOICE=False` — wake-word model is a temporary "Hey Jarvis" placeholder, not the real trained "Hey Willie" model (training was deferred, see wake-word memory tracking). Code is otherwise complete (STT/local-LLM/TTS all previously verified working). |
| `retrieval_task.py` | **PARTIALLY IMPLEMENTED** | Best-covered subsystem in the whole plan per the gap analysis — grasp is a fixed primitive sequence (no per-joint IK calibration), hand-off confirmation is timeout-based (no tactile sensor). |
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
