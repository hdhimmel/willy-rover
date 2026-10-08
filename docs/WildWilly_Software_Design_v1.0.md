# WildWilly Autonomous Rover

## Software Design — As-Built

**Revision 1.4 · Current Implementation · 2026-10-02**

---

## Document Control

| Field | Value |
|-------|-------|
| Project | WildWilly Autonomous Rover |
| Document | Software Design — as-built implementation |
| Revision | 1.4 |
| Date | 2026-10-02 |
| Owner | Howard Himmel |
| Status | Implemented and off-hardware tested; partially run on the rover (see §12). The filename keeps `v1.0` so cross-references in the Master Hardware Design, the FRD and `CLAUDE.md` stay valid; the Revision field is authoritative |
| Companions | Master Hardware Design rev 2.6; Functional Requirements v3.4 |

**Scope.** This describes the software as it is written today in `hdhimmel/willy-rover`.
It describes the current state only; history lives in git. Where a subsystem is
stubbed, disabled, approximate or not yet run on the rover, it says so.

---

## 1. System Summary

| Property | Value |
|----------|-------|
| Host | Raspberry Pi 5 (8GB), Debian 13 Trixie, Python 3.13.5 |
| Boot | SanDisk Extreme USB SSD (`sda`, 931 GB, label `willyssd`); EEPROM `BOOT_ORDER=0xf14` (USB first, SD fallback). The SD card is a bootable fallback refreshed weekly. See Master Hardware Design §5.1 |
| Entry point | `main.py` → `RoverBrain().run()` |
| Process management | systemd unit `willy-rover.service`, `Type=simple`, `Restart=on-failure`, `RestartSec=5`. **No `WatchdogSec`** (see S-6) |
| Modules | 35 Python files at repository root, plus `firmware/pico_a.py` and `firmware/pico_b.py` (MicroPython) |
| Source size | ~10,450 lines including firmware |
| Tests | 73 files, 404 `def test_` functions (more items collected, because parametrised cases collect separately), run under `WILLY_SIMULATE=1` |
| Simulation mode | `WILLY_SIMULATE=1` gates every real I²C, GPIO and UART open |

### 1.1 Module inventory

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `brain.py` | 2077 | Top-level FSM, tick loop, directive arbitration, health/fault checks, battery halt, demonstrations, identity wiring |
| `config.py` | 1238 | All tunables, addresses, pin maps; `validate()` self-check |
| `voice.py` | 873 | Wake word, STT, intent parsing, TTS, fast-path matching, tone; `interpret_text()` (email commands), `prompt_listen()` (one utterance without the wake word), current-person scoping of "remember that" facts |
| `sensors.py` | 714 | `SonarArray` (Pico B + ToF fusion), `IMU`, `ADC`, `Encoders` (Pico A), `CurrentMonitor` |
| `display.py` | 448 | Face rendering, status overlay, touch buttons (reset, roam, two-step STOP SVC and self-test override) |
| `ai_provider.py` | 383 | Unified cloud/local LLM abstraction |
| `email_client.py` | 352 | IMAP/SMTP with allowlists and confirm gates; owner email commands (DKIM-verified, freshness-checked); `approve <code>` handlers |
| `world_model.py` | 332 | Persistent spatial model — obstacles, rooms, objects, routes, stair edges (`Stair`, `ray_to_segment()`) |
| `identity.py` | 273 | FR-2100 identity store and matcher — separate SQLite file, three-band cosine match, pending-is-inert enrolment, `approve()`, `forget_all()`, greeting debounce |
| `motors.py` | 271 | Drive base and steering primitives; `MOTOR_SIGN`; closed-loop wheel speed (`wheel_duty()`); no-twitch `brake()` |
| `tof.py` | 270 | SEN0628 frame source (`SerialFrameSource`), background reader thread (`BackgroundFrames`), floor profile, obstacle/drop classification |
| `feature_requests.py` | 239 | FR-2200: evidence from his own log, cloud-composed request emailed with a one-time code; on approval writes `docs/feature-requests/<date>-<slug>.md`, commits that file alone and pushes. Own low-frequency thread |
| `vision.py` | 228 | Object detection (Hailo NPU backend; CPU backend present but disabled), bearing/range heuristics, `capture_frame()` / `capture_still()` |
| `pico_link.py` | 214 | One framed-UART reader per Pico (`$<body>*<XX>`); keeps the newest frame and its age; never invents a value |
| `memory_store.py` | 192 | Conversational and episodic memory (SQLite); routines (`note_routine()`, `top_routines()`); demonstrations; person-scoped facts |
| `retrieval_task.py` | 184 | Object retrieval sub-FSM |
| `navigation.py` | 165 | Route resolution and local planning |
| `safety.py` | 143 | The motion authority — sole gate to the motors |
| `hailo_llm.py` | 116 | Hailo NPU intent model (`qwen2:1.5b`, ChatML-framed) |
| `pursuit_task.py` | 111 | Come-here and follow-me sub-FSM |
| `arm.py` | 109 | Arm servo primitives; idle release; `center_all()` excludes the elbow |
| `odometry.py` | 99 | Dead-reckoning pose; optional IMU-yaw rotation source |
| `recognition.py` | 97 | FR-2100 embeddings: OpenCV YuNet detection + SFace 128-d embedding on the CPU, own thread, `IDLE`-only scan every `FACE_SCAN_S`; `capture_for_enrolment()`. Frames are embedded and dropped. Disables itself if models or camera are missing |
| `diagnostics.py` | 96 | Standalone read-only self-test |
| `remote_cmd.py` | 90 | Inbound Home Assistant commands on `:8765` (S-8) |
| `smart_home.py` | 84 | Home Assistant REST client (outbound; disabled) |
| `main.py` | 70 | Entry point, I²C pre-probe, signal routing |
| `mapping.py` | 68 | Learning-mode map recording session |
| `privacy.py` | 59 | Mic/camera disable flag; cloud-send notes; file purge |
| `storage.py` | 53 | Data root resolution and availability check |
| `logsetup.py` | 42 | Logging config and `log_event` structured tags |
| `hailo_stt.py` | 41 | Hailo STT scaffolding (`ENABLE_HAILO_STT=False`, no model) |
| `arm_jog.py` | 39 | Interactive bench-calibration jog tool |
| `witty_pi.py` | 33 | Witty Pi 5 hardware-watchdog heartbeat |
| `hw_sim.py` | 22 | Simulation mocks for motors and servo banks |
| `firmware/pico_a.py` | 362 | Pico A: six encoders in PIO, signed ×2, R5 sense, `$E` at 50 Hz. Version `a-0.3` |
| `firmware/pico_b.py` | 264 | Pico B: three HC-SR04 round-robin, BNO085 RST, `$S` at 33.3 Hz. Version `b-0.1` |

---

## 2. Control Architecture

### 2.1 Layering

One structural rule: **nothing calls the motors except through `safety.py`.** Not the
reactive FSM, not a task sub-machine, not the AI. `tests/test_no_direct_drive_bypass.py`
enforces it.

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
  Reflex inputs           Sonar (Pico B), ToF, encoders (Pico A), IMU, current monitors.
  (deterministic)         Feed the arbitration layer directly. Never wait on vision.
          │
          ▼
  Hardware layer          motors.py, arm.py, sensors.py — or hw_sim.py mocks
```

An obstacle stop never depends on a detection frame arriving (Master Hardware Design §12
rules 15–16). `tests/test_reflex_deliberative_separation.py` checks that no reflex module
imports or mentions an AI backend.

### 2.2 The safety gate

**`approve_motion(...)` — a pure function.** No hardware access, no state. Takes an
action, optional speed and duration, and the context (`front_cm`, `tilt_deg`,
`bat_tier`, `motion_enabled`) as explicit arguments. Returns an `ApprovedMotion` with
speed clamped to `SPEED_MAX` and duration to `MAX_COMMAND_DURATION_S` (3.0 s), or a
`Rejected` with a reason. Rejection order:

1. Motion not enabled — the startup self-test failed.
2. Action not in the recognised continuous set.
3. Tilt exceeds `IMU_TILT_LIMIT` (25°).
4. Battery tier is `safe` or `shutdown`.
5. Action is `forward` and the front distance is inside `DIST_STOP` (20 cm).

`front_cm` defaults to **0.0** (blocked), so forward motion is refused until a real
reading has arrived.

**`SafetyController` — the stateful wrapper.** Caches the context once per tick,
executes approved motion, and services timed moves without blocking. `duration=None` is
a continuous command re-issued each tick; `duration=<n>` starts a timed move serviced by
`tick()`. It has exactly one caller thread — the tick thread. Voice's `stop_requested` is
an `Event` consumed at the top of `_tick()` to preserve that.

### 2.3 The tick loop

`RoverBrain.run()` loops: tick, record duration, sleep 50 ms — about 20 Hz.

Order within `_tick()`:

1. **Voice stop** — before any directive gating. Aborts every task sub-machine, calls
   `emergency_stop()`, revokes roam permission. The only place the flag is cleared.
2. **Pending asks** — shutdown confirmation deadline, roam-permission ask (§3.1.1).
3. **Health check** — `_check_health()`: per-subsystem `_fault_since` tracking (IMU,
   encoders, current, battery ADC, sonar, motor ramp thread). Unhealthy beyond
   `SENSOR_FAULT_GRACE_S` (1.0 s) is a sustained fault → `emergency_stop()` and
   `SENSOR_FAULT`. Fault events carry `value=` and `expected=`.
4. **Watchdog notify** — `WATCHDOG=1` to systemd (inert: no `WatchdogSec`, S-6) and the
   Witty Pi 5 heartbeat.
5. **Odometry update.**
6. **Sensor read and safety context** — `distances`, tilt, battery; `update_context()`.
7. **Sustained fault → stop**, then **tilt** (`TILT_FAULT` past 25°, `WARN` past 18°).
8. **Detection checks**, each reporting and only `_check_arm_current()` acting:
   - `_check_motor_rail()` — +12V bus (INA260 0x45) below `MOTOR_RAIL_MIN_V` (6.0 V) for
     `MOTOR_RAIL_GRACE_S` → logged and shown on the face (SW-M motor-cut observability).
   - `_check_r5()` — Pico A's R5-low flag past `ENCODER_R5_GRACE_S` (0.5 s) → status prefix
     `⚠ENCODER RAIL LOW`; stall stops name the rail. No stop of its own.
   - `_check_arm_current()` — arm rail above `ARM_CURRENT_LIMIT_A` (2.5 A) for
     `ARM_CURRENT_LIMIT_S` (0.4 s) → `arm.release()`, `ARM_OVERCURRENT`.
   - `_check_sonar_channels()` — per-channel `SONAR_FAULT` from
     `SonarArray.failed_channels`, debounced `SONAR_FAULT_DEBOUNCE_S` (2 s) each way.
   - `_check_uncommanded_motion()` — wheels turning (≥ `UNCOMMANDED_COUNTS_PER_S`, 50)
     with nothing commanded for `UNCOMMANDED_GRACE_S` (2 s) → `UNCOMMANDED_MOTION`, once
     per episode, not braked.
   - `_check_battery_crosscheck()` — ADC vs INA260 0x45 (§4.2).
9. **Battery tier** (§4.2), then the **stall check** (`STALL_FAULT`) and the
   **overcurrent check** (`_check_overcurrent()`: a rail in `OVERCURRENT_LIMIT_A` —
   `bus_12v` 9.0 A only — the `steering_5v` trip was dropped 2026-10-08 because 0x40 does not see
   steering current — held `OVERCURRENT_S` 1.0 s → stop, latched
   `OVERCURRENT_FAULT` until operator reset).
10. **State dispatch** — the Directive 6 layer.

A tick longer than `TICK_OVERRUN_THRESHOLD_S` (0.15 s) logs `TICK_OVERRUN` with a running
count.

The IMU read thread treats a reading as failed when the quaternion **and** the raw
accelerometer are both unchanged for `IMU_STALE_S` (3.0 s) — the BNO085 driver otherwise
returns a cached value forever after a reset it did not cause. After
`IMU_RESET_AFTER_FAILS` (10) failures it pulses the BNO085 `RST` through Pico B
(`SonarArray.reset_imu`, acknowledged `$R,ok`) and rebuilds the driver, at most once per
`IMU_RESET_MIN_INTERVAL_S` (10 s).

### 2.3a Wheel speed and braking

- **Speeds are mph.** `SPEED_MAX_MPH` = 1.5 is the cap; `SPEED_ROAM` / `SLOW` / `TURN`
  are fractions of it (1.0 / 0.5 / 1.0 mph → 0.667 / 0.333 / 0.667), not PWM duty.
  `SPEED_MAX` = 1.0. The motors top out near 147 RPM free (~1.8 mph).
- **Ramp.** `SPEED_RAMP_PER_S` = 2.0 (full range in 0.5 s).
- **Closed-loop wheel speed** (`WHEEL_SPEED_CONTROL=True`). The ramp thread turns each
  wheel's ramped command into a target RPM and asks the pure `motors.wheel_duty()` for a
  duty: feed-forward from `WHEEL_FF` (per-wheel duty→RPM line) plus a PI trim on the
  encoder (`WHEEL_KP` 0.002, `WHEEL_KI` 0.008), bounded to ±`WHEEL_TRIM_MAX` (0.30) so a
  blocked wheel gets a limited push and the stall stop still fires. Encoders reach it via
  `DriveBase.attach_encoders()`; unhealthy encoders or the flag off → feed-forward only.
- **Coast.** After `MOTOR_COAST_AFTER_S` (2.0 s) stopped and ramped down, the bridges are
  released and both MotorKit PCA9685s sleep. `brake()` on a coasting drive with every
  target and actual at zero returns immediately — waking and braking would twitch all six
  wheels.
- **Sign.** `MOTOR_SIGN` negates the right side at the single throttle write (the sides
  are mounted mirrored); everything above it is in rover terms (+ = forward).

---

## 3. State Machine

### 3.1 Top-level states

Twenty states. Seventeen are in `_tick()`'s dispatch table; `INIT`, `SENSOR_FAULT` and
`STALL_FAULT` are handled outside it.

| State | Class | Entered when |
|-------|-------|--------------|
| `INIT` | Startup | Construction, before self-test |
| `IDLE` | Nominal | Self-test passed; nothing to do |
| `ROAM` | Nominal | Path cleared; or idle timeout elapsed **and** roam permission granted (§3.1.1) |
| `SLOW` | Nominal | Front distance inside `DIST_SLOW` (40 cm) |
| `AVOID` | Reactive | Front distance inside `DIST_STOP` (20 cm) |
| `STUCK` | Reactive | `CLAUDE_ESCALATE_AFTER` (5) consecutive stuck-avoid cycles |
| `WARN` | Fault | Tilt past `IMU_TILT_WARN` (18°) |
| `TILT_FAULT` | Fault | Tilt past `IMU_TILT_LIMIT` (25°) |
| `SENSOR_FAULT` | Fault | Sustained subsystem fault past grace period |
| `STALL_FAULT` | Fault | Commanded wheel showing no counts past `STALL_GRACE_S` (1.0 s) |
| `OVERCURRENT_FAULT` | Fault | A rail above `OVERCURRENT_LIMIT_A` for `OVERCURRENT_S`; latched until operator reset |
| `SAFE_MODE` | Fault | Battery below `BAT_SAFE_V` (10.5 V) |
| `LOW_BATTERY` | Terminal | Battery below `BAT_RTH_V` (10.8 V) with `ENABLE_DOCKING=False`: stopped, memory saved, guarded halt pending; back to `IDLE` if the pack recovers first |
| `SHUTDOWN` | Terminal | Battery below `BAT_SHUTDOWN_V` (10.2 V), or voice-confirmed shutdown |
| `DOCK` | Task | Battery below `BAT_RTH_V` only when `ENABLE_DOCKING=True`. Docking is deferred (`ENABLE_DOCKING=False`), so unreachable |
| `MANUAL` | Task | Voice-issued manual drive command |
| `NAVIGATE` | Task | `go_to` intent, delegates to `navigation.py` |
| `RETRIEVE` | Task | `retrieve` intent, delegates to `retrieval_task.py`; refused unless `ENABLE_RETRIEVAL_TASK` (False) |
| `PURSUE` | Task | `come_here` / `follow`, delegates to `pursuit_task.py` |
| `WAVE` | Task | `wave` intent — non-blocking step machine (see Arm control) |

`TILT_FAULT`, `SENSOR_FAULT` and `STALL_FAULT` do not auto-resume when the condition
clears: they keep braking until the touchscreen "TAP TO RESUME" button is pressed
(`brain.py::_await_reset_or_resume()`, `display.py::reset_tapped()`).

### 3.1.1 Permission to enter ROAM unprompted (FR-1000-005)

Two transitions into `ROAM` are unprompted: the `IDLE_TIMEOUT` (30 s) wander in
`_idle()`, and the charged-to-95% resume in the `DOCK` handling (dormant while docking is
deferred). Both call `_roam_allowed()`, which returns True only once
`self._roam_permission` has been granted this session, and otherwise opens a permission
request and returns False. Every other transition into `ROAM` (e.g. `AVOID`/`SLOW`
returning once the path clears) is untouched — the rover is already moving with
permission.

`_roam_allowed()` short-circuits on a pending request and on the cooldown before opening
a new one, so the every-tick callers cannot re-ask at tick rate.

The request has one exit, `_end_roam_ask()`, reached four ways: a panel tap or a spoken
yes (granted); a spoken no or a lapse past `ROAM_ASK_TIMEOUT_S` (30 s) (declined, starting
`ROAM_ASK_COOLDOWN_S`, 600 s). `_service_roam_ask()` handles the non-spoken outcomes each
tick; `_drain_voice_commands()` claims the next queued command as the answer, including
the `speech_only` early return. A pending shutdown confirmation suppresses the request,
and a voice stop calls `_revoke_roam_permission()`. A remote command is never claimed as
the answer to a pending shutdown or roam ask.

Panel side: `display.py::offer_roam()` / `roam_tapped()`, single tap. The `STOP SVC`
(`_handle_stop_tap`) and self-test override (`_handle_override_tap`) buttons are two-step,
because one stops the service and the other enables motion on a rover that failed its own
safety check. There is no DECLINE button — declining and ignoring land in the same
cooldown.

`ENABLE_AUTONOMOUS_ROAM=True` means "allowed to ask". The grant is not persisted, so no
configuration puts the rover into unattended roaming at power-on.
`ROAM_PERMISSION_REQUIRED=True`; False skips the ask.

### 3.2 Sub-state machines

- `RetrievalTask` — `LOCALIZE / APPROACH / GRASP / VERIFY / DELIVER / AWAIT_CONFIRM`
- `PursuitTask` — `LOCALIZE / APPROACH / FOLLOWING`. `LOCALIZE` looks for
  `PURSUIT_LOOK_TICKS` (10) ticks, then makes a timed left turn
  (`PURSUIT_SEARCH_TURN_S` 0.4 s), up to `PURSUIT_SEARCH_STEPS` (8). Standoff
  `PURSUIT_STANDOFF_CM` 60, resume hysteresis 20 cm
- `Navigator` — `SEEKING / AVOIDING / DONE / FAILED / ABORTED`

Each exposes `abort()`, called by `brain.py` when any Directive 1–4 preemption fires.
None re-checks the directives itself; `brain.py` tells it to stop.

### 3.3 Two deliberate deviations from a naive FSM design

**Mapping is not a top-level state.** `MappingSession.active` is an orthogonal flag
checked alongside the normal ROAM/SLOW/AVOID dispatch, so driving while mapping is the
unmodified reactive FSM. A mapping state would have to call `_avoid()`/`_stuck()`, whose
own `_go('ROAM')` transitions would silently exit mapping.

**Navigation's obstacle avoidance is a self-contained copy, not a call into
`_avoid()`**, for the same reason. The constants are shared. `Navigator` does own a
top-level state, because driving needs one.

**Stopping for an obstacle brakes (2026-10-07).** Crossing `DIST_STOP` calls
`SafetyController.obstacle_stop()` — a hard brake that also clears any timed move — instead of
the ramped `stop()`, which at 1 mph took ~0.3 s and, with each sonar refreshed only every ~90 ms,
let him roll ~10 cm past a first-seen obstacle. Used by ROAM/SLOW, the timed-move abort,
Navigator, pursuit and retrieval. The ToF's rows outside the floor band also now count any
return nearer than `TOF_NOFLOOR_OBSTACLE_MM` (40 cm) as an obstacle, so things at body height
(a couch edge, a table top) feed `front` and the turn choice.

**Both avoiders take their turn direction from `avoidance.py`** (2026-10-06). Left and
right clearance are each the min() of the side sonar, the ToF's column half
(`TOF_LEFT_COLUMNS=(0,1,2,3)`, re-measured 2026-10-07 after a 180° remount; only the floor
rows `TOF_FLOOR_ROWS=(6,7)` carry a profile, so obstacles count only where they block that band) and the nearest front-camera detection
on that side. It runs only after something has already stopped him, so the camera picks a
side and never gates a stop (Master Hardware Design §12 rule 15). A source that raises or
has nothing to say contributes nothing.

**Rotation mode (`rotate.py`, 2026-10-07).** Turning on the spot steers the four corners onto
the turning circle (FL and RR right, FR and RL left, middles straight), waits for the servos,
then spins with corners 1.44× the middles' speed (`DriveBase.set_wheels`). It stops on IMU
heading, not time; any sonar/ToF reading inside `ROTATE_CLEAR_CM`, a heading moving the wrong
way, a timeout, or the cameras disagreeing with the IMU stops it and says why. **Camera check
(2026-10-07, after two live runs):** front and rear cameras each integrate frame-to-frame image
shift, but only over clear frames (phase-correlation quality ≥ 0.5) and against the IMU over
those same frames — motion-blurred frames had read as "no movement" and turned 87° into 17°.
It stops only if every camera with enough clear frames disagrees, so one blurred or dark camera
cannot stop a turn the other agrees on. The rear camera's field of view is a typical figure,
not measured. **Blind spots (2026-10-07, spun into the couch):** nothing senses the rear or the
corners during a spin — sonars face front/left/right, the ToF forward, and sonar misses soft
furniture. The backstop is a bump stop: once under way, heading slower than 5°/s for 0.7 s
stops the turn (~1 s, not the 8 s timeout that caught the couch). Rotation needs open space.
**Pre-spin clearance (2026-10-07, outside review P0):** a rotation is refused before anything
moves unless front, left and right all read ≥ `ROTATE_START_CLEAR_CM` (20 cm: the corners sweep
~9 cm beyond the estimated 0.42 × 0.41 m body), or if the sensors cannot be read; he says which
side is short. In `_avoid()` a refused rotation backs up instead of skid-turning, since a skid
turn sweeps the same circle. The rear is still unseen — that is what the bump stop is for. Bench-run by `scripts/rotate_test.py` (feed-forward drive, no speed loop). **Live-verified
2026-10-07** in open space: +90° settled at +87.8°, −90° at −93.8° (stop 10° early, ~6–8° coast);
both cameras agreed with the IMU over clear frames with the check live; the bump stop caught two
runs against the couch in ~1.7 s each. **Wired into brain.py (2026-10-07, not yet run in the
service):** state `ROTATE` (`start_rotation(deg, then=...)`); the spin is approved by
`SafetyController.set_wheels` like any turn; every Directive/stop site aborts it; voice "turn
around" (180°) and "turn left/right N degrees"; `_avoid()` turns ±45°/±90° by rotation when
`AVOID_USE_ROTATION`, and a refused or blocked rotation backs off and lets AVOID retry.
Navigator's own avoidance still skid-turns. The service uses the front camera only.

**Faster replies (2026-10-07).** Live `voice timing` put speech-to-text at ~3.7–4.1 s (mostly
the speaking itself plus the 0.6 s end-of-speech silence; transcription ~1 s) and reply
synthesis at **2.6–5.1 s**, because every reply started a new `piper` process that loaded the
voice model from disk. `voice.PiperEngine` now loads the model once (on the speaker thread at
startup) through Piper's Python API — 1.3+ `synthesize_wav`/`SynthesisConfig` or 1.2
`synthesize` — and caches the finished audio of short replies (≤ `TTS_CACHE_MAX_CHARS`), so
fixed fast-path answers need no synthesis after first use. Any failure falls back to the old
subprocess. The timing line now names the path taken (`cache`/`inproc`/`subprocess`).
**Measured 2026-10-08:** reply synthesis 2.6–5.1 s → **0.1–0.4 s** (`inproc`); a simple command
6.5–8.8 s → ~4.5 s end to end. What remains is speech-to-text: ~2 s speaking (incl. the 0.6 s
end-of-speech wait) + ~2 s transcription. Benchmark on willie (12 Piper-spoken command phrases,
no recordings): `base.en` 2.19 s / 12 correct; 4 threads or no timestamps no faster; `tiny.en`
1.13 s but 11/12 ("how's your battery" → "House your battery") — rejected, a mishearing can
match the wrong command. With the service stopped `base.en` took **1.44 s**: the service competes
with itself. py-spy put the face display (30 fps redraw + flip) at ~20% of a core and the
wake-word listener at ~13% (it is the transcribing thread, so it already pauses). So the display
now drops to `DISPLAY_FPS_QUIET` (5) while transcribing (`display.set_quiet`, `voice._display_quiet`).

**Talking mouth (FR-1600-009, 2026-10-07).** `_synthesize_and_play()` computes the loudness
envelope of the WAV Piper just wrote (`speech_envelope`, 50 ms windows, normalised and gated)
and hands it to `display.set_talking()` immediately before `pw-play`; `stop_talking()` runs in
the `finally`. The display draws an open mouth whose height follows the envelope by elapsed time
(`mouth_openness`), so the face needs no audio access and no extra thread. Any failure leaves
the normal mouth; speech is never delayed by it.

**Hailo generation freezes the process (found 2026-10-07).** `generate_all()` holds the GIL for
the whole call (5.4 s measured): tick loop, sensor readers and the motor ramp thread all stop, and
every freshness check fails at once when it returns (IMU, encoders, current, battery ADC, sonars,
all within 0.1 s). A rover driving when a call starts would keep its last duty, unwatched. Interim:
`hailo_llm.set_before_generate()` runs brain's `_brake_before_hailo()` first, which brakes
synchronously through `SafetyController.brake_now()` if anything is commanded (fast-path voice never reaches the model). Real
fix open: the model in its own process, which needs design because the VDevice is shared with
vision (why hailo-ollama was rejected, 2026-08-21). **Streaming (2026-10-08):** `hailo_llm`
now uses `generate()` instead of `generate_all()`; measured on willie, the longest freeze of
other threads fell from 7.7 s to 2.2 s (the prompt read), ~0.12 s per token after it.

**Come to me (`come_to_me_task.py`, FR-1000-006) owns no motion.** It sequences
`Navigator` (room mission, through labelled doorways) and `PursuitTask` (`come_here`, with
its search sweep) under one `COME_TO_ME` state. Directive aborts reach the legs through the
existing navigator/pursuit abort sites, so the task's `active` is read from its current
leg, not from its own state. A blocked labelled doorway puts `Navigator` in `DOOR_WAIT`
(stopped, still `active`), asking aloud until the way clears or `DOOR_MAX_ASKS` runs out.

---

## 4. Startup and Shutdown

### 4.1 Startup sequence

**Before any of this: the clock** (`scripts/clock_sync.sh`, the unit's `ExecStartPre`,
2026-10-06). At boot the Witty Pi daemon sets the system clock from its own RTC; on
2026-10-06 that RTC was a week fast and the service started on the wrong date before
internet time arrived. The script waits up to 45 s for `timesyncd` to sync, then writes
the system time back to the Witty Pi RTC (`wp5`, as the service user). No internet in time
means starting on the RTC's time, logged; it never stops the service starting.

0. **I²C pre-probe in `main.py`.** Before importing `brain.py`, `main.py` does an `smbus2`
   read against each expected address. If none ack (Pi disconnected from the rover
   harness), it sets `WILLY_SIMULATE=1` and `WILLY_I2C_FORCED_SIMULATE=1` and patches
   `config.SIMULATE_HARDWARE=True` on the already-imported module; `start()` then shows
   "I2C OFFLINE — degraded mode, restart to recheck". One-time check; restart the service
   to re-check. **`config.SIMULATE_HARDWARE` is frozen at first import** — setting the env
   var later in the same process does not reach modules that already imported `config`.
1. `RoverBrain.__init__` constructs every subsystem. If `ENABLE_TOF`, it builds
   `ToFSensor(BackgroundFrames(SerialFrameSource()))` on `/dev/ttyAMA3` and attaches it to
   `SonarArray` (warning if no floor profile). The IMU gets Pico B's reset callback.
   `motors.py`/`arm.py` construction calls `PCA9685.reset()`, which clears ALLCALL — so
   0x70 does not answer and is not expected.
2. `start()` brings up display, sensors, encoders, current monitors; centres steering and
   the arm **except the elbow** (`Arm.center_all()` skips CH1 — see Arm control); starts
   voice, email, remote command, feature-request and face-recognition threads.
3. `_self_test()`:
   - **I²C presence** against `_EXPECTED_I2C` — **ten** addresses: 0x40, 0x42, 0x43, 0x44,
     0x45, 0x48, 0x4A, 0x51 (Witty Pi, because `ENABLE_WITTY_PI=True`), 0x60, 0x61. There
     is no full bus scan. `_i2c_present(seen, probe)` counts 0x4A present without probing
     it (its driver constructing proves it; `imu.is_healthy` is its health check) and
     probes only the other expected addresses not yet seen — any quick-write to 0x4A makes
     the BNO085 emit an SHTP error list that stalls it.
   - **Encoders** — `self.encoders.is_healthy`: Pico A's `$E` frames are fresh. Liveness
     only; channel-to-wheel attribution is a bench test (FR-500-001), because the gate that
     authorises motion cannot itself require motion.
   - **IMU** — `imu.is_healthy`. No code reads the BNO085 INT line.
   - `config.validate()` and `storage.check_storage()`.
   - **Base-off is named.** If every critical failure is base-fed (battery ADC, encoders,
     motor drivers) and 0x45 reads below `MOTOR_RAIL_MIN_V`, the failure reads "base power
     appears OFF (12V bus X V)".
4. `_motion_enabled` is set from the result and gates every `approve_motion()` call
   (FR-100-004). While it fails, the self-test re-runs every `SELFTEST_RETRY_S` (30 s);
   after `SELFTEST_OVERRIDE_AFTER` (3) failures for the same reason the display offers a
   two-step override, in memory only. TILT/STALL/SENSOR faults are not overridable.
5. `READY=1` is sent to systemd either way. On pass the state goes to `IDLE`. On fail,
   motion stays disabled, the reason is logged and shown, and voice keeps answering:
   `_drain_voice_in_selftest_fault()` runs `_SELFTEST_FAULT_INTENTS` (speech-only intents
   plus `diagnostics`, `shutdown`) and refuses anything else aloud with the reason.

Voice and email start regardless of self-test outcome. Neither can move the rover: voice
queues intents for `_tick()` to gate, and email commands queue the same way.

**Witty Pi 5 HAT+ (0x51).** Vendor software (`wp5` CLI, `wp5d` daemon) handles RTC sync,
scheduled power, the low-voltage cutoff and its own shutdown-request register.
`witty_pi.py` only feeds Willie's per-tick liveness into the HAT's independent hardware
watchdog (register #70) beside the systemd notify, so a hung kernel still gets a real
power cycle. The heartbeat is a register read, per the manual; whether it satisfies the
watchdog is not yet confirmed on the device (§12).

### 4.2 Shutdown

`main.py` routes SIGTERM through the same `KeyboardInterrupt` path as SIGINT, so systemd
stop/restart run `RoverBrain.stop()`: `emergency_stop()`, save memory and world model,
stop every background thread. `display.py` sets `SDL_NO_SIGNAL_HANDLERS=1` so SDL does not
swallow those signals.

Voice-commanded shutdown (FR-900-005) is confirm-gated: a pending flag with a deadline,
dispatched outside the state table.

**Battery halts (FR-200-004/005).** The `rth` tier (with `ENABLE_DOCKING=False`) and the
`shutdown` tier both end in `_battery_halt()`, which calls the same `_begin_shutdown()` as
a voice shutdown: emergency stop, `arm.center_all()` (no stow pose exists), "Shutting down
now", then `stop()`'s tail runs `sudo shutdown -h now`. `rth` first stops, saves memory
once, announces, and enters `LOW_BATTERY`. Two guards:

- **Confirm time.** The reading must stay under the tier's threshold for
  `BAT_HALT_CONFIRM_S` (10 s) with the rover stopped; recovery above the threshold restarts
  the clock, and recovery past the hysteresis band (`BAT_HYSTERESIS_V` 0.2) returns to
  `IDLE`.
- **Which reading is the authority (made explicit 2026-10-07).** While the +12V bus monitor
  (0x45) is live (≥ `MOTOR_RAIL_MIN_V`), `battery_volts` **is** the bus plus
  `BUS_TO_PACK_DROP_V` (since `b47f7d7`), so the halt acts on the bus. The ADS1115 divider is
  only the fallback for a dead bus (motor cut, base off), where it is the one reading left.
- **Cross-check veto.** `_battery_reading_disputed()`: with the bus live it is only a
  consistency guard (`battery_volts` vs the bus, which can differ only if that wiring is
  undone). With the bus dead, the halt is blocked while `_check_battery_crosscheck()` last
  caught the divider disagreeing with the bus by more than `BAT_CROSSCHECK_MAX_DIFF_V`
  (1.5 V) — a divider already known wrong (7.2 V, then 15.4 V, on a 12 V pack on 2026-10-06/07)
  must not power the Pi off, or be trusted to. This is the one place the cross-check changes
  behaviour, and it can only prevent a halt. Until the divider is fixed, a dead-bus low
  battery is therefore not caught by software.

Battery ladder: `BAT_WARN_V` 11.4, `BAT_RTH_V` 10.8, `BAT_SAFE_V` 10.5, `BAT_SHUTDOWN_V`
10.2. `BAT_FULL_V` 11.58 is a display-only 100% anchor for `battery_pct`; every safety
decision compares raw volts. `tests/test_battery_halt.py`.

---

## 5. Data and Persistence

Four data roots, resolved by `storage.resolve_root()` (env var if set, else a
repository-relative default): `WILLY_DATA_ROOT`, `WILLY_MAP_ROOT`, `WILLY_MEMORY_ROOT`,
`WILLY_LOG_ROOT`. All four resolve to the same volume (the SSD); the split exists so a
future separation is configuration, not code.

| Database | Module | Contents |
|----------|--------|----------|
| `memory.db` | `memory_store.py` | Conversational and episodic memory, routines, demonstrations |
| `world_model.db` | `world_model.py` | Obstacles, rooms, doorways, objects, landmarks, routes (including demonstration routes), `stairs` (name, x, y, heading, width_m) |
| `identities.db` | `identity.py` | Enrolled face embeddings (`IDENTITY_DB_PATH`) |

All WAL-mode. Each `__init__` catches `sqlite3.DatabaseError`, moves the corrupted file
aside (never deletes it) and starts fresh. `storage.check_storage()` is part of the
startup self-test.

Small JSON state lives in `secrets/` (never in git): pending enrolment codes, the pending
feature request, its history and push-retry flag, the inbound email allowlist, the remote
command token, the privacy flag.

**Retention.** `brain.py::_retention_sweep()` calls `memory.purge_expired()` from `IDLE`
at most once a day (`DATA_RETENTION_DAYS` 30; FR-1800-004 / FR-1900-010).
Since 2026-10-08 it also calls `privacy.purge_expired()` on rotated log backups
(`willy.log.*`, never the live file) older than that. Raw audio and camera frames are never
written. `world_model.db` is not swept: rooms, routes and doorways are kept on purpose.

Off-rover backup (nightly restic to the NAS) and the SD-card refresh are system timers on
willie, not repository code — Master Hardware Design §5.1.

---

## 6. AI Integration

### 6.1 Provider abstraction

`ai_provider.py` presents one `AIProvider` ABC with `CloudAIProvider` and
`LocalAIProvider` (llama.cpp, `llama-3.2-3b-instruct-q4.gguf`); `hailo_llm.py`'s
`HailoIntentModel` is a third implementation on the NPU.

One `CloudAIProvider` instance serves both `brain.py`'s STUCK motion decisions and
`voice.py`'s free-text fallback. Conversation history is **caller-owned** and passed into
each call, so the shared instance cannot leak STUCK's turns into voice's.

`CloudAIProvider` calls Anthropic's Claude API with `ANTHROPIC_API_KEY`, model
`claude-sonnet-5-5` (`CLAUDE_MODEL`): adaptive thinking at `CLAUDE_EFFORT='low'` (Sonnet
5.5 cannot disable thinking), `CLAUDE_MAX_TOKENS` 2000, the reply read from the first text
block, a refusal raised as a failure, server-side refusal fallback (`fallbacks:
"default"`) on, timeout `CLOUD_AI_TIMEOUT_S` 8 s. The STUCK escalation calls
`privacy.note_cloud_send()` before sending (FR-1800-003).

### 6.2 Confidence is four separate signals

`AIResult` deliberately keeps these apart:

| Field | Meaning |
|-------|---------|
| `parse_success` | The response structurally validated against the expected schema |
| `intent_confidence` | The model's self-reported confidence |
| `action_confidence` | Computed — action/duration/speed structurally sane. `None` for non-motion queries |
| `safety_validation` | Structural plausibility only |

`safety_validation` is **not** the safety gate; `approve_motion()` is. "The JSON parsed"
is never used as a proxy for "the model was confident".

### 6.3 Where the AI can and cannot act

The AI reaches exactly one motion path: `STUCK`, entered after `CLAUDE_ESCALATE_AFTER`
failed avoid cycles. Its proposal goes through `approve_motion()` like any other request.
Everywhere else it is advisory: intent interpretation, free-text replies,
world-state summaries.

An owner email command reaches the same interpreter through `voice.interpret_text()` and
is queued with `source='email'`, so it is gated exactly like a spoken command; only
DKIM-verified (`EMAIL_AUTHSERV_ID` `mx.google.com`), fresh (`EMAIL_COMMAND_MAX_AGE_S`
600 s) owner mail with the `willie` subject prefix gets that far (FR-2000-012/013).
FR-2200 feature requests use the cloud model to compose text only — an email and, on
approval, one Markdown file.

**Voice front end.** A transcript that is only the wake phrase (`_BARE_ADDRESS`) never
reaches a model; he asks "How can I help?". Compliments and personal questions
(`_BASHFUL_TRIGGER`) set the bashful tone and face; the reply tone reaches Piper as
`--length_scale` (`_TONE_LENGTH_SCALE`), falling back to neutral if Piper rejects the flag;
safety speech is always neutral. The wake loop logs a heartbeat once a minute.

### 6.4 Audio capture chain

Capture is a dedicated USB mic ("USB PnP **Sound** Device"); playback is the USB puck
("USB PnP **Audio** Device", its mic unused). The mic offers 48000 and 44100 Hz only,
openwakeword needs 16 kHz, and PortAudio exposes raw ALSA `hw:` devices with no
resampling route, so `voice.py` converts in software:

```
mic (48 kHz mono, 3840-sample block)
  -> VoiceInterface._read_frame()
       -> downsample_to_16k(block, factor=3)   # scipy.signal.decimate, FIR, zero_phase
  -> 1280 samples @ 16 kHz  ->  wake scoring / noise floor / endpointer / Whisper
```

`_read_frame()` is the single rate boundary, used by both the wake loop and utterance
capture, so everything downstream assumes 16 kHz / 1280.

- **48000, not 44100** — a whole-number ratio. `config.validate()` rejects any
  `AUDIO_INPUT_RATE` that is not a multiple of 16000.
- **`scipy.signal.decimate`, never `samples[::3]`** — striding aliases everything above
  8 kHz into the speech band and degrades wake scoring.
- **Selected by name** (`AUDIO_INPUT_DEVICE='USB PnP Sound Device'`), never card index;
  the resolved name is logged at startup.

Playback shells out to `pw-play` (PipeWire default sink, the puck).
`config.AUDIO_OUTPUT_DEVICE` is inert. STT is faster-whisper `base.en` on 3 CPU threads;
TTS is Piper `en_US-amy-medium`.

### 6.5 Front obstacle fusion (DFRobot SEN0628)

**As built:** `tof.py` reads the sensor, `sensors.py::SonarArray.distances` fuses it,
`scripts/calibrate_tof_floor.py` captures the floor profile. `ENABLE_TOF=True`.

**Transport.** `SerialFrameSource` speaks the DFRobot MatrixLidar protocol on
`/dev/ttyAMA3` (`uart3-pi5`) at 115200: request `[0x55][argsNumH][argsNumL][cmd][args]`
with `argsNum = len(args)+1`; reply `[status][cmd][lenL][lenH][payload]`, `0x53` success,
`0x63` failed, `0xFF` filler; payload 64 little-endian uint16 mm (4000 = invalid). The
sensor is strictly request/response and never streams. `BackgroundFrames` polls it on its
own thread every `TOF_POLL_S` (0.05 s; a frame takes ~0.13 s); the tick reads the newest
frame, and a frame older than `TOF_FRAME_MAX_AGE_S` (0.5 s) is no frame.

**Fusion.** `distances['front']` is the minimum of the sonar reading and the nearest ToF
zone **reporting an obstacle**. A zone counts only when it returns more than
`TOF_FLOOR_MARGIN_MM` (120 mm) shorter than its stored per-zone floor distance; a zone
returning more than the margin longer (or nothing) where floor is expected is a **drop**,
which sets `front` to 0.0 so every forward gate stops. The ToF is the only drop detector.
Sides are sonar only. `DIST_STOP`/`SLOW`/`CLEAR`, `_roam()`, `_slow()` and `_avoid()` see
the same dict key and do not know the ToF exists.

**Uncalibrated reports nothing.** Without a profile (`tof_floor_profile.json`, 64 values
averaged over `TOF_PROFILE_SAMPLES` frames on clear floor) the sensor contributes nothing,
rather than making the floor a permanent obstacle. **No profile has been captured yet**
(§12), so today the ToF adds nothing to `front`. Re-run the calibration after any bracket
change or for a different floor surface.

**This is the one stateful input to the reflex layer.** A stale profile degrades
detection; the failure direction is phantom obstacles (he stops for nothing), not
blindness.

**The ToF may live in the reflex layer and vision may not:** deterministic timing,
variable-latency NPU.

**ToF unavailability is not a fault.** A wedged UART or the sensor's RP2040 resetting
means `distances()` returns sonar alone and logs it — it must not raise and must not route
through `SENSOR_FAULT`. An exception inside the fusion is caught and logged.

**This rule does not extend to Pico B.** It holds only because the ToF is purely
additive. The sonar itself is behind a UART; for Pico B, stale means stop (S-9).

### 6.6 Stair standoff (FR-1200-005)

Hold `STAIR_STANDOFF_M` = 0.15 m from a mapped stair edge while in `floor` mode.
`config.MOBILITY_MODE='floor'` is the only mode; there is no `stair` mode and no
selector, so the standoff always applies. Mobility modes are a capability gate, not FSM
states.

**Labelling.** Voice (*"stairs ahead"*, intent `mark_stairs`) records a
`world_model.Stair` **edge**: centre `STAIR_LABEL_AHEAD_M` (0.30 m) ahead of the rover,
across its heading, `STAIR_DEFAULT_WIDTH_M` (0.9 m) wide, persisted in `world_model.db`
(`STAIR_LABELLED` event). The camera does not detect stairs.

**Planning front.** When ROAM / SLOW / AVOID decide,
`brain.py::_stair_planning_front(d)` casts a ray along the odometry heading
(`world_model.ray_to_segment()`); the nearest edge hit at distance *t* becomes a planning
front `(t − STAIR_STANDOFF_M) × 100 + DIST_STOP` cm, used in place of the sonar front for
that decision only. Forward only. `d`, `approve_motion()`, the world model and
`mapping.tick()` see the sonar alone.

**Deliberative, deliberately.** The standoff is arithmetic on a mapped position against a
dead-reckoned pose (odometry, optionally IMU heading). It informs planning; it never stops
the rover. The stop stays with the reflex layer (the ToF drop check, §6.5).

**It fails closed.** With stairs on the map and a stale pose, or an exception reading
them, `_roam()` stops and returns to IDLE with the reason on the face, and `_avoid()`
treats the front as blocked.

| Input | Job | Layer |
|---|---|---|
| Voice labels + map | Where the stairs are | Deliberative |
| Vision (camera 15° down) | Nothing yet — stair candidates from the camera are not built | Deliberative |
| SEN0628 multi-zone ToF | The drop detector | **Reflex** |

No scanning lidar is fitted or planned. The 15 cm margin is only as good as the
dead-reckoned pose (§12).

### 6.7 Which functions may use which reasoner

#### 6.7.1 The model's self-reported confidence never authorises a physical action

Permanent. Over 96 measured calls the model's self-reported confidence had the same
distribution for correct and wrong answers and never went below 0.8 — it carries no
information. Therefore:

- Do **not** raise or lower `HAILO_LLM_CONFIDENCE_FLOOR`.
- Do **not** add a second confidence threshold anywhere.
- Do **not** use the model's self-reported confidence to authorise a physical action.

`HAILO_LLM_CONFIDENCE_FLOOR` (0.7) is compared against `action_confidence`, a binary
structural check, not against the model's number. The voice path reads the model's
number (`LOCAL_LLM_CONFIDENCE_FLOOR` 0.55), but `voice.py::_interpret_local()` returns
0.0 for an answer that fails to parse or names an intent outside `_ACTIONABLE_INTENTS`, so
those escalate regardless. A wrong but valid intent still passes on the self-report.

#### 6.7.2 Tiers

**The model may recommend an action; it must never be the authority that makes the
action safe.**

**Tier A — deterministic only.**

| Function | Mechanism |
|---|---|
| Emergency stop by voice | `voice.py::is_emergency_stop()`, fullmatch with negation guard |
| Operator stop button | `brain.py::_tick()` polls it before any state handler |
| Tilt cutoff, sensor-fault stop | reflex layer, `safety.py` |
| Obstacle reflex (`DIST_STOP`) | sonar + ToF, `sensors.py` → `safety.py` |
| Duration and speed clamps | `safety.py`, every request regardless of source |

**Tier B — a model may propose; deterministic logic disposes.**

| Function | Who decides | Who authorises |
|---|---|---|
| STUCK recovery action | Hailo (primary), Claude (fallback) | `_action_confidence` + `safety.request()` clamps |
| retrieve / come_here / follow | intent from a model | `safety.py`, plus vision ranging (uncalibrated) |
| arm presets | intent from a model | `arm.py` limits plus the INA260 0x44 current guard |

**Tier C — a wrong answer is cheap.** `status`, `battery`, `where_are_you`,
`what_do_you_see`, `time`, `date`, conversation, feature-request composition. Most are
claimed by `_fast_path()` before any model runs.

#### 6.7.3 Hailo versus the CPU model

Same 32-case benchmark, same prompt and schema:

| | Actionable | Median latency |
|---|---|---|
| Hailo NPU (`qwen2:1.5b`) | 80.2% | 4.86 s |
| CPU `LocalAIProvider` | 96.9% | 24.95 s |

On the cases Hailo got confidently wrong, the CPU model got all right. The NPU buys
latency, not intent reliability. `ENABLE_HAILO_LLM=True`; whether to keep it on is the
owner's call (§12).

#### 6.7.4 What would change this

A more capable on-device model, or moving specific failing intents off the model
entirely — as `stop` is. Not a better prompt and not a better threshold.

---

## 7. Perception and the Accelerator

**Vision runs on the Hailo-10H NPU.** `vision.py`'s `ObjectDetector` uses a Hailo YOLOv8m
backend (`/usr/share/hailo-models/yolov8m_h10.hef`) via `picamera2.devices.Hailo`, on the
CSI imx708 front camera through `picamera2` (`ENABLE_HAILO_VISION=True`). If that backend
fails to load (simulation, missing model, any exception) vision is **disabled** — there is
no automatic fallback. A CPU `ultralytics` backend against the rear USB camera
(`CAMERA_DEVICE` `/dev/video8`) exists in the code and runs only when
`ENABLE_HAILO_VISION=False` and `ENABLE_OBJECT_RETRIEVAL=True`; both conditions are off.

**Device sharing.** The Hailo-10H `VDevice` is exclusive to one process.
`picamera2.devices.Hailo` keeps a class-level `Hailo.TARGET` singleton; `hailo_llm.py`
reuses it (a separately constructed `VDevice()` fails with
`HAILO_OUT_OF_PHYSICAL_DEVICES`), and increments `TARGET_REF_COUNT` only after `LLM()`
succeeds. Anything that needs the NPU outside `willy-rover.service` (`hailortcli`,
scripts) requires the service stopped.

`detect()` returns class, confidence, box, frame size, timestamp and camera id.
`localize()` gives bearing from pixel offset and range from box width against a nominal
per-class width (`_CLASS_WIDTH_CM`: person 45 cm, 8 cm fallback). Both are heuristics;
focal length and HFOV are unmeasured and the camera's 15° tilt is not modelled. Real
ranging is the ToF's job at the reflex layer; do not fuse ToF zones into `localize()`.
Perception feeds `world_model.py` for planning only (Master Hardware Design §12 rule 15).

`capture_frame()` supplies BGR frames to face recognition, under the same privacy gate.

**Hailo LLM.** `hailo_llm.py::HailoIntentModel` (`ENABLE_HAILO_LLM=True`) runs
`hailo_platform.genai.LLM` with `qwen2:1.5b` (`models/hailo_qwen2_1_5b.hef`),
temperature 0.1, top-p 0.9, 256 max tokens. **The prompt must be ChatML-framed**
(`hailo_llm.py::_chatml`) — `generate_all()` does not apply the chat template, and an
unframed prompt makes the model echo the template. `ai_provider.py::_normalise_payload`
drops placeholder `args` values; prompts carry no angle-bracket placeholders.

**Hailo STT** (`hailo_stt.py`, `ENABLE_HAILO_STT=False`) is scaffolding only: it needs a
Whisper HEF compiled on an x86 machine (the Dataflow Compiler does not run on ARM).

---

## 8. Known Gaps

Numbered S-1 to S-10 so other documents can cite them.

**S-1 — Emergency stop.** The main power switch. It cuts all power including the Pi; there is no separate E-stop and no sense input. FR-300-001 is satisfied by design.
`_check_motor_rail()` watches the +12V bus monitor (INA260 0x45) for the collapse a SW-M
cut produces, logs it and shows it on the face; detection only. Rail identities: **0x40 =
R2 5V, 0x44 = R3 6V arm, 0x45 = +12V bus** (`INA260_5V_ADDR`, `INA260_ARM_6V_ADDR`,
`INA260_BUS_12V_ADDR`, rail keys `steering_5v`, `arm_6v`, `bus_12v`);
`tests/test_motor_rail_identity.py` pins them. The arm-rail collapse a SW-A cut produces is
readable on 0x44 but not monitored.

**S-2 — Encoder sampling. Closed by Pico A.** Decode is in PIO on Pico A, signed ×2 (both
edges of Phase A, Phase B sampled at each), 763 counts per wheel revolution; the Pi reads
`$E` frames at 50 Hz over `uart4-pi5`. There is no I²C polling of encoder lines. Do not
use interrupt-driven decode or `GPIO.add_event_detect()` on the Pi.

**S-3 — Odometry constants.** `ENCODER_COUNTS_PER_REV` = 763 (measured under power, one
wheel: 381.6 ×1, doubled for ×2). `WHEEL_DIAMETER_M` = 0.1016 and `TRACK_WIDTH_M` = 0.310
are owner-measured off the chassis; the effective rolling diameter under load and the
other five wheels' scale have not been checked by driving a measured distance (§12).
`ENCODER_SIGN` (left +1, right −1) is applied in `odometry.py`; `Encoders.counts` stays
raw (unwrapped across 32 bits, re-based on a Pico reboot). Rotation can come from the IMU
yaw delta (`ODOM_USE_IMU_HEADING`, **False** until the yaw sign is checked; `IMU_YAW_SIGN`).
`IMU.heading` uses the BNO085 ROTATION_VECTOR report, which is magnetometer-referenced.
Do not calibrate counts per revolution by hand-turning a wheel — the hub slips on the
shaft when back-driven; `scripts/encoder_calibration.py` is invalid on this rover.

**S-4 — No inverse kinematics for the arm.** No per-joint calibration exists, so there is
no reach-envelope model. Grasp is a fixed primitive sequence. `arm_jog.py` is the tool.

**S-5 — Hand-off confirmation is timed, not sensed.** The FSR402 was removed 2026-10-04.
The gripper servo's pot wiper now feeds ADS1115 A2 through a 47k/47k divider (Master
Hardware Design §6.6), and `sensors.ADC.grip_feedback_volts()` reads it on demand. Nothing
consults it yet: `retrieval_task.py` releases on a timeout and logs that there is no
confirmation. Closing it needs the free-travel curve from `scripts/grip_feedback_curve.py`,
then `_await_confirm()` treating "jaw jumped back to its commanded position" as taken.

**S-6 — No systemd watchdog.** `willy-rover.service` has no `WatchdogSec` (the line is
commented out). It must not be added as-is: the unit is `Type=simple`, so systemd discards
`sd_notify` messages and the watchdog would fire unconditionally; and startup (loading a
~1.7 GB Hailo HEF and the voice models) takes seconds. Arming it needs `Type=notify` (or
`NotifyAccess=main`) and `TimeoutStartSec`/`WatchdogSec` matched to measured startup.
`willy-rover-watchdog.service.prepared` holds a prepared variant, not installed.
`brain.py` still sends `READY=1` and `WATCHDOG=1`; the Witty Pi 5 hardware watchdog is the
live one. Tick-serviced step machines (grasp, wave) keep any single tick short.

**S-7 — Stall and overcurrent.** `_check_stall()` checks each commanded wheel
(`DriveBase.commanded`) every tick; near-zero counts past `STALL_GRACE_S` (1.0 s) →
`emergency_stop()`, `MOTOR_STALL`, `STALL_FAULT`. `_check_overcurrent()` trips per rail
(`OVERCURRENT_LIMIT_A`, 90% of the 10 A F2/F4 fuses) → `OVERCURRENT`, latched
`OVERCURRENT_FAULT`. The arm rail has `ARM_CURRENT_LIMIT_A` → release. Rail-level, not
per-motor. The inverse — counts with nothing commanded — is `UNCOMMANDED_MOTION`.

**S-8 — Smart home and remote commands.** Outbound: `smart_home.py` sends commands to
devices through Home Assistant's REST API (`discover_devices`/`send_command`);
`ENABLE_SMART_HOME=False`. Inbound: `remote_cmd.py` (`ENABLE_REMOTE_CMD=True`) serves
`POST /command` on `REMOTE_CMD_PORT` 8765 with a Bearer token from
`secrets/remote_cmd_token.txt` (no file → no server). Fixed intents `status`, `battery`,
`stop`, `come_here`; JSON body `{"intent": ...}`. `stop` sets `voice.stop_requested`; the
others go on `voice.pending_commands` with `source='remote'` and an `on_reply` callback, so
all Directive gating applies and `brain._say()` returns the answer as the HTTP reply
(within `REMOTE_CMD_REPLY_TIMEOUT_S`, 8 s) for Home Assistant to speak on a Nest. Home
Assistant runs in Docker on willie, exposed through Tailscale Funnel; the Google Assistant
link is not finished (§12). `tests/test_remote_cmd.py`.

**S-9 — Sonar staleness means stop.** Pico B emits `-1` for an unmeasurable channel,
never a distance, with a per-channel age and a sequence number per frame.
`pico_link.py` never invents a value for a missing frame. A `$S` frame older than
`SONAR_STALE_S` (0.30 s) makes sonar UNKNOWN, which means stop; a fresh `-1` means
"pinged, heard nothing" and reads as `SONAR_MAX_CM` (400). `safety.py`'s `front_cm`
defaults to 0.0. Per-channel failure is reported as `SONAR_FAULT`.

**S-10 — Encoder transport.** `sensors.Encoders` reads Pico A over `uart4-pi5`
(`/dev/ttyAMA4`) through `pico_link.py`. Wheel order lives in one place,
`firmware/pico_a.py`'s `WHEELS`, and arrives in the frame. Frames older than
`ENCODER_STALE_S` (0.20 s) make the encoders unknown, and every wheel then reads as
stalled. Pico A also reports R5 (the encoders' 3.3 V rail) from its own ADC in every
frame and flags it below 3.0 V.

---

## 9. Logging and Diagnostics

`logsetup.log_event(logger, event, severity, **fields)` emits a greppable
`EVENT=<name>` tag at real fault and abort sites only.

| Event | Source |
|-------|--------|
| `IMU_FAULT`, `ENCODERS_FAULT`, `CURRENT_FAULT`, `BATTERY_ADC_FAULT` | `brain.py::_check_health()` (carry `value=`, `expected=`) |
| `LOW_BATTERY` (`warn` / `return_to_home` / `low_battery_halt` / `safe_mode` / `shutdown`), `BATTERY_HALT` | battery tiers, `_battery_halt()` |
| `OBSTACLE_STOP` | `safety.py` mid-flight abort |
| `NAVIGATION_ABORT` | `Navigator.abort()` |
| `AI_TIMEOUT` | `ai_provider.py`, on a real `TimeoutError` |
| `TICK_OVERRUN` | `_record_tick_duration()` |
| `MOTOR_STALL` | `_check_stall()` |
| `OVERCURRENT`, `ARM_OVERCURRENT` | `_check_overcurrent()`, `_check_arm_current()` |
| `SONAR_FAULT` | `_check_sonar_channels()` |
| `UNCOMMANDED_MOTION` | `_check_uncommanded_motion()` |
| `STAIR_LABELLED` | `mark_stairs` intent |
| `COMMANDED_SHUTDOWN` | `stop()` tail, before `shutdown -h now` |
| `EMAIL_COMMAND` | `email_client._handle_command()` (refused_dkim / refused_stale / approve_* / allowlist_* / accepted), `brain._email_command()` (queued) |
| `FEATURE_REQUEST` | `feature_requests.py` (proposed / approved) |
| `IDENTITY` | enrolment, approval, forget-everyone. Strangers are never logged |
| `DEMO` | demonstration record / save / replay |

Untagged: `WATCHDOG_FAULT` (a killed process cannot self-log).

`diagnostics.py` is a standalone read-only self-test. It never imports `motors`,
`steering` or `arm`, so it is safe to run mid-assembly, and reports an itemised table.
`tests/test_expected_i2c_agreement.py` keeps its expected bus identical to `brain.py`'s.

---

## 10. Testing

All off-hardware under `WILLY_SIMULATE=1`. **CI (2026-10-07):** `.github/workflows/tests.yml`
runs `compileall` and the full suite on every push and pull request (Ubuntu, Python 3.13, only
pytest/numpy/networkx/pygame-ce/scipy/smbus2 installed); failures are published as annotations,
which the public API returns without a login. First green run: 520 passed on `3a288d5`. The
first runs found code that imported rover-only modules at the top (`hailo_llm` via `brain`,
`board` in `diagnostics`) and a direct `DriveBase.brake()` — all fixed. The suite's other home
is willie.On the Windows dev box a subset fails for environment reasons only (no
`board` module, Windows file locking on temp SQLite files, no `socket.AF_UNIX`, no real
`picamera2` Hailo class).

Off-hardware execution needs `WILLY_SIMULATE=1` plus `pygame` and `networkx`.
`config.SIMULATE_HARDWARE` gates every real I²C/GPIO/UART open; `hw_sim.py` supplies
`SimMotor` and `SimServoBank` with unchanged interfaces. `display.py`'s pygame/Wayland
init is not covered by the gate; it fails non-fatally in its own thread under simulation.

Untestable by design: encoder rollover (counts are unbounded Python ints).

### 10.1 What the tests protect

| Area | Files |
|---|---|
| Layering and safety boundary | `test_no_direct_drive_bypass.py`, `test_reflex_deliberative_separation.py`, `test_safety.py`, `test_safety_controller.py`, `test_emergency_stop_phrases.py`, `test_malformed_model_output.py`, `test_confidence_gate_semantics.py`, `test_stuck_ai_fallback_chain.py` |
| Hailo | `test_hailo_chatml.py`, `test_hailo_statelessness.py`, `test_hailo_generation_params.py`, `test_hailo_device_sharing.py`, `test_ai_provider_normalisation.py`, `test_stuck_prompt.py` |
| Startup and health | `test_sd_notify.py`, `test_expected_i2c_agreement.py`, `test_selftest_i2c_probe.py`, `test_brain_voice_selftest_fault.py`, `test_brain_reset_gate.py`, `test_sensor_gaps.py`, `test_motor_rail_identity.py` |
| Battery | `test_battery_plausibility.py`, `test_battery_crosscheck.py`, `test_battery_halt.py`, `test_current_limits.py` |
| Drive | `test_wheel_speed_control.py`, `test_brake_no_twitch.py`, `test_encoder_order.py` |
| Sensing | `test_tof.py`, `test_sonar_tof_fusion.py` |
| Features | `test_remote_cmd.py`, `test_email_commands.py`, `test_feature_requests.py`, `test_demonstrations.py`, `test_identity_store.py`, `test_face_recognition_flow.py`, `test_rooms_stairs_memory.py`, `test_retrieve_gate.py`, `test_voice_tone.py`, `test_brain_voice_drain.py` |

A repo-wide check for an old prompt literal is an AST scan, because docstrings quote the
literal deliberately.

---

## 11. Configuration

`config.py` holds every tunable, address and pin map. Credentials are never in it — only
environment-variable names and file paths.

`config.validate()` runs at startup and returns a list of problems rather than raising.
It checks battery ladder ordering (`SHUTDOWN < SAFE < RTH < WARN`), `BAT_FULL_V` against
`BAT_WARN_V`, hysteresis positivity, and that `AUDIO_INPUT_RATE` is a multiple of 16000.

Feature flags on: `ENABLE_CLOUD_AI`, `ENABLE_EMAIL`, `ENABLE_EMAIL_COMMANDS` (the kill
switch if the owner's Gmail is ever suspected compromised), `ENABLE_FEATURE_REQUESTS`,
`ENABLE_FACE_RECOGNITION` (inert if `models/` lacks the YuNet/SFace files),
`WHEEL_SPEED_CONTROL`, `ENABLE_TOF`, `ENABLE_REMOTE_CMD`, `ENABLE_HAILO_VISION`,
`ENABLE_HAILO_LLM`, `ENABLE_WITTY_PI`, `ENABLE_VOICE`, `ENABLE_LEARNING`,
`ENABLE_STUCK_ALERT_EMAIL`, `ENABLE_AUTONOMOUS_ROAM` (= allowed to ask, §3.1.1).

Flags off: `ENABLE_DOCKING`, `ENABLE_SMART_HOME`, `ENABLE_RETRIEVAL_TASK`,
`ENABLE_OBJECT_RETRIEVAL`, `ENABLE_HAILO_STT`, `ODOM_USE_IMU_HEADING`.

**STUCK help-photo alert** (`ENABLE_STUCK_ALERT_EMAIL`): on entering `STUCK` he emails the
owner a front-camera photo with pose, sonar and battery context — the one outbound mail
without a confirmation step, only to `EMAIL_OUTBOUND_ALLOWLIST[0]`, at most once per
`STUCK_ALERT_COOLDOWN_S` (600 s) and `STUCK_ALERT_MAX_PER_SESSION` (5).

---

## 12. Open Items

Bench procedures with blank result fields are in `docs/WildWilly_Bench_Test_Procedures.md`.

1. **Not yet run on the rover** (simulated only): battery halts and `LOW_BATTERY`; the
   overcurrent, arm-current, sonar-channel and uncommanded-motion checks; closed-loop wheel
   speed and the mph speeds; stair labelling and the planning front; pursuit search;
   retention sweep; email commands; feature requests; face recognition and enrolment;
   demonstrations; voice fast-path additions and tone; the self-test voice drain and
   base-off message; the per-class vision widths; the remote-command fix that keeps remote
   commands from answering a pending ask.
2. **ToF floor profile not captured.** Run `scripts/calibrate_tof_floor.py` on clear floor;
   until then the ToF contributes nothing.
3. **Odometry scale** — drive a measured straight line; confirm the rolling diameter and
   the other five wheels' counts per revolution (S-3).
4. **IMU yaw sign** — turn left on the spot, confirm odometry heading and `IMU.heading`
   both increase (else `IMU_YAW_SIGN=-1`), then consider `ODOM_USE_IMU_HEADING=True`. The
   BNO085 report rate is ~5 Hz, cause unknown.
5. **Stair standoff drift** — measure dead-reckoning drift on the floor before relying on
   the 15 cm margin.
6. **Arm per-joint limits** — run `arm_jog.py` and record real limits (S-4); identify what
   CH3 does alone.
7. **Gripper feedback curve** — run `scripts/grip_feedback_curve.py` empty and loaded, store the
   curve, consult it in `RetrievalTask._await_confirm()` (S-5).
8. **Steering** — steering servos are centred and held; kinematics (crab, point-turn,
   arc) are deferred. Skid steer is the only turning mechanism (`motors.py::Steering`).
9. **Overcurrent limits** — the 9.0 A `bus_12v` limit is 90% of the fuse, not measured against
   real load. (The `steering_5v` limit was dropped 2026-10-08: its monitor cannot see steering
   current; the F4 10 A fuse protects that rail.)
10. **Hailo LLM** — `ENABLE_HAILO_LLM=True`; it labels some intents with synonyms
    (`fetch`, `halt`) at high confidence. Whether to keep it on is the owner's call (§6.7.3).
11. **systemd watchdog** — not armed (S-6).
12. **Witty Pi heartbeat** — whether the register-read heartbeat satisfies the HAT's
    watchdog is unconfirmed on the device.
13. **`ADC.is_charging` is hardcoded `False`** (charge-sense divider not wired). Its two
    callers are in `DOCK` handling, including a `safety.stop()` that cannot execute; both
    are dormant while `ENABLE_DOCKING=False`.
14. **Google Assistant link** to Home Assistant not finished (S-8).
15. **rf motor disconnected** — its `WHEEL_FF` entry is a default, not a fitted line;
    re-run `scripts/breakaway_sweep.py` with it connected.
16. **Boot clock** runs about a week ahead until NTP syncs (Witty Pi RTC suspected); log
    timestamps before sync, `feature_requests.py`'s evidence window and the backup timers
    are affected.

---

*End of document.*

---

## Arm control

`arm.py` rests on three facts measured on the hardware.

**1. The channel map.** Wrist pitch CH0, elbow CH1, shoulder CH2, second shoulder axis
CH3, wrist rotate CH4, gripper CH5, base yaw CH6, CH7 unused. `_JOINTS` uses
`ARM_SHOULDER` (CH2) as `'shoulder'`.

**2. No mirrored-pair derivation.** `set_pulse()` is a plain clamped write
(`ARM_SERVO_MIN_US` 500 – `ARM_SERVO_MAX_US` 2500); every joint is independent. **Do not
reinstate `shoulder_b = 2*ARM_SERVO_CENTER_US - shoulder_a`.** CH2/CH3 are not one axis,
and at the 750 µs wave position the derivation would command CH3 to 2250 µs.

**3. Never centre the elbow (CH1).** `ARM_SERVO_CENTER_US` (1500 µs) drives it into the
top of the chassis. `center_all()` skips it.

**Rules.**
- **Open the elbow before moving the shoulder**, or the arm strikes the top of Willy.
- Step the shoulder in `ARM_WAVE_APPROACH_STEP_US` (50 µs) steps; a single jump slams it.
- Shoulder: decreasing µs raises. Gripper: increasing µs closes (contact from ~1700 µs).
  Grip force is set by current, not position: stop feeding past ~0.4–0.5 A.
- Holding a pose is nearly free (~0.33 A for the wave pose); moving costs amps.
- **A released arm falls.** `release()` (PCA9685 SLEEP) makes every arm channel limp.
  Idle release happens after `ARM_RELEASE_AFTER_S` (10 s) with `ARM_RELEASE_WHEN_IDLE=True`.

**Current guard.** `brain.py::_check_arm_current()` samples the arm rail (INA260 0x44)
every tick (~20 Hz) and, above `ARM_CURRENT_LIMIT_A` (2.5 A) for `ARM_CURRENT_LIMIT_S`
(0.4 s), calls `arm.release()`, logs `ARM_OVERCURRENT` and says so. It must run while the
arm moves: sampling after a move reads idle current, and a threshold checked after a move
protects nothing. Settled current is what matters — a joint at position relaxes to
0.05–0.4 A; one that stays higher is still fighting.

**Presets.** `ARM_POSE_WAVE_HELLO` = elbow 1000, shoulder 750, wrist pitch 1500.
`ARM_POSE_REST` = elbow 2610 (clamped to 2500 by `arm.py`; ~2530 is the real limit),
shoulder 2010, wrist pitch 2450 (draws a sustained 0.87 A; 2300 holds the same shape at
0.23 A, `ARM_REST_WRIST_US`).

**Wave** (`brain.py::_wave_plan`): elbow to 1000, shoulder stepped to 750, wrist pitch
oscillated between `ARM_WAVE_WRIST_US` (1380/1620) for `ARM_WAVE_CYCLES` (4) at
`ARM_WAVE_LEG_S` (0.35 s), then shoulder stepped back to 2010, elbow to 2500, wrist pitch
to 2300. Non-blocking, one step per tick deadline.

`arm_stow`, `arm_home` and shutdown call `center_all()`; no calibrated stow pose exists.

**Diagnosis.** A current trace describes the motor, never the arm. Before interpreting a
trace, check whether the joint physically moved. `arm_jog.py` is the calibration tool
because a human watches it.
