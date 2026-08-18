# WildWilly Autonomous Rover

## Software Design — As-Built

**Revision 1.0 · Current Implementation**

---

## Document Control

| Field | Value |
|-------|-------|
| Project | WildWilly Autonomous Rover |
| Document | Software Design — as-built implementation |
| Revision | 1.0 |
| Date | 2026-08-18 |
| Owner | Howard Himmel |
| Status | Implemented and off-hardware tested; not live-verified |
| Supersedes | Nothing. First revision. |
| Companions | Master Hardware Design v2.0; Functional Requirements v3.1 |

**Scope of this document.** This describes the software as it is currently
written, in the repository `hdhimmel/willy-rover`. It describes structure and
intent, not aspiration. Where a subsystem is stubbed, disabled or approximate,
it is recorded as such rather than described as if complete.

**What "as-built" means here.** Every module listed exists and imports. The
144-test suite passes off hardware. None of it has been proven against the
assembled rover. Those are three different claims and this document keeps them
separate.

---

## 1. System Summary

| Property | Value |
|----------|-------|
| Host | Raspberry Pi 5 (8GB), Debian 13 Trixie, Python 3.13.5 |
| Boot | 1TB SSD |
| Entry point | `main.py` → `RoverBrain().run()` |
| Process management | systemd unit `willy-rover.service`, `Restart=on-failure` |
| Modules | 26 Python files at repository root |
| Source size | ~4,160 lines |
| Tests | 144, across 17 files, all passing off hardware |
| Simulation mode | `WILLY_SIMULATE=1` gates every real I²C and GPIO open |

### 1.1 Module inventory

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `brain.py` | 720 | Top-level FSM, tick loop, directive arbitration |
| `config.py` | 347 | All tunables, addresses, pin maps; `validate()` self-check |
| `voice.py` | 344 | Wake word, STT, intent parsing, TTS |
| `sensors.py` | 320 | Sonar, IMU, ADC, encoders, current monitors |
| `world_model.py` | 282 | Persistent spatial model — obstacles, rooms, objects, routes |
| `ai_provider.py` | 272 | Unified cloud/local LLM abstraction |
| `display.py` | 197 | Face rendering and status overlay |
| `email_client.py` | 184 | IMAP/SMTP with allowlist and confirm gates |
| `retrieval_task.py` | 181 | Object retrieval sub-FSM |
| `memory_store.py` | 173 | Conversational and episodic memory (SQLite) |
| `navigation.py` | 165 | Route resolution and local planning |
| `safety.py` | 124 | The motion authority — sole gate to the motors |
| `pursuit_task.py` | 101 | Come-here and follow-me sub-FSM |
| `motors.py` | 93 | Drive base and steering primitives |
| `vision.py` | 84 | Object detection and bearing/range heuristics |
| `smart_home.py` | 82 | Home Assistant REST client |
| `odometry.py` | 74 | Dead-reckoning pose integration |
| `mapping.py` | 68 | Learning-mode map recording session |
| `diagnostics.py` | 64 | Standalone read-only self-test |
| `privacy.py` | 59 | Mic/camera disable flag |
| `arm.py` | 59 | Arm servo primitives |
| `storage.py` | 53 | Data root resolution and availability check |
| `logsetup.py` | 42 | Logging config and `log_event` structured tags |
| `arm_jog.py` | 39 | Interactive bench-calibration jog tool |
| `hw_sim.py` | 22 | Simulation mocks for motors and servo banks |
| `main.py` | 9 | Entry point and signal routing |

---

## 2. Control Architecture

### 2.1 Layering

The design has one non-negotiable structural rule: **nothing calls the motors
except through `safety.py`.** Not the reactive FSM, not a task sub-machine, not
the AI. The test `tests/test_no_direct_drive_bypass.py` exists to enforce this
as a property of the codebase rather than a convention.

```
  Deliberative layer      AI provider, vision, world model, navigation planning
  (variable latency)      Proposes intent. Never authorises motion.
          │
          ▼
  Arbitration layer       brain.py::_tick() — Directives 1-5 checked in order
  (fixed 20Hz tick)       before any Directive 6 behaviour is dispatched
          │
          ▼
  Safety layer            safety.py::SafetyController — the single authority.
  (pure decision fn)      Clamps speed and duration, or rejects outright.
          │
          ▼
  Reflex inputs           Sonar, encoders, IMU, current monitors.
  (deterministic)         Feed the arbitration layer directly. Never wait on vision.
          │
          ▼
  Hardware layer          motors.py, arm.py, sensors.py — or hw_sim.py mocks
```

The separation between the deliberative and reflex layers is the same rule
carried in Master Hardware Design §12 rules 18–19. An obstacle stop must never
depend on a detection frame arriving.

### 2.2 The safety gate

`safety.py` splits into two deliberately separate pieces:

**`approve_motion(...)` — a pure function.** No hardware access, no state.
Takes an action, optional speed and duration, plus the current context
(`front_cm`, `tilt_deg`, `bat_tier`, `motion_enabled`) as explicit arguments.
Returns either an `ApprovedMotion` with speed and duration clamped to
configured limits, or a `Rejected` carrying a reason string. Because it is
pure, it is exhaustively unit-testable without a rover.

Rejection conditions, in the order checked:

1. Motion not enabled — the startup self-test failed.
2. Action not in the recognised continuous set.
3. Tilt exceeds `IMU_TILT_LIMIT`.
4. Battery tier is `safe` or `shutdown`.
5. Action is `forward` and the front sonar is inside `DIST_STOP`.

**`SafetyController` — the stateful wrapper.** Caches the context once per
tick (so individual call sites do not each thread sensor readings through),
executes approved motion, and services timed moves non-blockingly. A
`duration=None` request is a continuous command the caller re-issues each tick;
a `duration=<n>` request starts a timed move serviced by `tick()` rather than
sleeping. This is what replaced the earlier blocking `motors.*_for()` calls.

`SafetyController` has exactly one caller thread — the tick thread. Voice's
`stop_requested` is an `Event` consumed at the top of `_tick()` rather than a
direct call, specifically to preserve that invariant.

### 2.3 The tick loop

`RoverBrain.run()` is a plain loop: tick, record duration, sleep 50ms. Nominal
cadence is therefore about 20Hz.

Order of operations within `_tick()`:

1. **Voice stop** — checked before any directive gating. Aborts every active
   task sub-machine and calls `emergency_stop()`. This is the only place the
   flag is cleared.
2. **Watchdog notify** — `WATCHDOG=1` to systemd.
3. **Health check** — per-subsystem `_fault_since` tracking; a subsystem
   unhealthy beyond `SENSOR_FAULT_GRACE_S` returns a sustained fault, which
   routes unconditionally through `emergency_stop()` and forces the
   `SENSOR_FAULT` state. This runs *before* any sensor value is consulted, so
   a stale IMU reading cannot mask a real tilt fault.
4. **Directive checks** — tilt, then battery tier, in that order.
5. **Safety context update** — cached into `SafetyController`.
6. **State dispatch** — the Directive 6 layer.

Tick duration is recorded and an overrun past `TICK_OVERRUN_THRESHOLD_S`
(0.15s) is logged as a `TICK_OVERRUN` event with a running count. See §8 for
the inconsistency between this threshold and the systemd watchdog interval.

---

## 3. State Machine

### 3.1 Top-level states

`brain.py` dispatches on fifteen states through a table in `_tick()`.

| State | Class | Entered when |
|-------|-------|--------------|
| `INIT` | Startup | Construction, before self-test |
| `IDLE` | Nominal | Self-test passed; nothing to do |
| `ROAM` | Nominal | Idle timeout elapsed, or path cleared |
| `SLOW` | Nominal | Front distance inside `DIST_SLOW` |
| `AVOID` | Reactive | Front distance inside `DIST_STOP` |
| `STUCK` | Reactive | `CLAUDE_ESCALATE_AFTER` consecutive stuck-avoid cycles |
| `WARN` | Fault | Tilt past `IMU_TILT_WARN` |
| `TILT_FAULT` | Fault | Tilt past `IMU_TILT_LIMIT` |
| `SENSOR_FAULT` | Fault | Sustained subsystem fault past grace period |
| `SAFE_MODE` | Fault | Battery below `BAT_SAFE_V` |
| `SHUTDOWN` | Terminal | Battery below `BAT_SHUTDOWN_V`, or voice-confirmed |
| `DOCK` | Task | Battery below `BAT_RTH_V` |
| `MANUAL` | Task | Voice-issued manual drive command |
| `NAVIGATE` | Task | `go_to` intent, delegates to `navigation.py` |
| `RETRIEVE` | Task | `retrieve` intent, delegates to `retrieval_task.py` |
| `PURSUE` | Task | `come_here`/`follow` intent, delegates to `pursuit_task.py` |

### 3.2 Sub-state machines

Three task modules own their own internal state and run *underneath* a
top-level state rather than replacing it:

- `RetrievalTask` — `LOCALIZE / APPROACH / GRASP / VERIFY / DELIVER / AWAIT_CONFIRM`
- `PursuitTask` — `LOCALIZE / APPROACH / FOLLOWING`
- `Navigator` — `SEEKING / AVOIDING / DONE / FAILED / ABORTED`

Each exposes `abort()`, called externally by `brain.py` when any Directive 1–4
preemption fires. None of them re-checks the directives independently — that
would duplicate the arbitration and risk divergence. The contract is: the task
never decides whether it is safe to continue; `brain.py` tells it to stop.

### 3.3 Two deliberate deviations from a naive FSM design

**Mapping is not a top-level state.** `MappingSession.active` is an orthogonal
flag checked passively alongside the normal ROAM/SLOW/AVOID dispatch. Driving
while mapping is therefore *literally* the unmodified reactive FSM, not a copy
of it. Making mapping its own state would have meant calling into `_avoid()`
and `_stuck()`, which carry their own `_go('ROAM')` transitions and would
silently exit mapping mode the instant the path cleared.

**Navigation's obstacle avoidance is a self-contained copy, not a call into
`_avoid()`.** Same reasoning: `_avoid()`'s internal state transitions are
written for the top-level FSM and would corrupt whichever state called into it.
The duplication is intentional and the constants are shared.

`Navigator` *does* own a top-level state, unlike mapping, because driving
legitimately needs one where passive observation does not.

---

## 4. Startup and Shutdown

### 4.1 Startup sequence

1. `RoverBrain.__init__` constructs every subsystem. Note that `motors.py` and
   `arm.py` construction calls `PCA9685.reset()`, which clears the MODE1
   ALLCALL bit — this is why 0x70 legitimately stops answering before the
   self-test runs, and why it is excluded from the expected-address set.
2. `start()` brings up display, sensors, encoders, current monitors; centres
   steering and arm; starts voice and email background threads.
3. `_self_test()` runs the I²C scan against `_EXPECTED_I2C` (ten addresses,
   0x70 deliberately excluded), plus `config.validate()` and
   `storage.check_storage()`.
4. `_motion_enabled` is set from the self-test result. It gates every call into
   `approve_motion()`. This is FR-100-004.
5. On pass: `READY=1` to systemd, state to `IDLE`. On fail: motion stays
   disabled, the failure reason is logged and shown on the display, and the
   process keeps running in an observable failed state rather than exiting.

Voice and email start regardless of self-test outcome. Neither can move the
rover: voice queues intents for `_tick()` to gate, and email never acts
autonomously.

### 4.2 Shutdown

`main.py` routes SIGTERM through the same `KeyboardInterrupt` path as SIGINT,
so systemd stop and restart both run `RoverBrain.stop()` cleanup rather than
dying mid-tick. `stop()` calls `emergency_stop()`, saves memory and world
model, and stops every background thread.

Voice-commanded shutdown (FR-900-005) is confirm-gated: a pending flag with a
deadline, dispatched outside the normal state table.

`display.py` sets `SDL_NO_SIGNAL_HANDLERS=1` because SDL otherwise installs
process-wide SIGINT/SIGTERM handlers that translate signals into an `SDL_QUIT`
event consumed only by its own event loop — which silently ate shutdown signals
before `main.py` ever saw them.

---

## 5. Data and Persistence

Four data roots, resolved by `storage.resolve_root()`: if the environment
variable is set it is used as-is; if unset, a repository-relative default. The
names are `WILLY_DATA_ROOT`, `WILLY_MAP_ROOT`, `WILLY_MEMORY_ROOT`,
`WILLY_LOG_ROOT`.

All four currently resolve to the same volume. The split exists so that a
future RAM/SSD/SD separation is a configuration change rather than a code
change.

Two separate SQLite databases, both WAL-mode:

| Database | Module | Contents |
|----------|--------|----------|
| `memory.db` | `memory_store.py` | Conversational and episodic memory |
| `world_model.db` | `world_model.py` | Obstacles, rooms, doorways, objects, landmarks, routes |

**Corruption handling.** Both `__init__` paths catch `sqlite3.DatabaseError`,
move the corrupted file aside — never delete it — and start fresh. Without
this, a corrupted database after an unclean shutdown raised straight out of
`RoverBrain.__init__` and crashed the service on every restart. This was
verified against a real garbage file, not only unit tests.

`storage.check_storage()` is folded into the startup self-test, so a bad mount
blocks motion the same way a missing sensor does.

---

## 6. AI Integration

### 6.1 Provider abstraction

`ai_provider.py` presents one `AIProvider` ABC with `CloudAIProvider` and
`LocalAIProvider` implementations. It replaced three separate call sites: two
independent clients POSTing to the same endpoint with duplicated transport
code, and a bare `llama_cpp.Llama` instance inlined in `voice.py`.

One `CloudAIProvider` instance is shared between `brain.py`'s STUCK-state
motion decisions and `voice.py`'s free-text fallback. Conversation history is
**caller-owned** and threaded through each call rather than held by the
provider, so one shared instance cannot leak STUCK's motion turns into voice's
unrelated turns.

### 6.2 Confidence is four separate signals

`AIResult` deliberately refuses to collapse these:

| Field | Meaning |
|-------|---------|
| `parse_success` | Did the response structurally validate against the expected schema |
| `intent_confidence` | The model's own self-reported confidence, asked for by the prompt |
| `action_confidence` | Separately *computed* — is the action/duration/speed structurally sane. `None` for non-motion queries |
| `safety_validation` | Structural plausibility only |

`safety_validation` is explicitly **not** the safety gate.
`SafetyController.approve_motion()` remains the sole authority and is untouched
by any of this. The named anti-pattern this design avoids is using "the JSON
parsed" as a proxy for "the model was confident".

### 6.3 Where the AI can and cannot act

The AI is reachable from exactly one motion path: the `STUCK` state, entered
only after `CLAUDE_ESCALATE_AFTER` consecutive failed avoid cycles. Whatever it
proposes goes through `approve_motion()` like any other request, with speed
clamped to `SPEED_MAX` and duration to `MAX_COMMAND_DURATION_S`.

Everywhere else the AI is advisory: voice intent interpretation, free-text
response, world-state summarisation.

---

## 7. Perception and the Accelerator

`vision.py`'s `ObjectDetector` is **CPU-only YOLOv8** with
`ENABLE_OBJECT_RETRIEVAL=False`. The AI HAT+ 2 is PCIe-bonded and enumerating
(Master Hardware Design §5.2) but is not yet in the software path.

`detect()` returns class, confidence, bounding box, frame dimensions, timestamp
and camera id. Bearing and range come from a separate `localize()` call and are
documented in-code as heuristic, not calibrated ranging.

When the accelerator is integrated, the constraint from Master Hardware Design
§12 rule 18 governs: it feeds `world_model.py` for planning and classification
only. It does not gate a stop.

---

## 8. Known Gaps

These are recorded rather than described as working. Each is flagged in the
implementing code itself.

**S-1 — E-stop is invisible to software.** No GPIO sense pin exists. Directive
1 is enforced physically but has no representation in the control loop, cannot
be logged, and FR-300-003's post-E-stop reset gate cannot be implemented
*for E-stop specifically* — this needs a wiring change first.

The reset-gate *mechanism* itself is no longer blocked on that wiring, though.
Owner decision 2026-08-18: a touchscreen "TAP TO RESUME" button, applied now
to `TILT_FAULT`/`SENSOR_FAULT`/`STALL_FAULT` — all three stop auto-resuming
the instant their condition clears and instead keep braking until
`display.py`'s new button is tapped (`brain.py::_await_reset_or_resume()`,
`display.py`'s `_reset_event`/`reset_tapped()`). The same mechanism will
gate E-stop once the sense pin exists; this is not a placeholder built ahead
of the hardware, it's a real behavior change for the three faults that
already fire today. `tests/test_brain_reset_gate.py` covers the brain.py-side
logic off-hardware; the touchscreen's own tap detection needs the physical
5" DSI panel (Master Hardware Design v2.0 §15.3) to verify.

**S-2 — Encoder polling under-samples at speed.** *Decision made 2026-08-18:
interrupt-driven decode*, over a dedicated counter or accepting stall-only.
`Encoders` now configures the MCP23017's `IOCON.MIRROR`/`INTCON`/`GPINTEN`
registers and registers a `GPIO.add_event_detect()` callback on
`config.ENCODER_INT_PIN`, so a real quadrature edge triggers an immediate
read instead of waiting for the next scheduled poll — this closes the
"multiple edges collapse into one polling window" failure mode specifically.
It is not a claim that every edge at the full 8.5kHz/channel figure is now
captured: the interrupt only changes *when* a read happens, not how long one
I2C transaction takes, and that transaction cost is what set the ~1kHz
ceiling in the first place. **Hardware prerequisite, not yet done**: the
MCP23017's INTA pin needs a physical wire to the Pi GPIO named in
`config.ENCODER_INT_PIN` (currently GP7) — until then this code path simply
never fires and behavior is unchanged from before. `_loop()`'s own poll
dropped from ~1kHz to a 0.1s heartbeat (only needed now to keep
`is_healthy`/`counts_per_sec` fresh while stationary, not for decode
accuracy). None of this is live-verified — only checked for syntax
correctness and unchanged `WILLY_SIMULATE=1` behavior off-hardware.
Bench-confirm `ENCODER_COUNTS_PER_REV` before acting on the arithmetic — it is
taken from the motor listing, not measured.

**S-3 — Odometry rests on two unmeasured constants.** `WHEEL_DIAMETER_M` and
`TRACK_WIDTH_M` are both marked UNCONFIRMED placeholders in `config.py`. Every
pose estimate inherits their error.

**S-4 — No inverse kinematics for the arm.** No per-joint calibration exists,
so there is no reach-envelope model to plan against. Grasp is a fixed primitive
sequence. `arm_jog.py` is the tool that closes this.

**S-5 — Hand-off confirmation is timed, not sensed.** No tactile or force
sensor on the gripper.

**S-6 — Watchdog and overrun thresholds are inconsistent.** *Partially
addressed 2026-08-18.* `willy-rover.service` sets `WatchdogSec=500ms`,
requiring `WATCHDOG=1` at least every 250ms. The run loop is a tick plus a
50ms sleep, and `TICK_OVERRUN_THRESHOLD_S` is 0.15s — the concrete risk was
never really about those two numbers directly (150ms and 0.15s both already
sit safely under 500ms); it was that `brain.py` only calls `notify()` once per
tick, so a single tick blocking anywhere *near* 500ms gets the process killed
by systemd mid-tick, before that tick's own overrun-logging (which runs after
`_tick()` returns) ever executes. The two known code paths that could push a
tick that long — `retrieval_task.py`'s `_grasp()` (~1.1s) and the wave-hello
gesture (~1.5s), both previously blocking via `time.sleep()` — are now
non-blocking, tick-serviced step machines. No other per-tick blocking call is
currently known, which closes the *known cause*, not the risk structurally.
Raising `WatchdogSec` or lowering `TICK_OVERRUN_THRESHOLD_S` further is still
sound general hygiene, just no longer urgent the same way. Unverified on live
hardware, same as everything else in this document.

Separately, `brain.py` carries a 2026-08-08 audit comment asserting no
`WatchdogSec` is configured, confirmed at the time via `systemctl cat`. The
repository unit file now sets one. Confirm which is true on the rover before
relying on either.

**S-7 — `Encoders.stalled()` has no caller.** *Addressed 2026-08-18.*
`RoverBrain._check_stall()` now calls it every tick for each currently-
commanded wheel (via `motors.py::DriveBase.commanded`), escalating to
`emergency_stop()` and a new `STALL_FAULT` state after `config.STALL_GRACE_S`
(1.0s, to clear the ramp-up window and the encoder's own 0.2s rate-sampling
lag) — same sustained-past-a-grace-period shape as `_check_health()`'s
IMU/encoder/current checks. Emits a `MOTOR_STALL` event (not `MOTOR_FAULT` —
that name was always meant to cover both stall and overcurrent generically;
this only implements the stall half). Directive 5 is enforced by code now;
not yet live-verified, since it has never run against a real motor. There is
still no overcurrent trip threshold defined — that half of the original
`MOTOR_FAULT` concept remains open.

**S-8 — Smart home direction is an unconfirmed assumption.** `smart_home.py`
implements Willie sending commands *out* to devices via Home Assistant's REST
API. Whether the requirement actually meant the reverse — Willie controlled by
Google Assistant — is recorded in the FRD as not yet confirmed with the owner.
Google exposes no public API for a third-party script to command another
account's Home devices, which is why Home Assistant is the backend; the
`discover`/`send_command` interface is written so the backend can be swapped
without touching callers.

---

## 9. Logging and Diagnostics

`logsetup.log_event(logger, event, severity, **fields)` emits a greppable
`EVENT=<name>` tag. Applied at real fault and abort sites only — this was
deliberately *not* a wholesale reformat of every log line into JSON.

Tagged events currently emitted:

| Event | Source |
|-------|--------|
| `IMU_FAULT`, `ENCODERS_FAULT`, `CURRENT_FAULT`, `BATTERY_ADC_FAULT` | `brain.py::_check_health()` |
| `LOW_BATTERY` (tagged `warn`/`return_to_home`/`safe_mode`/`shutdown`) | `brain.py` battery tiers |
| `OBSTACLE_STOP` | `safety.py` mid-flight abort |
| `NAVIGATION_ABORT` | `navigation.py::Navigator.abort()` |
| `AI_TIMEOUT` | `ai_provider.py`, only on a real `TimeoutError` |
| `TICK_OVERRUN` | `brain.py::_record_tick_duration()` |
| `MOTOR_STALL` | `brain.py::_tick()`, via `_check_stall()` — added 2026-08-18, see S-7 |

Deliberately untagged: `ESTOP_ACTIVE` (no sense pin to observe), and
`WATCHDOG_FAULT` (by the time systemd's watchdog fires the process is being
killed, so it cannot self-log). `MOTOR_FAULT`'s overcurrent half still has no
call site (no trip threshold defined) — see S-7; its stall half is now
`MOTOR_STALL` above.

`diagnostics.py` is a standalone read-only self-test. It never imports
`motors`, `steering` or `arm`, so it is safe to run at any time including
mid-assembly without risk of movement. It reports an itemised table rather than
a pass/fail string, and can run without starting the tick loop.

---

## 10. Testing

144 tests across 17 files, all off-hardware, all passing.

Off-hardware execution requires `WILLY_SIMULATE=1` plus `pygame` and
`networkx`. `config.SIMULATE_HARDWARE` gates every real I²C and GPIO open in
`motors.py`, `arm.py`, `sensors.py` and `brain.py`'s scan. `hw_sim.py` supplies
`SimMotor` and `SimServoBank`, which satisfy the existing interfaces unchanged
— no caller-visible API differences between simulated and real.

`display.py`'s pygame/Wayland init is deliberately not covered by the
simulation gate. It throws in its own daemon thread under simulation,
non-fatally, and does not block `RoverBrain.start()`.

Coverage exists for every item on the original test checklist except two, both
correctly untestable rather than overlooked: E-stop (no sense pin) and encoder
rollover (counts are unbounded Python ints, not a fixed-width register).

Notable: `tests/test_no_direct_drive_bypass.py` enforces the §2.1 layering rule
structurally. `tests/test_safety.py` covers the pure `approve_motion()`;
`tests/test_safety_controller.py` covers the stateful wrapper including command
timeout, mid-flight obstacle abort, and `emergency_stop()`.

---

## 11. Configuration

`config.py` holds every tunable, address and pin map, with dated calibration
notes and section citations against the hardware documentation. Credentials are
never in `config.py` — only environment-variable names and file paths.

`config.validate()` runs at startup and returns a list of problems rather than
raising, so a non-blocking issue is logged without preventing boot. It
currently checks battery ladder ordering (`SHUTDOWN < SAFE < RTH < WARN`),
`BAT_FULL_V` against `BAT_WARN_V`, and hysteresis positivity.

Two feature flags default on and were explicitly confirmed by the owner rather
than left as accidental defaults: `ENABLE_CLOUD_AI` and `ENABLE_EMAIL`.

---

## 12. Open Actions

1. ~~Repoint `CLAUDE.md`.~~ Done 2026-08-18 — points at the current trio now,
   with an explicit note on the rev 6.2.0-is-real-but-uncommitted situation.
2. **Watchdog threshold inconsistency (S-6) — partially addressed 2026-08-18.**
   The two known tick-blocking culprits are fixed (see S-6); still needs a
   live `systemctl cat willy-rover.service` check and live verification that
   no tick now approaches the kill threshold.
3. **Wire an E-stop sense line (S-1).** Blocks Directive 1 from being
   represented in software at all.
4. **Run `arm_jog.py` and record real per-joint limits (S-4).** Nothing else
   unblocks retrieval.
5. ~~Give `Encoders.stalled()` a caller (S-7).~~ Done 2026-08-18 for the stall
   half (see S-7) — not yet live-verified. Overcurrent half still open (no
   trip threshold defined).
6. **Bench-confirm `ENCODER_COUNTS_PER_REV`, `WHEEL_DIAMETER_M`,
   `TRACK_WIDTH_M` (S-2, S-3).**
7. **Confirm smart-home direction with the owner (S-8).**
8. **Integrate the accelerator into `vision.py` (§7).**

---

*End of document.*
