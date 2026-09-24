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
| 2 | Non-blocking control loop | **CONFLICT** *(stale finding, kept for history — see the 2026-08-07 Phase 1 update below: fixed by commit `adb9077`, not yet live-verified)* | `brain.py::_stuck()` calls `claude_client.py::ClaudeClient.decide()` directly on the tick thread — a blocking `urllib.request.urlopen(..., timeout=8)` HTTP call. `motors.py`'s `forward_for`/`reverse_for`/`turn_*_for` also block via `time.sleep(t)`, and `_avoid()`/`_dock()`/`_stuck()` call them directly from `_tick()`. The systemd watchdog `WATCHDOG=1` is sent at the *top* of `_tick()`, before these blocking calls, so it isn't starved outright — but real Directive 1-5 safety processing (tilt/battery) is delayed for the full blocking duration each time this path fires. `claude_client.py` itself no longer exists — retired 2026-08-08, folded into `ai_provider.py::CloudAIProvider` (§14). |
| 3 | Safety gate between AI and motors | **CONFLICT** *(stale finding, kept for history — see the 2026-08-07 Phase 1 update below: fixed by commit `adb9077`, not yet live-verified)* | No `SafetyController.approve_motion()` or equivalent exists. Claude's proposed `duration` is cast to `float` and passed straight to `motors.forward_for()` etc. with **no clamp** — an unreasonable duration from the LLM is not rejected (the plan's own §20 test list calls this out explicitly: "excessive duration"). Speed *is* clamped (`motors.py` clamps to `config.SPEED_MAX` at the motor layer), and this path is only reachable after `CLAUDE_ESCALATE_AFTER=5` consecutive stuck-avoid cycles, so blast radius is contained today — but it is still the AI directly commanding motors with no independent legality check, which §3 explicitly forbids. `safety.py::SafetyController.approve_motion()` now exists and is unchanged by the §14/§15 AI-provider refactor (2026-08-08) — it remains the sole gate regardless of which AI backend answers. |
| 4 | Watchdog redesign | **DONE** *(stale finding corrected 2026-08-08 — fixed by commit `adb9077`, not yet live-verified)* | Original finding said `_check_health()` only logs and never stops motors, and that a stale cached `self.imu.tilt` could mask a real tilt fault indefinitely. Both are now false: `brain.py::_check_health()` tracks a per-subsystem `_fault_since` and returns a `sustained_fault` once any of `imu`/`encoders`/`current` (battery_adc excluded — see the code's own comment on why that path is already safe) has been unhealthy past `config.SENSOR_FAULT_GRACE_S`. `_tick()` then routes that through `self.safety.emergency_stop()` unconditionally and forces the `SENSOR_FAULT` FSM state — this is exactly the "stale tilt reading masking a real fault" case the original finding worried about, now closed: an unhealthy IMU forces a stop before its (possibly stale) `tilt` value is ever consulted for the `IMU_TILT_LIMIT` check below it. Still not a separate supervisor task/thread (unchanged from the original finding) — the check runs inline at the top of `_tick()`, same thread as everything else. |
| 5 | E-Stop integration | **N/A-HW / MISSING** | Already honestly flagged in `brain.py`'s own comments: "software has no way to observe [E-stop] — the hardware-only latching cut has no documented GPIO sense pin." This needs a wiring change (a sense pin into a GPIO) before any software can be written against it — not purely a code gap. |
| 6 | Battery voltage logic | **DONE** *(corrected 2026-08-09 — stale finding, this row was never revisited after Phase 1 shipped)* | The protection half is already done well: `config.py` has a distinct `BAT_WARN/RTH/SAFE/SHUTDOWN_V` ladder with hysteresis (`BAT_HYSTERESIS_V`), separate from the old flat low/critical pair, and `brain.py`'s `_update_bat_tier` implements one-way-worse-then-hysteresis-to-recover correctly. `battery_pct` is still a plain linear map between `BAT_SHUTDOWN_V` and `BAT_FULL_V`, but it is **display-only** (HUD/voice announcements, not any safety decision, which all key off raw voltage vs. the tier thresholds directly). The originally-flagged gap — no code comment documenting that voltage-under-load ≠ open-circuit voltage — was actually closed same-day back in Phase 1 (`config.py:117-120`, `sensors.py:146-147`); this row just never got updated to reflect it. Separately-known, still-open issue (not part of §6's own scope): `config.validate()`'s audit-P2 self-test (`52102a7`) found `BAT_FULL_V=11.39` sits *below* `BAT_WARN_V=11.4`, a calibration bug, not a §6 architecture gap — logged non-blocking at startup, owner's call to fix the number. |

## Priority 1 — Motion Foundation / World Model / Navigation / Vision

| § | Topic | Status | Finding |
|---|---|---|---|
| 7 | RP2040 encoder architecture | **N/A-HW** | No RP2040 exists on this unit per any prior session or doc. Current `Encoders` (MCP23017 polling, ~1kHz ceiling, self-documented as lossy at speed) already exposes close to the requested API shape (`counts`, `counts_per_sec`, `is_healthy`, per-wheel `stalled()`) — swapping to an RP2040 later looks like a backend swap behind the existing interface, not a rewrite, consistent with how `vision.py`/`smart_home.py` already handle their own hardware-substitution notes. |
| 8 | Odometry | **DONE** (2026-08-07) | `odometry.py` added: `Odometry.update()` (called every `brain.py` tick) converts averaged left/right wheel counts into a `Pose(x,y,heading,linear_velocity,angular_velocity,timestamp,stale)`, logged at `POSE_LOG_INTERVAL_S`. Pure-logic `integrate()` unit-tested (`tests/test_odometry.py`, 6 cases). Dead-reckoning only — no slip correction, no IMU fusion — and `WHEEL_DIAMETER_M`/`TRACK_WIDTH_M` are unconfirmed placeholder measurements (flagged in `config.py`); not yet consumed by navigation/mapping since neither exists (§9/§11). |
| 9 | World model | **DONE (milestone 1)** (2026-08-08) | `world_model.py` added: `WorldModel` class + `RobotState/Pose(delegated)/Room/Doorway/Obstacle/Object/Landmark/Route/Observation` types, exposing exactly the plan's own API (`update_observation/get_robot_pose/get_nearby_obstacles/get_room/remember_object/save/load`). Layered per §9's own instruction (obstacle map / odometry-delegated / rooms / objects-landmarks / routes), explicitly not SLAM. Own SQLite file (`world_model.db`, separate from `memory.db` per master doc §13.4), same WAL/lock/upsert convention as `memory_store.py`. Wired into `brain.py`: constructed + auto-loaded in `__init__`, a passive per-tick sonar->obstacle feed (no motor consequence), saved on shutdown. 8 unit tests (`tests/test_world_model.py`), all off-hardware. Room-identification (§10 step 6) is an intentional gap, not attempted yet — rooms/doorways/routes have no producer wired in this step (that's §10/§11). |
| 10 | Mapping / learning mode | **DONE (milestone 1)** (2026-08-08) | `mapping.py` added: `MappingSession` records vision-detected objects/landmarks into `world_model.py` while active and snapshots the map (`world_model.save()`) on `stop()`/`abort()` — persistent load already happens automatically (`WorldModel.__init__` calls `load()`, §9). Voice-triggered via new `map`/`stop_map` intents (mirrors the existing `retrieve` intent's queue-and-drain pattern in `voice.py`/`brain.py`). Deliberately **not** a top-level `brain.py` FSM state, unlike the plan's original phrasing suggested — see `mapping.py`'s module docstring: `self.mapping.active` is an orthogonal flag brain.py checks passively alongside the existing ROAM/SLOW/AVOID/STUCK dispatch (same pattern as the §9 odometry/obstacle logging), so driving during mapping is *literally* the unmodified existing reactive FSM, not a copy of it — avoids a real bug the original phrasing would have hit (routing mapping through its own top-level state and calling into `_avoid()`/`_stuck()` directly would inherit their internal `self._go('ROAM')`/`self._go('STUCK')` transitions and silently exit mapping mode the instant the path cleared). Aborted on the same Directive 1-4 preemption points as `RetrievalTask` (sensor/tilt/battery faults, shutdown). Room-identification (§10 step 6) remains an explicit, undone gap this milestone, matching the plan's own "when possible" wording. 11 tests (`tests/test_mapping.py`): pure-logic on `project_point()`/session start-stop-tick-abort with fakes, plus one full `RoverBrain()` simulation-lifecycle subprocess test. |
| 11 | Navigation layer | **DONE (milestone 1)** (2026-08-08) | `navigation.py` added: `Mission` (room name / route name / raw x,y) + `Navigator` resolving a global route (known `Route` waypoints verbatim; a `Room` target via a `networkx` shortest-path over known Room/Doorway records, falling back to a single straight-line waypoint at the target's centroid when no graph connectivity is known yet — honest, not fake obstacle-aware planning) and driving it via a local planner (bearing-to-waypoint heading correction + forward, all through `safety.py`'s existing gate, nothing new below it). Obstacle avoidance mirrors `brain.py`'s `_avoid()` reverse-then-turn pattern (same config constants) as a **self-contained copy inside `Navigator`**, not a direct call into `_avoid()` — same reasoning as §10's deviation: `_avoid()`'s own `self._go(...)` transitions are written for brain.py's top-level FSM and would corrupt whichever state calls into it. Unlike mapping, Navigator *does* own a top-level FSM state (`NAVIGATE`, brain.py's dispatch table + `_navigate()`), since driving (unlike passive observation) legitimately needs one — its own `SEEKING/AVOIDING/DONE/FAILED/ABORTED` sub-states live underneath it, same shape as `RetrievalTask`. Voice-triggered via the `go_to` intent, which was already queued by `voice.py` but never wired to an executor — now is. Aborted on the same Directive 1-4 preemption points as `RetrievalTask`/`MappingSession`. `networkx` added to `requirements.txt` (previously only a transitive dep). 16 tests (`tests/test_navigation.py`): route resolution (raw xy / named route / room-graph path / no-graph fallback / unknown mission), local-planner heading/arrival/obstacle-handoff logic with fakes, plus one full `RoverBrain()` simulation-lifecycle subprocess test. One real bug caught and fixed by the local-planner tests before commit: the initial turn-direction sign was inverted (turned right for a CCW/left bearing error) — round `heading_err>0` maps to `turn_left`, not `turn_right`, per `odometry.py`'s own CCW-positive convention. |
| 12 | YOLO / vision integration | **PARTIAL, mostly DONE** (2026-08-08) | `vision.py`'s `detect()` now returns `timestamp`/`camera_id` alongside `class/conf/bbox/frame_w/frame_h` (§12's shape). Bearing/range remain a separate `localize()` call rather than bundled onto the detection dict — a deliberate minimal-diff choice, not an oversight; `mapping.py` already calls `detect()`+`localize()` together every tick, so merging them would be a larger refactor for no behavior change. Fusion into the world model is no longer blocked (§9 landed) — `mapping.py` already does it for vision-detected objects/landmarks. Already good, unchanged: the code's own comments explicitly warn distance/bearing are heuristic, not calibrated ranging, exactly what §12 asks for. |

## Priority 1 — Memory / AI Interface / Retrieval

| § | Topic | Status | Finding |
|---|---|---|---|
| 13 | Memory architecture | **DONE (milestone 1)** (2026-08-08) | New `storage.py`: `resolve_root(env_var,default)` (env var set -> used as-is; unset -> repo-relative default, unchanged from today's behavior) backs new `config.WILLY_DATA_ROOT`/`WILLY_MAP_ROOT`/`WILLY_MEMORY_ROOT`/`WILLY_LOG_ROOT`, exactly the four names §13 names. `memory_store.py`/`world_model.py`/`logsetup.py` now root off these instead of three independent copies of the same `__file__`-relative join. `check_storage()` adds the startup availability/permission check §13 asks for, folded into `brain.py::_self_test()`'s existing INIT->IDLE gate — a bad storage mount now blocks motion the same way a missing sensor already does. **No physical RAM/SSD/SD split** — confirmed via `df`/`mount` this unit has no separate SSD/SD mount yet (master doc §13.4's boot-from-SSD migration is still pending), so all four roots currently resolve to the same microSD card; genuinely overridable via env var whenever that migration happens, with zero further code changes. Operational memory (current mission/robot state/map/active obstacles) was **not** built as a new RAM class — already satisfied by live objects (`brain.py`'s `self._state`, `self.navigator`, `self.world_model`'s in-memory layers); adding a duplicate accessor with no real consumer would be pure overhead. 8 new tests (`tests/test_storage.py`). |
| 14 | AI / LLM interface | **DONE (milestone 1)** (2026-08-08) | New `ai_provider.py`: `AIProvider` ABC (owns the non-blocking worker-thread plumbing, unchanged in shape from the old `claude_client.py`, plus a synchronous `ask_sync()` path for off-tick-thread callers) with `CloudAIProvider`/`LocalAIProvider` implementations — `claude_client.py` and `cloud_ai.py` (previously two separate clients independently hitting the same Anthropic endpoint) are fully retired, folded into one `CloudAIProvider` instance `brain.py` now shares with `voice.py`. `build_world_state()` assembles §14's exact schema (`robot: {room,pose,battery}, goal, nearby_objects, nearby_obstacles, available_routes`) from real `world_model.py` (§9) data — no longer blocked on §9 not existing. `brain.py::_stuck()` now builds its situation this way instead of a raw sensor dict; conversation history is caller-owned (threaded through each call) rather than provider-owned, so one shared provider instance can't leak STUCK's motion-decision turns into voice's unrelated free-text turns or vice versa. **No change to what actually gates motion** — `safety.py::SafetyController.approve_motion()` remains the sole authority, untouched. |
| 15 | AI confidence | **DONE (milestone 1)** (2026-08-08) | Fixed alongside §14 (same `ai_provider.py`) — `AIResult` carries `parse_success`, `intent_confidence` (the model's own self-reported `"confidence"` field, not a parse-success proxy), `action_confidence` (separately *computed*: is the specific action/duration/speed structurally sane — `None` for non-motion queries), and `safety_validation` (structural plausibility only, explicitly documented as not the real safety gate). `voice.py::_interpret_local()`'s old hardcoded `0.8`/`0.0` is gone, replaced by `result.intent_confidence`. The already-correct downstream consequence handling (low confidence -> ask for clarification, never guess) is unchanged. |
| 16 | Retrieval behavior | **DONE** (mostly) | `retrieval_task.py` already implements almost exactly the requested state list — `LOCALIZE/APPROACH/GRASP/VERIFY/DELIVER/AWAIT_CONFIRM` — as its own sub-FSM, gated correctly behind `brain.py`'s Directive 1-5 checks, with `abort()` always called externally per §27's "never decide internally" pattern. Its own comments already honestly flag the two real remaining gaps: grasp is a fixed primitive sequence, not IK (no per-joint calibration exists — §20.6 in the master doc), and hand-off confirmation is timeout-based, not tactile-sensed. Best-covered section in the whole plan; what remains is hardware calibration work, not architecture work. |

## Priority 2 / Cross-Cutting

| § | Topic | Status | Finding |
|---|---|---|---|
| 17 | Stair-climbing prep | **MISSING (expected)** | No `STAIR_*` states exist. Plan explicitly says not to build this without hardware/testing support and marks it Priority 2 lowest — absence here is correct, not a gap to close now. |
| 18 | Configuration cleanup | **DONE** (owner sign-off 2026-08-08) | Config values already carry dated calibration notes and explicit master-doc section citations (e.g. a 2026-08-02 GPIO pin fix, a 2026-08-02 battery-divider recalibration, per-value "confirmed/unconfirmed" flags). Credentials are correctly kept out of `config.py` (env var names/paths only). The one item needing explicit owner confirmation — `ENABLE_CLOUD_AI=True`/`ENABLE_EMAIL=True` both default-on — was put to the owner directly on 2026-08-08: **both confirmed to stay `True`**, no code change. This closes the last open item in §18. |
| 19 | Hardware abstraction | **DONE** (2026-08-07) for motors/sensors/arm; camera/display out of scope | `config.SIMULATE_HARDWARE` (env var `WILLY_SIMULATE=1`) gates every real I2C/GPIO open in `motors.py`/`arm.py`/`sensors.py`/`brain.py`'s own I2C self-test scan, both the module-level conditional imports and each class's construction/`_update()`. New `hw_sim.py` holds the two shared mocks (`SimMotor`, `SimServoBank`) that satisfy `DriveBase`/`Steering`/`Arm`'s existing interfaces unchanged — no caller-visible API change. `ObjectDetector` (`vision.py`) was already safely gated behind `ENABLE_OBJECT_RETRIEVAL` and didn't need this. `display.py`'s pygame/Wayland init is **not** covered — out of scope (not one of §19's listed interfaces) and confirmed to still throw in its own background thread under simulation, non-fatally (daemon thread, doesn't block `RoverBrain.start()`). |
| 20 | Testing | **DONE (milestone 1)** (2026-08-08) | 107 tests across 12 files, all off-hardware. Every item on §20's own checklist now has coverage except E-Stop (**N/A-HW**, no GPIO sense pin wired — correctly untestable) and encoder rollover (no rollover case exists — `Encoders`' counts are unbounded Python ints, not read from a fixed-width register, per `sensors.py`'s own comment). This update closed the three real gaps found by auditing that checklist: (1) `SafetyController` itself (not just the pure `approve_motion()`) had zero tests — `tests/test_safety_controller.py` (10) now covers command timeout/cancellation, mid-flight obstacle abort, `emergency_stop()`. (2) Corrupted-database handling wasn't just untested, it was **unhandled** — `MemoryStore`/`WorldModel.__init__` would raise `sqlite3.DatabaseError` straight out of `RoverBrain.__init__`, crashing the whole service on a corrupted `memory.db`/`world_model.db` (a real failure mode after an unclean shutdown). Both now catch it, move the corrupted file aside (never deleted), and start fresh — verified against a real garbage file before committing, not just the unit tests (`tests/test_memory_store.py`, `tests/test_world_model.py`). (3) AI timeout was only accidentally covered by a generic exception handler — now pinned down explicitly (`tests/test_ai_provider.py`). Also added: battery-tier hysteresis (`tests/test_brain_battery.py`) — real safety-relevant logic that had only ever been exercised indirectly through full sim construction. |
| 21 | Logging / diagnostics | **DONE (milestone 1)** (2026-08-08) | New `logsetup.log_event(logger,event,severity='info',**fields)`: the exact `EVENT=<NAME>` tag §21 asks for (`grep 'EVENT=IMU_FAULT' willy.log`-able), applied at real fault/abort call sites — `brain.py::_check_health()`'s per-subsystem transitions (`IMU_FAULT`/`ENCODERS_FAULT`/`CURRENT_FAULT`/`BATTERY_ADC_FAULT`), all three battery-tier branches (`LOW_BATTERY`, tagged `safe_mode`/`shutdown`/`return_to_home`), `safety.py`'s mid-flight obstacle abort (`OBSTACLE_STOP`), `navigation.py`'s `Navigator.abort()` (`NAVIGATION_ABORT`), and `ai_provider.py`'s `CloudAIProvider._call()` specifically when the exception is a real `TimeoutError` (`AI_TIMEOUT`, not every failure — offline/quota errors stay a plain log line, not mislabeled as a timeout). Deliberately **not** a wholesale reformat into JSON — every existing free-text `log.info`/`log.warning` call elsewhere is unchanged; a full structured-logging rewrite across ~15 files would be a much larger, riskier change for no benefit proportional to the risk. `ESTOP_ACTIVE` stays untagged (**N/A-HW**, no GPIO sense pin exists to observe it). `WATCHDOG_FAULT` stays untagged too — architecturally can't self-log: by the time systemd's watchdog fires, the process is being killed/restarted, not running code. `MOTOR_FAULT` has no real call site to tag — `Encoders.stalled()` exists but is never actually called anywhere in production code (confirmed via repo-wide grep), and no overcurrent trip threshold exists per `config.py`'s own long-standing comment; fabricating a call site for an example event with no underlying detection would be worse than leaving it out. "Important safety events must be persistent" was already satisfied by the existing rotating file handler (FR-1100-003) — no new persistence mechanism was needed. 3 new tests (`tests/test_logsetup.py`). `diagnostics.py`'s existing solid self-test is unchanged. |
| 22 | Documentation | **DONE (milestone 1)** (2026-08-08) | New `docs/WildWilly_Subsystem_Status.md`: the exact `IMPLEMENTED/HARDWARE REQUIRED/SIMULATION ONLY/PARTIALLY IMPLEMENTED/PLANNED` tag taxonomy §22 names, applied per Python module (not per plan section — a different, complementary organization from this gap analysis doc). Includes a small ASCII architecture diagram of the real, currently-wired AI/World Model/Navigation/Safety/Hardware data flow (not aspirational), and — the part of §22 that matters most given this session's scope — an explicit **capability caution** reiterating "do not describe this robot as having SLAM, autonomous house navigation, persistent spatial memory, or stair climbing" now that `world_model.py`/`mapping.py`/`navigation.py` exist and could easily be oversold by anyone skimming commit messages without reading the "milestone 1, not SLAM" caveats already embedded in each module's own docstring. `docs/`'s existing actively-maintained, dated, section-cited practice (Master Engineering Package, FRD v2.2, checklists) was already good and is unchanged. |

## Summary

Out of 21 substantive sections (excluding §1/23-27, which are process/meta):
- **DONE:** 15 (§4 watchdog — corrected 2026-08-08, was mismarked PARTIAL, §6 battery voltage logic — corrected 2026-08-09, was mismarked PARTIAL, §8 odometry, §9 world model milestone 1, §10 mapping/learning mode milestone 1, §11 navigation layer milestone 1, §13 memory architecture milestone 1, §14 AI/LLM interface milestone 1, §15 AI confidence milestone 1, §16 retrieval modulo hardware-calibration gaps, §18 configuration cleanup — owner sign-off 2026-08-08, §19 hardware abstraction for motors/sensors/arm — camera/display out of scope, §20 testing milestone 1, §21 structured logging milestone 1, §22 documentation milestone 1)
- **PARTIAL:** 1 (§12)
- **MISSING:** 1 (§17-expected)
- **CONFLICT** (actively does what the plan says not to): 2 (§2, §3 — see note)
- **N/A-HW** (blocked on hardware, not code): 2 (§5, §7)

*(Historical, 2026-08-07)* The three original CONFLICT findings (§2, §3, §14/§15) all pointed at
the same root cause: the one existing AI-to-motor path (`claude_client.py` via `brain.py::_stuck()`)
blocked the tick thread and had no independent safety gate or duration clamp. Phase 1 (§2/§3) and
now §14/§15 (2026-08-08, `ai_provider.py`) have both landed — §2/§3 remain listed as CONFLICT only
because Phase 1 is still not *live-verified* (see below), not because the code itself still
conflicts with the plan.

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

## Update (2026-08-08, same day): Phase 5 begun — §12 (vision shape) and §14/§15 (AIProvider
## unification) implemented

Continuing per §24's phase order (Phase 1 Safety → Phase 2 Motion foundation → Phase 3 World
model → Phase 4 Navigation, all now done → **Phase 5 Vision/AI**, begun this update):

- **§12** (see updated row above): `vision.py::ObjectDetector.detect()` now returns
  `timestamp`/`camera_id` per detection.
- **§14/§15** (see updated rows above, and the retired-`claude_client.py`/`safety.py`-unchanged
  notes added to the §2/§3 rows): new `ai_provider.py` — `AIProvider` ABC + `AIResult` +
  `CloudAIProvider`/`LocalAIProvider`, `build_world_state()` implementing §14's schema from real
  `world_model.py` data. `claude_client.py` and `cloud_ai.py` fully deleted, not shimmed —
  `brain.py` and `voice.py` now share one `CloudAIProvider` instance instead of two independent,
  duplicated Anthropic clients. `voice.py`'s old hardcoded `0.8`/`0.0` "confidence" is gone,
  replaced by a real model-self-reported `intent_confidence` plus a separately-computed
  `action_confidence`. **`safety.py::SafetyController.approve_motion()` was not touched** — it
  remains the sole authority over what the rover is allowed to do, unchanged by this refactor.
  25 new tests (`tests/test_ai_provider.py`), all off-network (HTTP calls faked/never reached in
  any automated test — no live Anthropic API call is made by this test suite).

Tally now DONE:8, PARTIAL:8, MISSING:1 (§17-expected only), CONFLICT:2 (§2/§3, both stale findings
— see the notes added to those rows), N/A-HW:2 (§5/§7). Remaining unstarted work in the plan:
§13 (memory tiering, currently PARTIAL), §17 (stair-climbing prep, intentionally not started),
§18/§21/§22 (config/logging/docs cleanup, PARTIAL), and Phase 6/7 (§13/§17 overlap — memory
architecture, advanced retrieval/requester-navigation behavior). Phase 1 through §15 remains
**not live-verified** — unchanged gating item, still blocked on the pre-existing IMU/I2C fault.

## Update (2026-08-08, same day): Phase 6 — §13 Memory Architecture milestone 1 implemented

Continuing per §24's phase order (Phase 6 — Memory, after Phase 5 Vision/AI):

New `storage.py` (see updated §13 row above) gives the four env-var-configurable roots §13 names
(`WILLY_DATA_ROOT`/`MAP_ROOT`/`MEMORY_ROOT`/`LOG_ROOT`), a startup availability/permission check
folded into `brain.py::_self_test()`'s existing gate, and unifies three previously-independent
copies of the same `__file__`-relative path-join logic (`memory_store.py`/`world_model.py`/
`logsetup.py`). Confirmed via `df`/`mount` this unit has no physical SSD/SD split yet (master doc
§13.4's boot-from-SSD migration is still pending) — all four roots resolve to today's exact
locations by default, verified unchanged
(`WILLY_DATA_ROOT`/`WILLY_MAP_ROOT`/`WILLY_MEMORY_ROOT`=`/home/hhimmel/rover`,
`WILLY_LOG_ROOT`=`/home/hhimmel/rover/logs`). 8 new tests (`tests/test_storage.py`).

Tally now DONE:9, PARTIAL:7, MISSING:1 (§17-expected), CONFLICT:2 (§2/§3, stale), N/A-HW:2 (§5/§7).
Per §24, Phases 1-6 are now all code-complete at milestone-1 scope. Remaining unstarted: §17
(stair-climbing prep, intentionally deferred), §18/§20/§21/§22 (config/testing/logging/docs
cleanup, PARTIAL), and Phase 7 (advanced retrieval/requester-navigation/stair autonomy). Nothing
through §13 is **live-verified** — same standing gate, still blocked on the pre-existing IMU/I2C
fault.

## Update (2026-08-08, same day): §20 Testing Requirements milestone 1 — three real gaps closed

Audited §20's own checklist against the (by then) 91-test suite and found three genuine blind
spots rather than just thin coverage (see the updated §20 row above for full detail): zero tests
on `SafetyController` itself (only the pure `approve_motion()` function was covered), corrupted-
database handling that was **unhandled, not just untested** (a corrupted `memory.db`/
`world_model.db` would crash `RoverBrain.__init__` outright — fixed, verified against a real
garbage file before committing, not just unit-test assertions), and AI timeout only accidentally
covered by a generic exception handler. Also added battery-tier hysteresis tests — real
safety-relevant logic that had never been directly unit tested. 16 new tests across 4 files
(`test_safety_controller.py`, `test_memory_store.py` — new, `test_world_model.py`,
`test_ai_provider.py`, `test_brain_battery.py` — new). 107 tests total, all pass.

Tally now DONE:10, PARTIAL:6, MISSING:1 (§17-expected), CONFLICT:2 (§2/§3, stale), N/A-HW:2
(§5/§7). Remaining: §17 (intentionally deferred, needs hardware), §18 (config audit — mostly
owner-confirmation work, not code), §21 (structured `EVENT=...` logging tags), §22 (doc status
taxonomy), Phase 7 (advanced behavior — hardware-calibration gaps, not architecture). Nothing
through §20 is **live-verified** — same standing gate, still blocked on the pre-existing IMU/I2C
fault. That gap is now seven phases/sections wide.

## Update (2026-08-08, same day): §21 (structured logging) and §22 (documentation) milestone 1 —
## everything code-shaped in this plan is now done except §17/§18/Phase 7

§21 (`logsetup.log_event()`, commit `50ba669`) and §22 (`docs/WildWilly_Subsystem_Status.md`, this
commit) both landed — see their updated rows above. Tally now **DONE:12, PARTIAL:4 (§4/§6/§12/§18),
MISSING:1 (§17), CONFLICT:2 (§2/§3, stale), N/A-HW:2 (§5/§7)**.

What's left is deliberately not being started, for reasons already documented rather than by
oversight: §17 (stair-climbing) needs hardware/testing support the plan itself says not to build
without; §18 (config audit) is mostly an owner-confirmation checklist (verify I2C addresses/GPIO/
thresholds against the engineering package), not a code change; Phase 7's remaining items
(`retrieval_task.py` improvements, requester navigation) are hardware-calibration gaps per §16's
own notes (no per-joint IK, no tactile hand-off sensor), not architecture work a code session can
close. §4/§6/§12 stay PARTIAL for their own previously-documented reasons (watchdog doesn't yet
stop motors on every fault class; `battery_pct`'s load-vs-open-circuit caveat; vision detection
shape's bearing/range still a separate `localize()` call).

**The live-verification gap is unchanged and is now the only thing standing between "this plan is
code-complete" and "this plan is actually trustworthy."** 110 tests pass, all off-hardware. Nothing
since Phase 1 has run a real `RoverBrain.run()` on the physical rover — see
`docs/WildWilly_Subsystem_Status.md`'s standing note, and update it (not just this doc) the moment
that changes.

## Update (2026-08-08, same day): §4 corrected (stale, not fixed by new code); IMU RST pin wired up

Auditing §4's row against the current `brain.py` found it was simply wrong, not stale-but-still-true
like §2/§3 — `_check_health()`/`SENSOR_FAULT` already does exactly what the row said was missing
(commit `adb9077`, 2026-08-07). Corrected to **DONE** above; tally is now DONE:13/PARTIAL:3.

Separately: owner confirmed the BNO085's RST line is wired to MCP23017 port B bit 4 (previously
the master doc only said "spare pin", no bit number). `sensors.py::IMU.__init__` now builds a real
`digitalio`-style reset pin via `adafruit_mcp230xx` (already a dependency, previously unused) and
passes it to `BNO08X_I2C(reset=...)` — `adafruit_bno08x`'s own `initialize()` calls `hard_reset()`
before every `soft_reset()`/`_check_id()` retry, so this was a real no-op before, not just a missing
optimization as the old code comment claimed. Verified live on the actual Pi (`Willie`, this unit
*is* the deployment target — see `reference_rover_project` memory): `IMU()` and `Encoders()`
constructed together in `brain.py`'s exact init order, both report healthy, no register-write
interference on the shared MCP23017 chip. This is a real fix to a previously-open lead, not part of
the plan's own numbered sections — logged here since it's adjacent to §4/§8.2 hardware notes.

## Update (2026-08-08, same day): §18 closed; first-ever live `RoverBrain.run()`; one live bug found + fixed

Owner confirmed both `ENABLE_CLOUD_AI`/`ENABLE_EMAIL` stay `True` — §18 moved to **DONE** above
(tally now DONE:14, PARTIAL:2 (§6,§12), MISSING:1 (§17), CONFLICT:2 (§2/§3, stale), N/A-HW:2
(§5/§7)). Only §17 (correctly hardware-gated), §6/§12 (documented, low-stakes partials), and Phase
7 (hardware-calibration gaps per §16's own notes) remain — nothing else code-shaped is open.

Separately, and much bigger: the owner reconnected VCC to the arm's PCA9685 board (the physical
root cause of the `0x43` "No I2C device" crash that had blocked every restart since 08-07 —
confirmed by `i2cdetect`: `0x43` went from silent to acking, nothing else changed). `willy-rover.
service` came up **`active (running)`** for the first time since Phase 1 shipped — the
live-verification gap flagged as "seven phases wide" earlier today is now closed for
construction/init at least; a real `RoverBrain.run()` is executing on hardware.

With the base intentionally powered off, `battery_volts` correctly read ~3.17V (confirmed by
owner: expected, not a sensor fault) and the battery-shutdown safety path engaged exactly as
designed — first live exercise of that path. It surfaced one real bug: `safety.py::
emergency_stop()`'s own `log.warning()` had no throttle, and `brain.py` calls it every tick while
a fault persists, so the log filled at ~20Hz indefinitely (same bug class as `516d1ec`'s
`memory.save_all_now()` fix, just for a log line, and missed by that pass since it lives in
`safety.py` not `brain.py`). Fixed same session: throttled to `ESTOP_LOG_INTERVAL_S` (5s) via a
last-logged timestamp, `brake()` itself untouched — still fires every call. 2 new tests
(`tests/test_safety_controller.py`).

Owner also asked about adding a new low-current emergency-stop trigger on the Pi INA260 rail
(current, not the voltage the master doc's §5.5 undervoltage row describes) — explicitly deferred
("disable emergency stop for now", clarified via AskUserQuestion to mean *skip this new feature*,
not disable the real `SafetyController.emergency_stop()` safety gate). Not built this session;
`CurrentMonitor.is_healthy` remains read-recency-only, unchanged. Needs before attempting: which
rail(s), a real amp threshold (no numeric overcurrent value exists anywhere in the docs per
`sensors.py`'s own long-standing comment), and whether it should mean the harder immediate
`emergency_stop()` brake or the master doc's distinct SAFE_MODE behavior.

**How to apply now:** this is the first time any of Phase 1 through §22's code has run live —
init, the safety FSM, and the battery-shutdown path are now real-hardware-verified, not just
sim-tested. Motion itself (forward/reverse/turn through `SafetyController.request()`, `NAVIGATE`,
retrieval, mapping) is still **not** live-verified — nothing in this session commanded the drive
base. That's the next real milestone once the battery/base situation allows it.
