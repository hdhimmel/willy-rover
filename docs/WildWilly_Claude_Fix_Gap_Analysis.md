# WildWilly — Gap Analysis vs. `WildWilly_Claude_Fix_Implementation_Plan.md`

**Session: 2026-08-07.** Audit of the current `willy-rover` repo (18 `.py` files, ~2091 lines,
commit `516d1ec`) against every section of `WildWilly_Claude_Fix_Implementation_Plan.md`, per
that document's own §27 instruction to review before implementing. No code changed in this pass —
read-only audit only.

Status legend: **DONE** / **PARTIAL** / **MISSING** / **CONFLICT** (does the opposite of what the
plan asks) / **N/A-HW** (blocked on hardware that doesn't exist yet, not a code gap).

## Priority 0 — Safety and Control-Loop Architecture

| § | Topic | Status | Finding |
|---|---|---|---|
| 2 | Non-blocking control loop | **CONFLICT** | `brain.py::_stuck()` calls `claude_client.py::ClaudeClient.decide()` directly on the tick thread — a blocking `urllib.request.urlopen(..., timeout=8)` HTTP call. `motors.py`'s `forward_for`/`reverse_for`/`turn_*_for` also block via `time.sleep(t)`, and `_avoid()`/`_dock()`/`_stuck()` call them directly from `_tick()`. The systemd watchdog `WATCHDOG=1` is sent at the *top* of `_tick()`, before these blocking calls, so it isn't starved outright — but real Directive 1-5 safety processing (tilt/battery) is delayed for the full blocking duration each time this path fires. |
| 3 | Safety gate between AI and motors | **CONFLICT** | No `SafetyController.approve_motion()` or equivalent exists. Claude's proposed `duration` is cast to `float` and passed straight to `motors.forward_for()` etc. with **no clamp** — an unreasonable duration from the LLM is not rejected (the plan's own §20 test list calls this out explicitly: "excessive duration"). Speed *is* clamped (`motors.py` clamps to `config.SPEED_MAX` at the motor layer), and this path is only reachable after `CLAUDE_ESCALATE_AFTER=5` consecutive stuck-avoid cycles, so blast radius is contained today — but it is still the AI directly commanding motors with no independent legality check, which §3 explicitly forbids. |
| 4 | Watchdog redesign | **PARTIAL** | `_check_health()` runs every tick and logs IMU/encoder/current-monitor/battery-ADC faults, but **only logs** — it never stops motors or changes FSM state on a sensor fault. Only the battery-ADC failure path is actually safe today (a failed read defaults `battery_volts` to 0, which the existing tier ladder correctly treats as `shutdown`). An IMU thread stall does not stop motion — `_tick()` reads `self.imu.tilt` unconditionally, which returns the last cached value once the thread dies, so a stale tilt reading can mask an actual tilt fault indefinitely. No separate supervisor task; watchdog heartbeat lives on the same thread as the blocking calls in §2. |
| 5 | E-Stop integration | **N/A-HW / MISSING** | Already honestly flagged in `brain.py`'s own comments: "software has no way to observe [E-stop] — the hardware-only latching cut has no documented GPIO sense pin." This needs a wiring change (a sense pin into a GPIO) before any software can be written against it — not purely a code gap. |
| 6 | Battery voltage logic | **PARTIAL** | The protection half is already done well: `config.py` has a distinct `BAT_WARN/RTH/SAFE/SHUTDOWN_V` ladder with hysteresis (`BAT_HYSTERESIS_V`), separate from the old flat low/critical pair, and `brain.py`'s `_update_bat_tier` implements one-way-worse-then-hysteresis-to-recover correctly. What §6 flags — `battery_pct` is still a plain linear map between `BAT_SHUTDOWN_V` and `BAT_FULL_V` — is still present, but it is **display-only** (used for the HUD/voice announcements, not for any safety decision, which all key off raw voltage vs. the tier thresholds directly). No code comment documents that voltage-under-load ≠ open-circuit voltage, as §6 asks. |

## Priority 1 — Motion Foundation / World Model / Navigation / Vision

| § | Topic | Status | Finding |
|---|---|---|---|
| 7 | RP2040 encoder architecture | **N/A-HW** | No RP2040 exists on this unit per any prior session or doc. Current `Encoders` (MCP23017 polling, ~1kHz ceiling, self-documented as lossy at speed) already exposes close to the requested API shape (`counts`, `counts_per_sec`, `is_healthy`, per-wheel `stalled()`) — swapping to an RP2040 later looks like a backend swap behind the existing interface, not a rewrite, consistent with how `vision.py`/`smart_home.py` already handle their own hardware-substitution notes. |
| 8 | Odometry | **DONE** (2026-08-07) | `odometry.py` added: `Odometry.update()` (called every `brain.py` tick) converts averaged left/right wheel counts into a `Pose(x,y,heading,linear_velocity,angular_velocity,timestamp,stale)`, logged at `POSE_LOG_INTERVAL_S`. Pure-logic `integrate()` unit-tested (`tests/test_odometry.py`, 6 cases). Dead-reckoning only — no slip correction, no IMU fusion — and `WHEEL_DIAMETER_M`/`TRACK_WIDTH_M` are unconfirmed placeholder measurements (flagged in `config.py`); not yet consumed by navigation/mapping since neither exists (§9/§11). |
| 9 | World model | **DONE (milestone 1)** (2026-08-08) | `world_model.py` added: `WorldModel` class + `RobotState/Pose(delegated)/Room/Doorway/Obstacle/Object/Landmark/Route/Observation` types, exposing exactly the plan's own API (`update_observation/get_robot_pose/get_nearby_obstacles/get_room/remember_object/save/load`). Layered per §9's own instruction (obstacle map / odometry-delegated / rooms / objects-landmarks / routes), explicitly not SLAM. Own SQLite file (`world_model.db`, separate from `memory.db` per master doc §13.4), same WAL/lock/upsert convention as `memory_store.py`. Wired into `brain.py`: constructed + auto-loaded in `__init__`, a passive per-tick sonar->obstacle feed (no motor consequence), saved on shutdown. 8 unit tests (`tests/test_world_model.py`), all off-hardware. Room-identification (§10 step 6) is an intentional gap, not attempted yet — rooms/doorways/routes have no producer wired in this step (that's §10/§11). |
| 10 | Mapping / learning mode | **DONE (milestone 1)** (2026-08-08) | `mapping.py` added: `MappingSession` records vision-detected objects/landmarks into `world_model.py` while active and snapshots the map (`world_model.save()`) on `stop()`/`abort()` — persistent load already happens automatically (`WorldModel.__init__` calls `load()`, §9). Voice-triggered via new `map`/`stop_map` intents (mirrors the existing `retrieve` intent's queue-and-drain pattern in `voice.py`/`brain.py`). Deliberately **not** a top-level `brain.py` FSM state, unlike the plan's original phrasing suggested — see `mapping.py`'s module docstring: `self.mapping.active` is an orthogonal flag brain.py checks passively alongside the existing ROAM/SLOW/AVOID/STUCK dispatch (same pattern as the §9 odometry/obstacle logging), so driving during mapping is *literally* the unmodified existing reactive FSM, not a copy of it — avoids a real bug the original phrasing would have hit (routing mapping through its own top-level state and calling into `_avoid()`/`_stuck()` directly would inherit their internal `self._go('ROAM')`/`self._go('STUCK')` transitions and silently exit mapping mode the instant the path cleared). Aborted on the same Directive 1-4 preemption points as `RetrievalTask` (sensor/tilt/battery faults, shutdown). Room-identification (§10 step 6) remains an explicit, undone gap this milestone, matching the plan's own "when possible" wording. 11 tests (`tests/test_mapping.py`): pure-logic on `project_point()`/session start-stop-tick-abort with fakes, plus one full `RoverBrain()` simulation-lifecycle subprocess test. |
| 11 | Navigation layer | **DONE (milestone 1)** (2026-08-08) | `navigation.py` added: `Mission` (room name / route name / raw x,y) + `Navigator` resolving a global route (known `Route` waypoints verbatim; a `Room` target via a `networkx` shortest-path over known Room/Doorway records, falling back to a single straight-line waypoint at the target's centroid when no graph connectivity is known yet — honest, not fake obstacle-aware planning) and driving it via a local planner (bearing-to-waypoint heading correction + forward, all through `safety.py`'s existing gate, nothing new below it). Obstacle avoidance mirrors `brain.py`'s `_avoid()` reverse-then-turn pattern (same config constants) as a **self-contained copy inside `Navigator`**, not a direct call into `_avoid()` — same reasoning as §10's deviation: `_avoid()`'s own `self._go(...)` transitions are written for brain.py's top-level FSM and would corrupt whichever state calls into it. Unlike mapping, Navigator *does* own a top-level FSM state (`NAVIGATE`, brain.py's dispatch table + `_navigate()`), since driving (unlike passive observation) legitimately needs one — its own `SEEKING/AVOIDING/DONE/FAILED/ABORTED` sub-states live underneath it, same shape as `RetrievalTask`. Voice-triggered via the `go_to` intent, which was already queued by `voice.py` but never wired to an executor — now is. Aborted on the same Directive 1-4 preemption points as `RetrievalTask`/`MappingSession`. `networkx` added to `requirements.txt` (previously only a transitive dep). 16 tests (`tests/test_navigation.py`): route resolution (raw xy / named route / room-graph path / no-graph fallback / unknown mission), local-planner heading/arrival/obstacle-handoff logic with fakes, plus one full `RoverBrain()` simulation-lifecycle subprocess test. One real bug caught and fixed by the local-planner tests before commit: the initial turn-direction sign was inverted (turned right for a CCW/left bearing error) — round `heading_err>0` maps to `turn_left`, not `turn_right`, per `odometry.py`'s own CCW-positive convention. |
| 12 | YOLO / vision integration | **PARTIAL** | `vision.py`'s `detect()` returns `class/conf/bbox/frame_w/frame_h` but not `timestamp` or `camera_id` as the plan's detection shape wants, and bearing/range come from a separate `localize()` call rather than being bundled onto the detection. Already good: the code's own comments explicitly warn distance/bearing are heuristic, not calibrated ranging — exactly what §12 asks for ("do not describe bounding-box-size distance estimation as accurate ranging"). Fusion into a world model is blocked on §9. |

## Priority 1 — Memory / AI Interface / Retrieval

| § | Topic | Status | Finding |
|---|---|---|---|
| 13 | Memory architecture | **MISSING** | Single SQLite file, no RAM/SSD/SD tiering, no `WILLY_DATA_ROOT`/`MAP_ROOT`/`MEMORY_ROOT`/`LOG_ROOT` env vars — paths (`MEMORY_DB_PATH`, `LOG_DIR`) are hardcoded relative to the script directory. No storage-availability/permission startup checks. The underlying save/purge/replay mechanics are a reasonable seed for "long-term memory," just not tiered. |
| 14 | AI / LLM interface | **CONFLICT** | Three separate, un-unified AI call sites instead of one `AIProvider` abstraction: `claude_client.py::ClaudeClient.decide()` (motion-command-shaped, called only from `_stuck()` — this is the same object flagged in §3 as bypassing the safety gate), `cloud_ai.py::CloudAIClient.ask()` (free-text fallback, called from `voice.py`), and a third local-LLM call inlined directly inside `voice.py::_interpret_local()` (not even its own class). No structured world-state payload (room/pose/battery/goal/nearby_objects/routes) is assembled anywhere — inputs are raw sensor dicts today, which tracks with §9/§11 not existing yet to source that from. |
| 15 | AI confidence | **CONFLICT** | `voice.py::_interpret_local()`'s own comment admits it: "uses a plain heuristic (did the model return well-formed JSON we asked for) rather than a real probability" — `return parsed,0.8` on parse success, `return None,0.0` on any exception. This is exactly the anti-pattern §15 names: "Do not use 'valid JSON' as AI confidence." The *consequence* handling is already correct, though — low confidence does fall back to "ask for clarification" rather than guessing, which is what §15 wants downstream of a real confidence signal. |
| 16 | Retrieval behavior | **DONE** (mostly) | `retrieval_task.py` already implements almost exactly the requested state list — `LOCALIZE/APPROACH/GRASP/VERIFY/DELIVER/AWAIT_CONFIRM` — as its own sub-FSM, gated correctly behind `brain.py`'s Directive 1-5 checks, with `abort()` always called externally per §27's "never decide internally" pattern. Its own comments already honestly flag the two real remaining gaps: grasp is a fixed primitive sequence, not IK (no per-joint calibration exists — §20.6 in the master doc), and hand-off confirmation is timeout-based, not tactile-sensed. Best-covered section in the whole plan; what remains is hardware calibration work, not architecture work. |

## Priority 2 / Cross-Cutting

| § | Topic | Status | Finding |
|---|---|---|---|
| 17 | Stair-climbing prep | **MISSING (expected)** | No `STAIR_*` states exist. Plan explicitly says not to build this without hardware/testing support and marks it Priority 2 lowest — absence here is correct, not a gap to close now. |
| 18 | Configuration cleanup | **PARTIAL, already unusually rigorous** | Config values already carry dated calibration notes and explicit master-doc section citations (e.g. a 2026-08-02 GPIO pin fix, a 2026-08-02 battery-divider recalibration, per-value "confirmed/unconfirmed" flags). Credentials are correctly kept out of `config.py` (env var names/paths only). One thing worth explicit owner confirmation: `ENABLE_CLOUD_AI=True` and `ENABLE_EMAIL=True` are both default-on — each cites a specific FR number and a dated verification note, so this reads as an intentional, documented decision, not an oversight, but §18 is unusually blunt about not defaulting these on without the engineering package's explicit say-so. |
| 19 | Hardware abstraction | **DONE** (2026-08-07) for motors/sensors/arm; camera/display out of scope | `config.SIMULATE_HARDWARE` (env var `WILLY_SIMULATE=1`) gates every real I2C/GPIO open in `motors.py`/`arm.py`/`sensors.py`/`brain.py`'s own I2C self-test scan, both the module-level conditional imports and each class's construction/`_update()`. New `hw_sim.py` holds the two shared mocks (`SimMotor`, `SimServoBank`) that satisfy `DriveBase`/`Steering`/`Arm`'s existing interfaces unchanged — no caller-visible API change. `ObjectDetector` (`vision.py`) was already safely gated behind `ENABLE_OBJECT_RETRIEVAL` and didn't need this. `display.py`'s pygame/Wayland init is **not** covered — out of scope (not one of §19's listed interfaces) and confirmed to still throw in its own background thread under simulation, non-fatally (daemon thread, doesn't block `RoverBrain.start()`). |
| 20 | Testing | **PARTIAL** (2026-08-07) | `tests/test_safety.py` (15), `tests/test_odometry.py` (6), and `tests/test_sim_hardware.py` (1, subprocess-based — constructs a full `RoverBrain()` under `WILLY_SIMULATE=1`, runs `start()`→`_tick()`→a safety-gated forward command→`stop()`, asserting self-test passes and the sim `DriveBase`/`Encoders`/odometry chain actually responds) all pass. This proves the §19 root cause is fixed: `RoverBrain()` now constructs and runs a full tick off the physical Pi. Still not covered from §20's own list: AI-interface tests (malformed JSON/invalid action/timeout — `claude_client.py` untested), memory tests, navigation tests (no navigation layer exists yet, §11). |
| 21 | Logging / diagnostics | **PARTIAL** | `logsetup.py` gives every subsystem a shared rotating-file + console logger (already UTF-8-safe, with a dated comment explaining why that matters on this Pi's locale). `diagnostics.py` is a genuinely solid standalone read-only self-test (I2C scan + every sensor healthy-check + pass/fail exit code) that already matches the plan's diagnostic intent closely. What's missing: log lines are free text, not structured/machine-parseable — no consistent `EVENT=ESTOP_ACTIVE`-style tagging as §21 asks for. |
| 22 | Documentation | **PARTIAL** | `docs/` already has an actively maintained, dated, section-cited doc set (Master Engineering Package rev6.0.7, FRD v2.2, several checklists) — this practice already matches the spirit of §22 well. What's missing is the specific `IMPLEMENTED/HARDWARE REQUIRED/SIMULATION ONLY/PARTIALLY IMPLEMENTED/PLANNED` tag taxonomy per subsystem; today that status is conveyed in prose instead. |

## Summary

Out of 21 substantive sections (excluding §1/23-27, which are process/meta):
- **DONE:** 6 (§8 odometry, §9 world model milestone 1, §10 mapping/learning mode milestone 1, §11 navigation layer milestone 1, §16 retrieval modulo hardware-calibration gaps, §19 hardware abstraction for motors/sensors/arm — camera/display out of scope)
- **PARTIAL:** 8 (§4, §6, §12, §13, §18, §20, §21, §22)
- **MISSING:** 1 (§17-expected)
- **CONFLICT** (actively does what the plan says not to): 3 (§2, §3, §14, §15 — see note)
- **N/A-HW** (blocked on hardware, not code): 2 (§5, §7)

The three CONFLICT findings (§2, §3, §14/§15) all point at the same root cause: **the one existing
AI-to-motor path (`claude_client.py` via `brain.py::_stuck()`) blocks the tick thread and has no
independent safety gate or duration clamp.** This is the highest-leverage place to start — fixing
it addresses §2, §3, and half of §14 simultaneously. §19's missing mock hardware layer is the
second highest-leverage item: it blocks §20 entirely and would make every subsequent phase safer
to develop against without touching the physical rover.

## Proposed Phase 1 scope (safety only, per the plan's own §24 ordering)

1. **Non-blocking control loop**: move `ClaudeClient.decide()` off the tick thread onto a worker
   (mirroring the pattern `voice.py`/`email_client.py` already use for their own background
   threads) with a request/result queue; `_stuck()` becomes a state that polls for a result rather
   than blocking on one.
2. **Replace blocking timed moves**: turn `motors.py`'s `*_for()` helpers into deadline-based
   states driven from `_tick()`'s own 20Hz cadence instead of `time.sleep()`-blocking calls.
3. **`SafetyController.approve_motion()`**: a single authoritative gate all motor commands
   (reactive FSM, retrieval task, and the Claude-decided action alike) pass through — enforcing
   speed limit, a real duration cap, tilt, battery tier, and command-timeout in one place instead
   of duplicated per-caller checks.
4. **Watchdog**: extend `_check_health()` so a sustained IMU/encoder/current fault actually
   transitions to a safe stopped state, not just a log line.
5. **Battery**: add the missing code comment distinguishing load vs. open-circuit voltage; leave
   `battery_pct`'s linear map as display-only (already the case) but document that explicitly.
6. **E-Stop**: flagged as blocked on hardware — no software action possible until a GPIO sense pin
   is wired. Left out of Phase 1 scope pending that.

## Phase 1 status (2026-08-07, later same session): code written, NOT yet live-verified

All six items above are implemented in the working tree (uncommitted):

- New `safety.py`: `approve_motion()` is a pure function (no hardware access) doing the
  speed/duration clamp + tilt/battery-tier/obstacle checks; `SafetyController` wraps `DriveBase`
  as the only thing anything is allowed to call directly. 15 unit tests in `tests/test_safety.py`
  cover it in isolation (`venv/bin/python -m pytest tests/test_safety.py` — all pass).
- `motors.py`'s blocking `*_for()` methods removed; `claude_client.py`'s HTTP call moved onto its
  own worker thread (`request_decision()`/`poll_decision()`/`reset()`).
- `brain.py`: `_avoid()`/`_stuck()` rewritten as non-blocking, deadline-serviced states (via a
  central `self.safety.tick()` call each tick); tilt/battery/new-`SENSOR_FAULT` faults now go
  through `safety.emergency_stop()`; `_check_health()` now escalates a sustained (>1s)
  imu/encoders/current fault to a stopped `SENSOR_FAULT` state instead of only logging.
  `retrieval_task.py` takes the same `SafetyController` instead of raw `motors`.

**Not yet done — explicitly out of scope for this pass, needs the owner:**
- **Live verification on the real rover.** `willy-rover.service` on this unit has been
  crash-looping since 17:44 today (744 restarts as of this check) on a `RuntimeError: Was not
  able to enable feature` from the BNO085 IMU init in `sensors.py` — confirmed via
  `journalctl`/restart-counter timestamps to **predate this session and be unrelated to these
  changes** (crash happens during `IMU()` construction, before any FSM/safety code runs). This is
  the already-tracked I2C-bus-fault issue, not a new one — do not attempt a software fix here;
  the planned ISO154x isolator hardware fix is what addresses it. Practical consequence:
  `RoverBrain.start()`/`run()` — and therefore every line of this Phase 1 rewrite — has **never
  actually executed** on this unit yet, crash-loop or not; only `SafetyController`'s constructor
  and the pure `approve_motion()` logic have been exercised (via unit tests + a standalone smoke
  test).
- Nothing has been committed or deployed. Do the real hardware verification pass (once the IMU
  fault is fixed) before considering Phase 1 done, and before starting Phase 2.

## Update (2026-08-07, later): Phase 1 committed + deployed; §8 odometry done ahead of live verification

Phase 1 was committed (`adb9077`) and `scp`'d to the live Pi — verified byte-identical post-copy.
`willy-rover.service` was restarted but is still crash-looping on the same pre-existing IMU fault
described above (confirmed unrelated to Phase 1: crash happens in `sensors.py::IMU.__init__`,
before `RoverBrain`'s safety/motor code ever runs), even after a genuine power cycle of the base —
so Phase 1 is still **not live-verified**, unchanged from the note above. Owner directed moving on
to the next code-level item rather than continuing to chase the IMU fault this session.

§8 (odometry, see the updated row above) was implemented next. This is a deliberate exception to
this doc's own earlier advice ("before starting Phase 2"): §8 has no dependency on live rover
verification — `odometry.py`'s `integrate()` is pure math, fully covered by
`tests/test_odometry.py` off the physical hardware, and `Odometry.update()` is wired into
`brain.py`'s tick loop as a passive read (no motor consequence) that simply won't produce
meaningful numbers until the IMU/encoder fault is resolved and the rover actually drives. Phase 1
live verification is still the gating item before either is trusted in the field.

## Update (2026-08-08): §9 World Model milestone 1 implemented

Same "no live-verification dependency" exception as §8: `world_model.py` is pure Python +
SQLite, fully covered off-hardware by `tests/test_world_model.py`, and its one `brain.py` hook
(a per-tick sonar->obstacle feed) is passive, matching how odometry was wired in. See the updated
§9 row above for what shipped. §10 (mapping/learning mode) and §11 (navigation layer) are next,
in that order per §24's phase ordering — both depend on this landing first. Phase 1 live
verification is still the overall gating item before any of §8/§9/§10/§11 is trusted in the field.

## Update (2026-08-08): §10 Mapping/Learning Mode milestone 1 implemented

Same off-hardware-testable exception as §8/§9. See the updated §10 row above for what shipped and
the deliberate deviation from the original plan wording (orthogonal flag instead of a competing
top-level FSM state — avoids a real state-collision bug the literal reading would have introduced).
§11 (navigation layer) is next and last of this trio, per §24's phase ordering. Phase 1 live
verification remains the overall gating item before any of §8/§9/§10/§11 is trusted in the field.

## Update (2026-08-08): §11 Navigation Layer milestone 1 implemented — §9/§10/§11 trio complete

Same off-hardware-testable exception as §8/§9/§10. See the updated §11 row above for what shipped,
including one real bug the local-planner unit tests caught before commit (an inverted turn-
direction sign). With this, every Priority-1 world-model/mapping/navigation section the gap
analysis originally flagged **MISSING** (§9/§10/§11 — "the major missing subsystem" per the plan's
own words) now has a milestone-1 implementation, fully off-hardware unit/sim tested (58 tests
total across `tests/test_safety.py`/`test_odometry.py`/`test_sim_hardware.py`/`test_world_model.py`/
`test_mapping.py`/`test_navigation.py`). What's left before any of this is trusted in the field:
Phase 1 live verification (still blocked on the pre-existing, unrelated IMU/I2C fault tracked
across prior sessions) is the overall gating item, and §9/§10/§11's own
documented gaps (room-identification heuristic, real slip-corrected localization, obstacle-aware
global planning beyond straight-line fallback) remain open for a future milestone 2, by design —
not attempted here per each section's own "not full SLAM" instruction.
