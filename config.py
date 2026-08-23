# WildWilly Rover — Central Configuration v2
# 180x125mm chassis · 5" 800x480 landscape display

import os,storage
# §19 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: every hardware-backed class in
# motors.py/sensors.py/arm.py checks this at construction time and, when set, skips opening real
# I2C/GPIO/SPI entirely in favor of an in-memory simulated stand-in with the same public
# interface — this is what lets brain.py (and everything built on it) import and run off the
# physical rover, per §20's testing requirements. Default OFF: the real hardware path is
# unchanged unless this is explicitly requested.
SIMULATE_HARDWARE=os.environ.get('WILLY_SIMULATE','0')=='1'

# §13: configurable storage roots — see storage.py's module docstring for why the *default*
# (unset env var) anchors to the repo directory rather than the process's CWD, and why this unit
# doesn't yet split these across a real SSD/SD (no such split physically exists here — confirmed
# 2026-08-08, boot-from-SSD is still a pending item per the master doc §13.4). Setting an env var
# overrides that tier's location with zero further code changes whenever that migration happens.
WILLY_DATA_ROOT=storage.resolve_root('WILLY_DATA_ROOT','.')      # operational/working files root
WILLY_MAP_ROOT=storage.resolve_root('WILLY_MAP_ROOT','.')        # world_model.db lives here (§9)
WILLY_MEMORY_ROOT=storage.resolve_root('WILLY_MEMORY_ROOT','.')  # memory.db lives here (§FR-1900)
WILLY_LOG_ROOT=storage.resolve_root('WILLY_LOG_ROOT','logs')     # logsetup.py's rotating file dir

DISPLAY_W=800; DISPLAY_H=480; DISPLAY_FPS=30; DISPLAY_ROTATE=0

# Drive — 2x Adafruit FeatherWing #2927 MotorKit boards over I2C (§9, §1.3 master doc).
# Replaces the old GPIO H-bridge pins (freed — no discrete driver chip, no direction/PWM GPIO).
MOTORKIT_LEFT_ADDR=0x60; MOTORKIT_RIGHT_ADDR=0x61
MOTOR_PORT={'lf':(MOTORKIT_LEFT_ADDR,1),'lm':(MOTORKIT_LEFT_ADDR,2),'lr':(MOTORKIT_LEFT_ADDR,3),
            'rf':(MOTORKIT_RIGHT_ADDR,1),'rm':(MOTORKIT_RIGHT_ADDR,2),'rr':(MOTORKIT_RIGHT_ADDR,3)}
SPEED_ROAM=0.55; SPEED_TURN=0.50; SPEED_SLOW=0.35; SPEED_MAX=0.80
SPEED_RAMP_PER_S=2.0  # FR-400-003: max throttle change per second (slew rate), full range in 0.5s
TURN_INNER_SCALE=0.0

# Sonar (§8.1 master doc) — FRONT_ECHO/LEFT_ECHO were wired to GP11/GP19 here, which do not match
# the documented harness (GP26/GP14) and aren't connected to anything real — front/left obstacle
# detection has likely been silently reading 999cm (no obstacle) on every call. Fixed 2026-08-02.
SONAR_FRONT_TRIG=5;  SONAR_FRONT_ECHO=26
SONAR_LEFT_TRIG=13;  SONAR_LEFT_ECHO=14
SONAR_RIGHT_TRIG=4;  SONAR_RIGHT_ECHO=21
SONAR_TIMEOUT=0.025; SONAR_SAMPLES=3; SONAR_INTERVAL=0.05
DIST_STOP=20; DIST_SLOW=40; DIST_CLEAR=60; DIST_SIDE_CLEAR=25

IMU_ADDR=0x4A; IMU_TILT_LIMIT=25; IMU_TILT_WARN=18; IMU_POLL_HZ=100  # BNO085, §8.2/§8.5
# RST wired to MCP23017 (§9.1's same chip, ENCODER_ADDR) port B bit 4 — confirmed 2026-08-08
# (previously only documented as "spare pin", no bit number). MCP230xx get_pin() numbering is
# 0-7=port A, 8-15=port B, so B4 -> pin index 12. Doesn't collide with any ENCODER_PINS bit
# (bank B only uses bits 0-3 there).
IMU_RST_MCP_PIN=12

# Steering — PCA9685 @0x42, CH0-5 (§3.1/§10). Servo mode (500-2500/1000-2000/900-2100us) is
# unconfirmed per-unit — default to the narrowest documented range so a narrow-mode servo can't
# be driven into a mechanical bind. Widen only after a bench check confirms a unit's real range.
# Steering kinematics (wheel-angle coordination, crab/point-turn) are undesigned in the master
# doc (§10: "pending in software") — this pass only centers all six and holds them there.
STEER_PCA_ADDR=0x42
STEER_LF=0; STEER_RF=1; STEER_LM=2; STEER_RM=3; STEER_LR=4; STEER_RR=5
SERVO_CENTER_US=1500; SERVO_MIN_US=1000; SERVO_MAX_US=2000
SERVO_PWM_FREQ=50

# Arm — PCA9685 @0x43, CH1-7 (CH0 unused), base->gripper order (§11.1). J1a/J1b (shoulder) are a mirrored
# pair driving one physical axis — see arm.py. Wider nominal range than steering (manufacturer
# spec 500-2500us) though §11.5/§20.6 flag cheap-clone units may bind before the full sweep.
# No per-joint safe limits, presets, or IK exist yet pending §20.6 bench calibration — arm.py is
# a driver + manual jog tool only this pass, not autonomous motion.
ARM_PCA_ADDR=0x43
# Channels shifted +1 (2026-08-21, owner's physical rewiring): CH0 left unused, joints now on
# CH1-7 rather than CH0-6.
ARM_BASE=1; ARM_SHOULDER_A=2; ARM_SHOULDER_B=3; ARM_ELBOW=4
ARM_WRIST_ROT=5; ARM_WRIST_PITCH=6; ARM_GRIPPER=7
ARM_SERVO_MIN_US=500; ARM_SERVO_MAX_US=2500; ARM_SERVO_CENTER_US=1500

# Wheel encoders — MCP23017 @0x27 (§9.1), quadrature A/B per wheel. counts/rev is a "starting
# value" from the motor listing, not bench-confirmed.
ENCODER_ADDR=0x27
ENCODER_PINS={'lf':('A',0,1),'lm':('A',2,3),'lr':('B',0,1),
              'rf':('A',4,5),'rm':('A',6,7),'rr':('B',2,3)}
ENCODER_COUNTS_PER_REV=3292  # §9.2: 823.1 PPR x4 quadrature decode

# G-2 (FRD v3.1 §V.2): interrupt-driven decode, chosen 2026-08-18 over a dedicated hardware
# counter or accepting encoders as stall-only. HARDWARE PREREQUISITE, NOT YET WIRED: the
# MCP23017's INTA pin (physical chip pin 19) must be connected to this Pi GPIO -- IOCON.MIRROR
# (set in sensors.py::Encoders.__init__) combines both ports' interrupts onto INTA/INTB
# identically, so only one of the two physical INT pins needs a wire; INTB can stay unconnected.
# GP7 was chosen as the first of CLAUDE.md's documented free pins (GP7, GP8-11). Until this is
# physically wired, the interrupt callback simply never fires and Encoders falls back entirely
# on the periodic heartbeat poll -- same best-effort behavior as before this change, not a
# regression while the wiring is pending.
ENCODER_INT_PIN=7

# Odometry (§8, WildWilly_Claude_Fix_Implementation_Plan.md). UNCONFIRMED: the master doc gives
# only the overall chassis envelope (430x330x220mm, §2), never a wheel diameter or track (L/R
# wheel-center spacing) measurement — these two values are placeholder estimates derived from
# that envelope, not a bench/caliper measurement. odometry.py's pose output is dead-reckoning
# only (no slip correction, no fusion with the IMU heading) and will drift; re-measure these two
# values directly off the chassis before trusting distances/headings for anything beyond rough
# relative dead-reckoning.
WHEEL_DIAMETER_M=0.065  # UNCONFIRMED placeholder
TRACK_WIDTH_M=0.28      # UNCONFIRMED placeholder — center-to-center of left/right wheel tracks
POSE_LOG_INTERVAL_S=5.0 # brain.py logs the current odometry pose at most this often
TICK_OVERRUN_THRESHOLD_S=0.15 # brain.py::run() logs+counts a TICK_OVERRUN when a single _tick()
                              # call takes longer than this (loop targets ~50ms sleep + tick time) --
                              # 2026-08-08 audit P1, pure visibility regardless of whether systemd's
                              # WatchdogSec ends up catching a hung loop on its own -- see brain.py's
                              # RoverBrain.__init__ comment for the unreconciled repo-vs-live-unit
                              # WatchdogSec=500ms discrepancy found 08-08, still unresolved.
                              # Raised from 0.1 2026-08-09 after this ran live for the first time:
                              # a sustained-brake state (battery shutdown/tilt/sensor fault) makes
                              # safety.py::emergency_stop() call motors.py::brake() every tick, which
                              # is 6 real per-wheel PCA9685 I2C writes -- that alone measured
                              # 100-134ms live (py-spy confirmed the cost is in
                              # adafruit_pca9685.duty_cycle's I2C write, not a bug). That write is
                              # intentional (safety.py's own comment: must reassert every tick to
                              # survive a noise-flipped register) so the threshold moved up to match
                              # real cost instead of the write being removed. Still tight enough to
                              # catch a genuine hang well above this range.
ESTOP_LOG_INTERVAL_S=5.0 # safety.py throttles emergency_stop()'s own log line to at most this
                          # often — the brake() call itself still fires every tick unconditionally,
                          # only the logging is throttled (found 2026-08-08: a sustained fault/tilt/
                          # battery-shutdown condition calls emergency_stop() every tick for as long
                          # as it persists, which had been flooding the log at ~20Hz with no limit —
                          # same class of bug as 516d1ec's memory.save_all_now() fix, just for a
                          # log line instead of a disk write, and missed by that pass since it lives
                          # in safety.py not brain.py)

# Current monitoring — INA260 x3 (§5.2). Monitor/log only (FR-1100 diagnostics) — no numeric
# overcurrent trip thresholds exist anywhere in the documentation to hardcode a cutoff against.
INA260_SERVO_ADDR=0x40; INA260_PI_ADDR=0x44; INA260_MOTOR_ADDR=0x45

# Witty Pi 5 HAT+ (UUGear) — RTC and power management. Uses only SDA/SCL (per its own user
# manual), no other GPIO — confirmed no conflict with anything else on this bus. Physically
# installed, `wp5`/`wp5d` software installed and configured 2026-08-21: power source priority
# V-USB first (matches wiring), "default state when powered" set to ON with a 2s delay (so Willy
# boots when power is connected rather than needing the HAT's physical button pressed), hardware
# watchdog enabled at 200 missed heartbeats (~10-20s at brain.py's tick's ~50-100ms heartbeat
# cadence — tolerant of ordinary hiccups, still catches a genuinely wedged kernel; see CLAUDE.md).
# ENABLE_WITTY_PI now True — 0x51 is included in brain.py's _EXPECTED_I2C self-test set.
# Wired via VUSB (USB-C, off the existing 5V/INA260_PI_ADDR-monitored rail), not VIN — the
# manual documents its configurable low-voltage-threshold registers (#22/#23) as monitoring VIN
# specifically; whether an equivalent threshold usefully applies to a dropping VUSB is NOT
# confirmed and needs live testing, not an assumed number. The existing software battery-tier
# system (config.BAT_SHUTDOWN_V et al., via the real battery-voltage ADC) remains the primary
# safety mechanism regardless of how that resolves.
ENABLE_WITTY_PI=True
WITTY_PI_ADDR=0x51

ADS_ADDR=0x48; ADS_CH_BATTERY=0  # AIN0 only; charge-sense divider not yet wired
# Re-trimmed 2026-08-16: AIN0 read 2.9112V while a multimeter on the pack
# terminals read 12.2V (2.9112/12.2). Previous value (0.2865, set 2026-08-02)
# had drifted — direction of drift didn't fit simple aging (raw reading fell
# while actual pack voltage rose), so if this disagrees with a meter again,
# check the physical divider connection before just recalibrating again.
BATTERY_DIVIDER_SCALE=0.2386

# Battery threshold ladder (§13.2) — one-way toward safer states until voltage recovers above
# the next threshold up + hysteresis. Supersedes the old flat BAT_LOW/BAT_CRITICAL pair.
#
# BAT_FULL_V is a *display-only* 100% anchor for the battery_pct linear map (sensors.py
# ADC.battery_pct) — not a true full-charge voltage. A fully charged 3S LiPo open-circuit/rested
# reads ~12.6V; 11.39V is what this pack read *under load* while driving at calibration time
# (§13.2). battery_pct is cosmetic (HUD/voice announcements only) — every real safety decision
# in brain.py compares raw measured voltage against BAT_WARN/RTH/SAFE/SHUTDOWN_V directly, never
# battery_pct. Don't treat voltage-under-load as equivalent to open-circuit/rested voltage if
# these thresholds are ever recalibrated from a bench (unloaded) reading.
BAT_FULL_V=11.58      # display-only 100% anchor for battery_pct (post-fuse voltage)
BAT_WARN_V=11.4       # -> warn
BAT_RTH_V=10.8        # -> return-to-home / DOCK
BAT_SAFE_V=10.5        # -> SAFE_MODE (motion stop, arm holds)
BAT_SHUTDOWN_V=10.2   # -> controlled shutdown; also the 0% anchor for battery_pct
BAT_HYSTERESIS_V=0.2

# Diagnostics/logging (FR-1100) — rotating file log alongside the existing journal output;
# the journal is ephemeral (rotates per systemd-journald policy), this file persists independently.
# §13: the directory itself is now WILLY_LOG_ROOT above (was a bare 'logs' joined against the
# script's own directory here — that join now happens once, in storage.resolve_root()).
LOG_FILE='willy.log'
LOG_MAX_BYTES=2_000_000; LOG_BACKUP_COUNT=5

# World model (§9/§10, WildWilly_Claude_Fix_Implementation_Plan.md) — spatial/semantic memory,
# a separate SQLite file from memory.db per the master doc's §13.4 storage design ("SQLite on
# the SSD = spatial/semantic memory... live source of truth").
WORLD_MODEL_DB_PATH='world_model.db'
OBSTACLE_MAX_AGE_S=30.0      # Layer-1 local obstacle points older than this are dropped, never persisted
ROOM_MATCH_RADIUS_M=1.5      # default Room radius when add_room() isn't given one
OBJECT_DEDUPE_RADIUS_M=0.5   # repeated detections of the same class within this radius merge into one Object
# Sonar mounting bearing relative to chassis forward (0deg, matches odometry.py's heading
# convention) — UNCONFIRMED placeholder, no bench measurement exists in any doc for how the side
# sonars are actually angled. Used to project a sonar hit into a world (x,y) point via the
# current pose (mapping.py). Re-measure off the chassis before trusting mapped obstacle positions.
SONAR_BEARING_DEG={'front':0.0,'left':-90.0,'right':90.0}

# Navigation (§11, WildWilly_Claude_Fix_Implementation_Plan.md) -- local planner tunables for
# navigation.py's Navigator. No bench-measurement basis for these two (same "UNCONFIRMED
# placeholder" caveat as WHEEL_DIAMETER_M/TRACK_WIDTH_M above) -- reasonable starting guesses.
NAV_ARRIVAL_RADIUS_M=0.3       # how close counts as "reached" a waypoint
NAV_HEADING_DEADBAND_DEG=15.0  # within this heading error, drive forward instead of turning first
NAV_TURN_STEP_S=0.2            # duration of each incremental heading-correction turn while seeking

CLAUDE_MODEL='claude-sonnet-5'
CLAUDE_MAX_TOKENS=300; CLAUDE_ESCALATE_AFTER=5
AI_NEARBY_RADIUS_M=3.0  # §14: how far counts as "nearby" when ai_provider.py's build_world_state()
                        # filters world_model.py objects/obstacles into the AI's world-state payload

# safety.py SafetyController (§3/§4 of docs/WildWilly_Claude_Fix_Implementation_Plan.md) — the
# single authoritative gate all motor commands pass through, reactive-FSM and Claude-proposed
# alike.
MAX_COMMAND_DURATION_S=3.0  # hard cap on any single timed move regardless of what was requested
SENSOR_FAULT_GRACE_S=1.0    # how long imu/encoders/current may report unhealthy before _tick()
                            # forces a safe stopped state (SENSOR_FAULT) instead of just logging
STALL_GRACE_S=1.0           # FR-500-003 (Directive 5): how long a commanded wheel may show near-zero
                            # counts_per_sec before brain.py treats it as a real stall rather than
                            # still ramping up. Must clear both SPEED_RAMP_PER_S's worst-case ramp
                            # time (0.5s, full range) and Encoders' own 0.2s rate-sampling window —
                            # 1.0s matches SENSOR_FAULT_GRACE_S's precedent with comfortable margin
                            # over both. Unconfirmed against real hardware (no live drive test yet).

# ============================================================================
# v2.2 subsystems (docs/archive/WildWilly_Functional_Requirements_Document_v2.2.md,
# superseded by v3.0 but kept for the v2.2-era subsystem notes).
# Every flag below defaults OFF except the two with no external dependency
# (display expressions, local memory) — FR-000 Directive 6 requires all
# task-level behavior to stay inert unless explicitly enabled, and several of
# these need assets/credentials that are not provisioned on this unit yet
# (see docs/WildWilly_v2.2_Programming_Pass.md for the open list). Flip a
# flag only after its prerequisite is actually in place.
# ============================================================================

# --- FR-1300/2000: Willie's own Google account. This is NOT the owner's
# personal account (h.d.himmel@gmail.com). Create it, enable Gmail/Home Graph
# access on it, and populate the credential paths below before flipping
# ENABLE_SMART_HOME/ENABLE_EMAIL. Never put a live secret value directly in
# this file (FR-2000-005) — only env var names / paths under secrets/
# (gitignored).
WILLIE_GOOGLE_ACCOUNT='willie.pi5.droid@gmail.com'

ENABLE_SMART_HOME=False  # FR-1300
GOOGLE_HOME_CREDS_PATH='secrets/google_home_token.json'
SMART_HOME_DISCOVERY_TIMEOUT_S=5

# FR-1400 cloud AI fallback, never a primary dependency. The FRD assumed Gemini under
# WILLIE_GOOGLE_ACCOUNT above, but that account's Gemini API key hit a persistent zero free-tier
# quota even with billing linked (Google-side provisioning gap, parked 2026-08-06) — swapped to
# Anthropic's API instead, reusing ANTHROPIC_API_KEY (already configured for brain.py's STUCK-
# state decisions, see .env). See ai_provider.py::CloudAIProvider for the unified client (§14) —
# both this fallback and the STUCK-state decisions now share one Anthropic client instance.
ENABLE_CLOUD_AI=True
CLOUD_AI_TIMEOUT_S=8

ENABLE_EMAIL=True  # FR-2000 — Gmail app password verified working 2026-08-06 (IMAP+SMTP login OK)
GMAIL_IMAP_HOST='imap.gmail.com'; GMAIL_SMTP_HOST='smtp.gmail.com'; GMAIL_SMTP_PORT=465
GMAIL_APP_PASSWORD_ENV='WILLIE_GMAIL_APP_PASSWORD'
GMAIL_POLL_INTERVAL_S=120  # FR-2000-002
OWNER_EMAIL='h.d.himmel@gmail.com'
# FR-2000-009: single hard-coded outbound recipient, enforced in email_client.py itself, not
# just here — changing who Willie can email requires a code change, not a config edit.
EMAIL_OUTBOUND_ALLOWLIST=('h.d.himmel@gmail.com',)
# FR-2000-010/011: inbound sender allowlist is owner-managed at runtime (voice/display cannot
# touch it) so it lives in its own file, not a code constant like the outbound list above.
EMAIL_INBOUND_ALLOWLIST_PATH='secrets/email_sender_allowlist.json'

# --- FR-1500 voice pipeline. Hardware confirmed present 2026-08-06 (USB PnP Audio Device,
# mic+speaker, card 2). Enabled 2026-08-09 on owner's go-ahead. Audio I/O and the acoustic
# feedback loop (TTS leaking into the mic and self-triggering) were fixed 2026-08-15 (b5ae067) —
# see voice.py's own comments for both. Not yet live-verified end-to-end with real voice input.
ENABLE_VOICE=True
# Custom-trained "Hey Willie" model (models/hey_willie.onnx + .onnx.data, trained 2026-08-07,
# deployed 2026-08-15 — see wakeword_data/hey_willie_model/ for training artifacts) — replaced
# the earlier "Hey Jarvis" placeholder; this is the real trained wake phrase, not a stand-in.
WAKEWORD_MODEL_PATH='models/hey_willie.onnx'; WAKEWORD_THRESHOLD=0.65
# 2026-08-23: was 0.5. Live symptom traced to a dehumidifier's continuous background noise
# false-triggering the wake word, not echo (ruled that out first -- raising the post-speech
# decay window 0.6s->2.0s, see VOICE_ECHO_DECAY_S, didn't stop it; the trigger fired 8s after
# the reply ended, well outside any speech-adjacent window). 0.65 is a first, untested-live
# guess at cutting ambient-noise false positives without also missing real "Hey Willie" -- if
# it still false-triggers, go higher; if it stops responding to real wake attempts, go lower.
WHISPER_MODEL_SIZE='base.en'   # 2026-08-21: was 'small.en'. Benchmarked on this rover against a
                               # real 1.21s "what time is it" clip, service stopped: small.en
                               # 5.71s vs base.en 1.88s -- 3x faster for an identical, correct
                               # transcription. Pre-downloaded into ~/.cache/huggingface/hub
                               # before flipping (see the local_files_only note below).
                               # faster-whisper model name. NOTE voice.py loads this with
                               # local_files_only=True, so changing it to a size that is not
                               # already in ~/.cache/huggingface/hub RAISES, gets caught by
                               # _load_models()'s except, and silently disables voice entirely.
                               # Pre-download on the rover first, then change this.
WHISPER_CPU_THREADS=3          # 2026-08-21: was unset, so faster-whisper took all 4 cores. That
                               # all-core burst is the largest current spike this rover makes and
                               # it was browning the 5V rail out mid-utterance (EXT5V dipping past
                               # the Witty Pi cutoff -> hard power-off, reproducible by asking him
                               # the time). Leaving a core free trades a little STT latency for a
                               # smaller peak draw. Raise back to 4 once the rail is fixed.
# --- Hailo NPU STT, 2026-08-23. Scaffolding only -- see docs/superpowers/plans/2026-08-23-
# hailo-voice-offload-design.md Task 5. Blocked on compiling a Whisper HEF via Hailo's Dataflow
# Compiler on a separate x86 Ubuntu machine -- ARM (this rover) cannot run the compiler, and no
# such machine is available yet. Do not enable until HAILO_STT_MODEL_PATH points at a real HEF.
ENABLE_HAILO_STT=False
HAILO_STT_MODEL_PATH='models/hailo_whisper.hef'  # does not exist yet
PIPER_VOICE_PATH='models/piper/en_US-amy-medium.onnx'
LOCAL_LLM_MODEL_PATH='models/llama-3.2-3b-instruct-q4.gguf'  # llama.cpp gguf
LOCAL_LLM_CONFIDENCE_FLOOR=0.55  # FR-1400-001: below this, offer cloud AI fallback if enabled
# --- Hailo NPU intent-parsing LLM, 2026-08-23. See docs/superpowers/plans/2026-08-23-hailo-
# voice-offload-design.md Task 4 for the full investigation trail. Shares vision's Hailo device
# via picamera2.devices.Hailo.TARGET (confirmed live on the rover -- a separately-constructed
# VDevice collides with vision's, HAILO_OUT_OF_PHYSICAL_DEVICES(74); reusing the existing one
# does not). CPU LocalAIProvider baseline on voice.py's real prompt: 75% (24/32) on a 32-case
# intent-reliability batch (experiments/llm_reliability_batch.py) -- that is the number this
# backend's own pass rate needs to be judged against before treating it as safe to leave on,
# not an assumed-good ~100%.
ENABLE_HAILO_LLM=False  # default off -- flip only after experiments/llm_reliability_batch.py
                        # (run with `hailo` as the arg) shows an acceptable pass rate live
HAILO_LLM_MODEL_PATH='models/hailo_qwen2_1_5b.hef'  # qwen2:1.5b, the real Hailo GenAI Model
                                                     # Zoo model for this rover's delivery path
                                                     # (Phi-2 is not obtainable here -- see spec
                                                     # section 10.1). ~1.6GB, not tracked in git.
AUDIO_INPUT_DEVICE=None; AUDIO_OUTPUT_DEVICE=None  # None = system default
VOICE_TONE_DEFAULT='neutral'  # 'neutral'|'funny'|'silly'|'bashful' — FR-1500-008/009/010
# --- Voice latency, 2026-08-21. Measured live on this rover, "What time is it?":
# stt=12.1s intent=0.0s tts=4.6s total=16.7s. ~4.0s of that stt bucket was the old fixed capture
# window sitting in silence long after the speaker had stopped -- a 1.3s command paid the same
# 4s as a 4s one. Endpointing ends capture on trailing silence instead. NOTE the CPU was at a
# full un-throttled 2.4GHz for that measurement, so the remaining cost is real compute, not the
# power/throttling artifact the NPU spec (SS1) guessed at.
VOICE_CAPTURE_MAX_S=4.0       # hard cap -- unchanged from the old fixed window, so a noisy room
                              # that never endpoints behaves exactly as before, never worse
VOICE_CAPTURE_MIN_S=1.2       # never endpoint before this. Was 0.8, which live turned out to be
                              # short enough that a premature endpoint cut mid-command and Whisper
                              # returned nothing. Real commands ("what time is it") run ~1.2s of
                              # speech, so this is a floor under the whole utterance, not padding.
VOICE_ENDPOINT_SILENCE_S=0.6  # trailing silence that ends capture, once speech has been heard.
                              # Set >= VOICE_CAPTURE_MAX_S to disable endpointing entirely.
VOICE_VAD_NOISE_MULT=2.5      # speech threshold = measured ambient floor x this
VOICE_VAD_FLOOR=0.004         # absolute minimum threshold (RMS, 0-1) so a silent room can't set
                              # a threshold low enough for its own noise to read as speech
VOICE_ECHO_DECAY_S=2.0        # 2026-08-23: was hardcoded 0.6s in voice.py::_speaker_loop. Live
                              # symptom: after a real reply, 2-3 more wake-word triggers fired in
                              # a row, each with an empty transcript ("How can I help?" spoken
                              # each time) -- classic self-triggering-on-own-echo loop (see the
                              # no-echo-cancellation note above _SAFETY_PATTERN), just not fully
                              # closed by the existing 0.6s gap in this room's actual acoustics.
                              # Raised as a first, testable mitigation -- not confirmed sufficient
                              # yet, re-tune from a live retest.
# Perceived latency: a short chirp the instant the wake word fires, so the interaction *starts*
# immediately even though STT/TTS still take seconds behind it. This is the "Gotcha" idea the
# Hailo NPU spec (SS6) deferred rather than rejected. Deliberately a tone and NOT speech: this
# mic+speaker puck has no echo cancellation (see voice.py), so a spoken ack would be recorded
# and transcribed as part of the command.
VOICE_ACK_ENABLED=True
VOICE_ACK_PATH='models/ack.wav'  # generated on first use, not provisioned -- models/ is gitignored
# 2026-08-23: owner-requested -- a second, audibly distinct chirp signalling Willy has finished
# speaking and is listening again. Two 660Hz pulses (vs. the single 880Hz wake chirp) so the two
# are never confused by ear. Plays while still muted (_speaking held) so its own sound can't
# self-trigger the wake word, same defensive shape as the wake chirp's deaf_frames handling.
VOICE_DONE_CHIRP_ENABLED=True
VOICE_DONE_PATH='models/done.wav'  # generated on first use, not provisioned

# --- FR-1600 display expressions. Pure software, layered on the existing WillyFace state
# machine (display.py) — no new hardware/model dependency, safe to default on.
ENABLE_DISPLAY_EXPRESSIONS=True
IDLE_PERSONALITY_CYCLE_S=90  # FR-1600-007: how often the idle 'silly' animation may recur

# --- FR-1700 object detection/retrieval. Arducam OV9281 (USB) confirmed present 2026-08-06.
# CAMERA_DEVICE corrected 2026-08-16: /dev/video0 is actually the imx708 CSI camera
# (rp1-cfe driver), not the Arducam — /dev/video8 is the Arducam's real capture node
# (/dev/video9 on the same bus is metadata-only, no Video Capture capability). Device-node
# assignment isn't stable across reboots/kernel changes; re-check with
# `v4l2-ctl --list-devices` / `v4l2-ctl -d /dev/videoN --info` before trusting this again.
# An AI HAT+2 (Hailo-10H) was installed and PCIe-bonded 2026-08-16 (see CLAUDE.md) and vision.py
# IS now wired to use it — see ENABLE_HAILO_VISION below (2026-08-21). The flags in this block
# describe only the older CPU/Arducam fallback path, which that swap left untouched.
ENABLE_OBJECT_RETRIEVAL=False  # 2026-08-20: briefly flipped True and live-verified the capture/
                               # inference pipeline works end-to-end (model, cv2 5.0.0,
                               # ultralytics 8.4.115, Arducam all confirmed present + a real
                               # frame captured). Reverted immediately: owner confirmed the
                               # Arducam (config.CAMERA_DEVICE, /dev/video8) is mounted REAR-
                               # facing, not front — vision.py::_CAMERA_ID='front' and
                               # retrieval_task.py's detect()-then-forward() logic both assume
                               # forward-facing. Do not re-enable until CAMERA_DEVICE points at
                               # the actual front camera (CSI imx708, /dev/video0) and that
                               # capture path is verified working — untested as of this note.
CAMERA_DEVICE='/dev/video8'
YOLO_MODEL_PATH='models/yolov8n.pt'
YOLO_CONF_THRESHOLD=0.5
# --- Hailo-10H vision backend, 2026-08-21. Pre-installed HEF confirmed present on this exact
# rover (/usr/share/hailo-models/yolov8m_h10.hef, compiled for HAILO10H specifically -- verify
# with `python3 -c "from picamera2.devices import hailo_architecture; print(hailo_architecture())"`
# before trusting this path again if the OS image ever changes). Does NOT replace
# ENABLE_OBJECT_RETRIEVAL/CAMERA_DEVICE above -- those stay as the (currently-wrong-facing,
# disabled) CPU/Arducam fallback path. This is a separate backend selector: when True, detect()
# uses the CSI front camera (imx708) + Hailo NPU instead of the Arducam + CPU.
# NOT ONLY a backend selector in effect, though: vision.py's _enabled is (this OR
# ENABLE_OBJECT_RETRIEVAL), so turning this on also makes detector.available True for the first
# time -- which arms the vision-gated behaviours that were dead while both flags were False:
# voice come_here/follow (PursuitTask) and retrieve (RetrievalTask, not gated on available at
# all) will now actually drive the rover, steering on vision.py::localize()'s uncalibrated
# distance/bearing estimates. See CLAUDE.md's CSI/Hailo note before trusting a range.
ENABLE_HAILO_VISION=True  # 2026-08-23: re-enabled after resolving the real power/I2C faults
                          # found this session (DROK 9V VIN feed to Witty Pi, loose 3.3V wire to
                          # the I2C peripherals reseated). Startup under the live service not yet
                          # independently re-verified post-fix -- check self-test/logs after deploy.
HAILO_YOLO_MODEL_PATH='/usr/share/hailo-models/yolov8m_h10.hef'
HAILO_COCO_LABELS_PATH='models/coco.txt'
RETRIEVAL_APPROACH_STOP_CM=25   # distance from target to halt before attempting grasp
RETRIEVAL_GRASP_RETRIES=2       # FR-1700-005
RETRIEVAL_PERSON_MAX_RANGE_CM=150  # FR-1700-008: hand-off proximity gate
PURSUIT_STANDOFF_CM=60          # FR-1000 come_here/follow: how close is "arrived" -- stop short of a person, not into them
PURSUIT_RESUME_HYSTERESIS_CM=20 # FR-1000 follow: how far past standoff before FOLLOWING resumes closing the gap

# --- FR-1800 privacy / retention. Presence of the flag file (not its content) disables mic+
# camera, independent of and in addition to E-stop — deleting the file re-enables them.
MIC_CAMERA_DISABLE_FLAG_PATH='secrets/privacy_disable.flag'
DATA_RETENTION_DAYS=30          # FR-1800-004
RAW_AUDIO_CAMERA_PERSIST=False  # FR-1800-002

# --- FR-1900 local memory store. SQLite, no external dependency — safe to default on.
ENABLE_LEARNING=True
MEMORY_DB_PATH='memory.db'
MEMORY_REPLAY_SIMILARITY_FLOOR=0.6  # FR-1900-003: below this, report mismatch rather than replay
STUCK_TIMEOUT=3.0; BACK_UP_TIME=0.8; TURN_TIME_90=1.2; IDLE_TIMEOUT=30.0

# Owner decision 2026-08-20: autonomous ROAM relies on sonar alone for obstacle avoidance and was
# wandering into things it couldn't sense, tripping repeated STALL_FAULTs. Gate _idle()'s
# auto-ROAM behind this flag — default off. Manual/voice-commanded driving is unaffected, this
# only blocks the unprompted idle-timeout wander.
# NOTE 2026-08-21: the original note said "until vision is live-verified; flip to True then".
# Vision now IS live-verified (ENABLE_HAILO_VISION above) — but that does NOT satisfy this gate
# and this stays False. Vision feeds world_model.py for planning/classification only; it is
# deliberately kept out of the reflex/obstacle path (see CLAUDE.md's "keep the NPU out of the
# safety path"), so ROAM is still sonar-only for avoidance and the original reason is unchanged.
ENABLE_AUTONOMOUS_ROAM=False

def validate():
    """Configuration self-test (2026-08-08 external code audit's P2 item): config.py has grown
    into the central hardware/software contract, large enough that a copy-paste or typo drift
    (a duplicate address, a threshold quietly out of order) is a real risk and easy to miss by
    reading the file top to bottom. Pure function, no hardware access -- returns a list of
    problem strings (empty if clean). Deliberately NOT wired into brain.py::_self_test()'s
    motion-blocking gate: unlike a missing sensor, a config problem found here doesn't mean the
    robot can't safely hold still, and unilaterally turning validation on for a live safety gate
    is an owner decision, not something to flip silently. Wired into diagnostics.py (read-only,
    FR-1100-004) instead -- run `python3 diagnostics.py` to see current results."""
    problems=[]

    i2c_addrs={'ENCODER_ADDR':ENCODER_ADDR,'INA260_SERVO_ADDR':INA260_SERVO_ADDR,
               'STEER_PCA_ADDR':STEER_PCA_ADDR,'ARM_PCA_ADDR':ARM_PCA_ADDR,
               'INA260_PI_ADDR':INA260_PI_ADDR,'INA260_MOTOR_ADDR':INA260_MOTOR_ADDR,
               'ADS_ADDR':ADS_ADDR,'IMU_ADDR':IMU_ADDR,
               'MOTORKIT_LEFT_ADDR':MOTORKIT_LEFT_ADDR,'MOTORKIT_RIGHT_ADDR':MOTORKIT_RIGHT_ADDR}
    seen={}
    for name,addr in i2c_addrs.items():
        if addr in seen: problems.append(f'duplicate I2C address {addr:#x}: {seen[addr]} and {name}')
        else: seen[addr]=name

    gpio_pins={'SONAR_FRONT_TRIG':SONAR_FRONT_TRIG,'SONAR_FRONT_ECHO':SONAR_FRONT_ECHO,
               'SONAR_LEFT_TRIG':SONAR_LEFT_TRIG,'SONAR_LEFT_ECHO':SONAR_LEFT_ECHO,
               'SONAR_RIGHT_TRIG':SONAR_RIGHT_TRIG,'SONAR_RIGHT_ECHO':SONAR_RIGHT_ECHO,
               'ENCODER_INT_PIN':ENCODER_INT_PIN}
    seen={}
    for name,pin in gpio_pins.items():
        if pin in seen: problems.append(f'duplicate GPIO pin {pin}: {seen[pin]} and {name}')
        else: seen[pin]=name

    # MCP23017 (0x27) pin-index namespace is separate from raw Pi GPIO above -- 0-7=port A,
    # 8-15=port B (adafruit_mcp230xx's own get_pin() numbering). Encoders use bank-A entirely
    # (2 bits x 6 wheels doesn't fit in 8, so lr/rr spill onto B0-B3) plus IMU_RST_MCP_PIN=B4.
    mcp_pins={}
    for wheel,(bank,bitA,bitB) in ENCODER_PINS.items():
        base=0 if bank=='A' else 8
        for bit,role in ((bitA,'A'),(bitB,'B')):
            idx=base+bit
            key=f'ENCODER_PINS[{wheel!r}] ({role})'
            if idx in mcp_pins: problems.append(f'duplicate MCP23017 pin {idx}: {mcp_pins[idx]} and {key}')
            else: mcp_pins[idx]=key
    if IMU_RST_MCP_PIN in mcp_pins:
        problems.append(f'IMU_RST_MCP_PIN={IMU_RST_MCP_PIN} collides with {mcp_pins[IMU_RST_MCP_PIN]}')

    if not (BAT_SHUTDOWN_V<BAT_SAFE_V<BAT_RTH_V<BAT_WARN_V):
        problems.append(f'battery tier thresholds not strictly ordered: '
                         f'SHUTDOWN={BAT_SHUTDOWN_V} SAFE={BAT_SAFE_V} RTH={BAT_RTH_V} WARN={BAT_WARN_V}')
    if BAT_FULL_V<BAT_WARN_V:
        problems.append(f'BAT_FULL_V={BAT_FULL_V} is below BAT_WARN_V={BAT_WARN_V} -- battery_pct could '
                         f'report 100% while the safety tier ladder has already escalated to \'warn\'')
    if BAT_HYSTERESIS_V<=0:
        problems.append(f'BAT_HYSTERESIS_V={BAT_HYSTERESIS_V} must be positive')

    if IMU_TILT_WARN>=IMU_TILT_LIMIT:
        problems.append(f'IMU_TILT_WARN={IMU_TILT_WARN} must be below IMU_TILT_LIMIT={IMU_TILT_LIMIT} '
                         f'(warn should fire before the hard stop, not after)')

    for label,lo,center,hi in (('SERVO',SERVO_MIN_US,SERVO_CENTER_US,SERVO_MAX_US),
                                ('ARM_SERVO',ARM_SERVO_MIN_US,ARM_SERVO_CENTER_US,ARM_SERVO_MAX_US)):
        if not (lo<center<hi):
            problems.append(f'{label} pulse-width range not ordered MIN<CENTER<MAX: {lo}<{center}<{hi}')

    for name,speed in (('SPEED_ROAM',SPEED_ROAM),('SPEED_TURN',SPEED_TURN),('SPEED_SLOW',SPEED_SLOW)):
        if not (0<speed<=SPEED_MAX):
            problems.append(f'{name}={speed} must be in (0, SPEED_MAX={SPEED_MAX}]')
    if not (0<SPEED_MAX<=1.0):
        problems.append(f'SPEED_MAX={SPEED_MAX} must be in (0, 1.0]')

    if MAX_COMMAND_DURATION_S<=0:
        problems.append(f'MAX_COMMAND_DURATION_S={MAX_COMMAND_DURATION_S} must be positive')

    return problems
