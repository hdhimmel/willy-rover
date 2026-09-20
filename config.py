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
# ADDRESSES SWAPPED 2026-09-18 AFTER MEASURING THEM. These read 0x60=left, 0x61=right
# from the original build until M-1 was finally run: the left wheels are on 0x61.
MOTORKIT_LEFT_ADDR=0x61; MOTORKIT_RIGHT_ADDR=0x60
# BENCH-VERIFIED 2026-09-18 (M-1). Rover on boxes, wheels clear, service stopped,
# each port driven ALONE by raw address+port -- never by wheel name, since this dict
# was the thing under test -- with the owner naming the wheel that actually turned.
#
#   0x61 M1 -> LEFT REAR     0x60 M1 -> RIGHT REAR
#   0x61 M2 -> LEFT CENTER   0x60 M2 -> RIGHT CENTER
#   0x61 M3 -> LEFT FRONT    0x60 M3 -> RIGHT FRONT
#
# Two separate findings, and only one of them was the expected one:
#
# 1. PORT ORDER M1=REAR, M2=MIDDLE, M3=FRONT IS CORRECT. This was the ordering
#    commit 484fbdc asserted on 2026-09-04 for "physical layout symmetry" -- an
#    argument, not a measurement, and flagged here as untrustworthy ever since. The
#    argument happened to be right.
#
# 2. THE BOARD ADDRESSES WERE SWAPPED, AND THAT WAS NEVER SUSPECTED. Every revision
#    of this file had 0x60=left, 0x61=right. The left wheels are on 0x61. Note the
#    hardware was rebuilt after the 2026-08-24 test, so that result described
#    different wiring and could not have caught this.
#
# The 2026-08-24 result (M1=MIDDLE, M2=FRONT, M3=REAR) is now superseded and should
# not be restored -- it predates the rebuild.
#
# WHY THIS HID FOR SO LONG, and it is worth understanding before trusting any
# per-wheel claim in this repo: _set() commands all three wheels of a side to the
# same value, so forward, reverse and skid turns behave identically whether or not
# the sides are swapped. A left/right swap is invisible to every gross motion the
# rover makes. It only surfaces under per-wheel work -- odometry attribution,
# crab/differential steering, stall tracing -- where "lf stalled" names the wrong
# physical wheel, on the wrong side of the robot.
#
# The encoder A/B channel assignment in Master Hardware Design section 7.2 is
# unverified for the same reason and is NOT settled by settling this one. It has its
# own bench test (E-1) and its own swap risk.
MOTOR_PORT={'lf':(MOTORKIT_LEFT_ADDR,3),'lm':(MOTORKIT_LEFT_ADDR,2),'lr':(MOTORKIT_LEFT_ADDR,1),
            'rf':(MOTORKIT_RIGHT_ADDR,3),'rm':(MOTORKIT_RIGHT_ADDR,2),'rr':(MOTORKIT_RIGHT_ADDR,1)}
# Raised 2026-08-24. The previous set (ROAM .55 / TURN .50 / SLOW .35 / MAX .80)
# was below breakaway torque for this chassis: commanded motion produced an
# audible hum with no rotation. Measured per-wheel on the bench that day, a
# JGA25-370 on this base needs roughly 0.5+ duty to start turning at all, so
# SLOW=0.35 could never move him -- it only ever stalled the motors.
# WHY breakaway is that high, established 2026-08-25: these are 12V 620 RPM motors,
# a low-reduction speed-optimised gearbox, driving 101.6mm wheels. Torque scales
# with reduction and tractive force scales inversely with wheel radius, so both
# choices cut force at the ground. Raising these numbers spends headroom; it does
# not create torque, and full duty is already full duty. If more torque is needed
# it is a motor change -- see Master Hardware Design v2.0 section 7.1.
SPEED_ROAM=0.75; SPEED_TURN=0.70; SPEED_SLOW=0.55; SPEED_MAX=1.00
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

# --- FR-1000-002 / FR-1200-005 multi-zone ToF (DFRobot SEN0628, Master Hardware Design §6.5).
# Front obstacle sensing ALONGSIDE the sonar, never replacing it: the two fail in opposite
# directions. Sonar is blind to chair legs, soft furnishings and angled surfaces; ToF looks
# straight THROUGH glass, which sonar reflects off perfectly well.
ENABLE_TOF=False            # flip True once the sensor is wired and a floor profile is captured
TOF_PORT='/dev/ttyAMA3'     # UART, not I2C -- keeps it off a bus that took the whole rover down
                            # twice on 2026-09-07/08. CONFIRM the Pi 5 overlay->pin mapping first
                            # (§6.5): the Pi 4 mapping does not carry over to the RP1.
TOF_BAUD=115200             # fixed in the sensor's firmware, not configurable
TOF_ZONES=64                # 8x8. A frame of any other length is a desynchronised UART, not data
TOF_POLL_INTERVAL_S=0.2     # tof.FramePoller's cadence. The sensor answers a getAllData in ~0.13s
                            # (scripts/tof_probe.py, 200 frames, 2026-09-15), so 0.2s is roughly
                            # back-to-back without pinning the link. NOT the tick rate -- the tick
                            # reads a cached frame and never waits on this.
TOF_STALE_AFTER_S=1.0       # a cached frame older than this is reported as NO frame, so ToFSensor
                            # goes unavailable and distances() falls back to sonar alone. Matches
                            # SENSOR_FAULT_GRACE_S's precedent. This is the ToF's degradation rule
                            # and NOT the sonar's -- nothing sits under the sonar, so a stale sonar
                            # reading must stop the rover rather than be ignored.
# Floor-profile margin. A zone counts as an obstacle only when it returns this much SHORTER than
# its own stored floor distance, and as a drop when it returns this much LONGER (or nothing).
# Wide enough to absorb carpet pile, a rug edge and a few mm of ride height -- without a margin
# every surface change reads as an obstacle and he never moves.
TOF_FLOOR_MARGIN_MM=120.0
TOF_FLOOR_PROFILE_PATH='tof_floor_profile.json'
TOF_PROFILE_SAMPLES=10      # frames averaged when capturing; one frame carries per-zone noise
                            # straight into the baseline everything else is measured against

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

# Arm — PCA9685 @0x43. Wider nominal range than steering (manufacturer spec 500-2500us) though
# §11.5/§20.6 flag cheap-clone units may bind before the full sweep.
ARM_PCA_ADDR=0x43
#
# CHANNEL MAP CORRECTED 2026-09-17 AGAINST HARDWARE. Every assignment below was verified by
# driving one channel at a time with the owner watching which joint moved. The previous map came
# from a 2026-09-06 paper reassignment that was never tested, and CHANNELS 0-3 WERE EXACTLY
# REVERSED in it -- it read shoulderA/shoulderB/elbow/wristPitch where the hardware is
# wristPitch/elbow/shoulder/shoulder. 4, 5 and 6 were already right.
#
#   CH0 wrist pitch   CH1 elbow   CH2 shoulder   CH3 shoulder(second axis, function unidentified)
#   CH4 wrist rotate  CH5 gripper CH6 base       CH7 unused, nothing connected
#
# CH2 and CH3 are NOT a mirrored pair. The old "J1b = 2x1500 - J1a" relation is wrong: driving
# them mirrored vs. same-direction gave statistically identical current (0.197A vs 0.176A), and
# a shared axis driven the wrong way would fight hard. CH2 is the shoulder lift axis; what CH3
# does alone has not been established.
ARM_BASE=6; ARM_WRIST_PITCH=0; ARM_ELBOW=1; ARM_SHOULDER=2; ARM_SHOULDER_B=3
ARM_WRIST_ROT=4; ARM_GRIPPER=5
ARM_SERVO_MIN_US=500; ARM_SERVO_MAX_US=2500; ARM_SERVO_CENTER_US=1500
#
# DO NOT CENTRE CH1. ARM_SERVO_CENTER_US applied to the elbow drives it into the top of Willy:
# the servo fitted before 2026-09-17 held ~8A there indefinitely and was destroyed by it. Any
# homing or park routine that centres every joint will stall the elbow on each startup.
#
# DIRECTIONS, owner-confirmed on hardware 2026-09-17:
#   shoulder CH2 : DECREASING us raises, increasing lowers
#   gripper  CH5 : INCREASING us closes (jaw contact from ~1700us), decreasing opens
#
# GRIP FORCE IS SET BY CURRENT, NOT POSITION. Closing draws 0.075A at 1500us, 0.156A at 1650,
# 0.215A at 1700, 0.457A at 1750, 1.049A at 1780. Stop feeding past ~0.4-0.5A: it grips there,
# and beyond that it is stalling and heating. No position means "closed" -- the jaws close on
# whatever is held.
#
# MOVE, THEN KEEP HOLDING. Releasing a channel (off=0) makes the arm go limp and fold. Holding
# is nearly free -- the full waving pose below sits at ~0.33A -- while MOVING briefly costs amps.
# Release only when slack is actually wanted.
#
# ORDER MATTERS: open the elbow BEFORE moving the shoulder, or the arm strikes the top of Willy.
#
# Presets. WAVE_HELLO verified end to end on hardware 2026-09-17; the whole pose holds at ~0.33A
# on a 6.04V rail with every channel energised. Reach it in the order given, 50us steps on the
# shoulder -- not as a single jump, which would slam the joint.
ARM_POSE_WAVE_HELLO={'elbow':1000,'shoulder':750,'wrist_pitch':1500}
#
# REST pose, owner-designated 2026-09-17. TWO CAVEATS, both measured, neither yet resolved:
#
#  1. It does NOT hold for free. The wrist sits against its travel limit here and draws a
#     SUSTAINED 0.87A (~5.2W) for as long as the pose is held, with the 6V rail sagging to
#     6.017V. Every other pose today settled under 0.4A. A rest pose is held indefinitely by
#     definition, so this is the one place a standing load actually matters. Wrist at 2300us
#     holds the same shape for 0.23A and 2200us for 0.05A -- prefer one of those if the exact
#     wrist angle is not load-bearing.
#  2. The elbow value is OUT OF SPEC (manufacturer range is 500-2500us). Past about 2530us the
#     servo stopped responding -- peaks collapsed to ~0.1A -- so 2610 is very likely not a
#     position it actually reaches. Treat ~2530us as the real limit until re-measured.
ARM_POSE_REST={'elbow':2610,'shoulder':2010,'wrist_pitch':2450}
ARM_WAVE_WRIST_US=(1380,1620)   # oscillate the wrist between these, ~0.35s per leg, 4 cycles
ARM_WAVE_APPROACH_STEP_US=50    # shoulder step size travelling to the pose
#
# Any arm motion should watch INA260 ARM_6V current and release a channel that stays above this
# for this long. A threshold checked only AFTER a move completes is useless -- that is how the
# first elbow servo was destroyed. The check must run inside the movement loop.
ARM_CURRENT_LIMIT_A=2.5
ARM_CURRENT_LIMIT_S=0.4

# Wheel encoders — MCP23017 @0x27 (§9.1), quadrature A/B per wheel. counts/rev is a "starting
# value" from the motor listing, not bench-confirmed.
ENCODER_ADDR=0x27
# MEASURED 2026-09-18 (E-1) -- LEFT AND RIGHT WERE TRANSPOSED, the same swap found on the
# motor boards the same day (see MOTOR_PORT above). The encoders were landed at the same time
# as the motors, so the same left/right confusion propagated into both. Master Hardware Design
# 7.2 predicted exactly this: the encoder column "may follow the physical wheels, or the port
# permutation, or neither".
#
# Method: drive one wheel 1.0s, compare the MCP23017 resting state before and after, and count
# over six trials how often each pin changes. A pin on that wheel's encoder changes on most
# trials (the shaft stops wherever it stops); a pin picking up PWM crosstalk changes rarely and
# inconsistently. Confirmed on two independent runs.
#
# DO NOT sample these pins in a tight loop looking for edges. At 0.6 duty the edge rate is
# ~7.7kHz and I2C polling tops out near 1.2kHz, which aliases to a CONSTANT reading -- that is
# why every earlier attempt concluded "no encoder produces any output", which was wrong.
#
# WARNING, PHASE B IS NOT VERIFIED AND CURRENTLY READS DEAD. Only the even pin of each pair
# (Phase A, yellow) produces transitions; every odd pin (Phase B, green) is silent except a
# flicker on A7. Six wheels failing on exactly the odd pin is one wiring pattern, not six
# faults -- trace the green wires before trusting any direction-aware decode. Until then the
# quadrature decode in sensors.py can count distance but cannot resolve direction.
#
# The encoder supply was found REVERSED on 2026-09-18 and corrected; lf went from 2/6 to 6/6
# on its Phase A immediately afterwards. Phase B did not recover, so those output stages may
# have been damaged by the reverse polarity -- the same failure that destroyed two sonars the
# previous day, on connectors reassembled during the same rebuild.
ENCODER_PINS={'lf':('A',4,5),'lm':('A',6,7),'lr':('B',2,3),
              'rf':('A',0,1),'rm':('A',2,3),'rr':('B',0,1)}
ENCODER_COUNTS_PER_REV=752   # 11 PPR (motor shaft) x4 quadrature x 17.1:1 reduction.
                             # WAS 3292, derived as "823.1 PPR x4". 823.1/11 implies a 74.8:1
                             # gearbox -- the ratio matching the STALE "6V, 100-200 RPM" motor
                             # spec corrected 2026-08-25. Owner gave the real reduction as
                             # 17.1:1 (consistent with 620 RPM from a ~10.6k RPM bare motor),
                             # making the old value 4.375x too high.
                             # odometry.py divides by this, so distances were reported at ~23%
                             # of actual from the encoder side alone. Together with the wheel
                             # diameter error fixed the same day (0.065 vs 0.1016, 1.56x), dead
                             # reckoning under-reported by roughly 6.8x before 2026-08-25.
                             # STILL DERIVED, NOT MEASURED: the 11 PPR figure comes from the
                             # same doc section that had the motor spec wrong. Confirm with
                             # scripts/encoder_calibration.py before trusting odometry -- see
                             # G-2 (FRD v3.1). Interrupt-driven decode (2026-08-18) is retracted
                             # (2026-08-23): would break ISO1540 galvanic isolation and would not
                             # have reduced I2C transaction count anyway. Polling is the real
                             # mechanism -- see sensors.py::Encoders._loop().

# Odometry (§8, WildWilly_Claude_Fix_Implementation_Plan.md). This comment used to cite a
# "430x330x220mm chassis envelope (§2)" — that figure appears ONLY in
# docs/archive/WildWilly_Master_Engineering_Package_rev6.0.7.md, a superseded document the repo
# explicitly says not to cite as authoritative, and the current Master Hardware Design v2.0
# carries no chassis envelope at all. Owner measured the chassis at 400mm wide on 2026-08-25;
# the archived 430mm is stale. Neither figure is a track measurement anyway — no doc ever gave a
# wheel diameter or a track (L/R wheel-center spacing), so both constants below began as
# estimates derived from that retired envelope rather than from a caliper. odometry.py's pose output is dead-reckoning
# only (no slip correction, no fusion with the IMU heading) and will drift; re-measure these two
# values directly off the chassis before trusting distances/headings for anything beyond rough
# relative dead-reckoning.
WHEEL_DIAMETER_M=0.1016 # 4.00 in, owner-measured 2026-08-25. Was 0.065 (an UNCONFIRMED
                        # placeholder), so every distance odometry reported was 56% short of
                        # actual -- 0.204 m/rev assumed against 0.319 m/rev real. Anything
                        # derived from dead reckoning before this date is wrong by that
                        # factor, including stored world_model landmark positions.
                        # NOTE this is the nominal/unloaded diameter. The effective ROLLING
                        # diameter under the rover's weight is slightly smaller if the tyre
                        # compresses; a drive-a-measured-distance check is what settles that.
TRACK_WIDTH_M=0.310     # Owner-measured 2026-08-25. 400mm overall width ACROSS THE WHEELS minus
                        # one 90mm wheel width: outer edges at +/-200mm put the wheel centrelines
                        # at +/-155mm, so track = 310mm. Was 0.28, which over-reported rotation by
                        # ~11% (odometry.py:36 divides d_heading by this, so too small a value
                        # makes him believe he turned further than he did).
                        # Chassis envelope, same measurements: 430mm long x 400mm wide across the
                        # wheels, wheels 90mm wide. Note the archived rev6.0.7 figure of
                        # "430x330x220mm" had the LENGTH right and the width wrong -- a reminder
                        # that a superseded citation is not automatically wrong in every part.
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
#
# 2026-08-24: ADDRESSES CORRECTED AGAINST LIVE MEASUREMENT. All three read directly off the bus
# with base power on and the self-test passing:
#     0x40 ->  5.148 V @ 0.136 A     0x44 -> 11.373 V @ 0.112 A     0x45 ->  9.068 V @ 0.002 A
# 0x40 matched its documentation exactly. The other two did NOT: the docs put the Pi's monitor on
# 0x44 (as a 5.0-5.1V Pi-buck rail) and the motor/+12V bus on 0x45. Measurement shows the opposite
# -- 0x44 is the ~11.4V bus and 0x45 is the Pi's supply. The 2026-08-23 power rework swapped them:
# the Pi is no longer fed 5V from the Pi buck, it is fed 9V (DROK -> Witty Pi VIN -> Pi), which is
# why 0x45 reads 9V rather than the old 5V and why it reads ~0A while the Pi runs on AC.
# So the original NAMES were right and only the ADDRESSES were transposed -- fixed by swapping the
# two address values below rather than renaming anything, which keeps every existing caller valid.
# Owner-confirmed. Master Hardware Design v2.0 §2.2/§16.4 updated to match.
#
# ⚠ SUPERSEDED 2026-09-15 -- AND NOTE WHY, because it is not "the docs were wrong".
# The 2026-08-24 readings above were CORRECT FOR THE WIRING OF THAT DATE. Re-measured 2026-09-15:
#     0x40 -> 4.986 V @ 0.526 A     0x44 -> 6.043 V @ 0.037 A     0x45 -> 11.174 V @ 0.019 A
# 0x44 moved from the +12V bus (11.373V) to the 6V arm rail, and 0x45 moved from the 9V Pi feed
# (9.068V) to the +12V bus. The monitors were PHYSICALLY RELOCATED between those dates -- there is
# an unmerged branch named docs/eplzon-rev3.2-ina260-relocation -- and neither this file nor the
# design docs were updated to follow. R1's 9V now has no INA260 at all; the Witty Pi HAT monitors
# its own VIN (owner-stated 2026-09-15).
#
# LESSON, and it is the expensive kind: a constant whose NAME encodes a consumer ("motor", "pi")
# silently becomes a lie when the wire moves, and nothing fails loudly. brain.py went on reading
# the rail called 'motor' for three weeks while that monitor sat on the arm supply. The names
# below now encode VOLTAGE, which is a property of the rail rather than of our intent for it.
# When an INA260 is relocated again, re-measure all three and rename to match -- do not assume
# the old name still describes the new wire.
# ---------------------------------------------------------------------------------------------
# INA260 IDENTITIES — CORRECTED AND RENAMED 2026-09-15, owner-stated, measurements agree.
#
# The old names (INA260_SERVO_ADDR / INA260_MOTOR_ADDR / INA260_PI_ADDR) were wrong about which
# rail two of the three watched, and the wrongness was not cosmetic: brain.py's motor-power-cut
# detector read the rail named 'motor' and was therefore watching the ARM rail. See the note on
# INA260_ARM_6V_ADDR below. Three mutually inconsistent mappings existed simultaneously -- these
# constants, sensors.py's class comment, and sensors.py's own _RAILS dict -- which is precisely
# how the error survived two separate identification passes (2026-09-13 and 2026-09-14).
#
# Names are now RAIL-DESCRIPTIVE rather than consumer-descriptive. "Servo" was ambiguous the
# moment arm servos moved to their own 6V rail; "motor"/"pi" were simply incorrect. A name that
# states the voltage cannot drift away from the hardware the way a name stating a purpose can.
#
# Measured 2026-09-15 with the pack at 11.36V (owner meter):
#     0x40 -> 4.986V     0x44 -> 6.043V     0x45 -> 11.174V
INA260_5V_ADDR=0x40      # R2, 5V (DROK-5V, replaced FEICHAO UBEC 2026-08-28) -> steering servos
                         # + sonar VCC + Pi screen. VERIFIED 5.148V; read 4.986V on 2026-09-15.
                         # Wired inline, so the rail passes through it: this device can stop
                         # ACKing on I2C while still passing power perfectly (seen 2026-08-24 --
                         # dropped off the bus, came back after the wiring was physically handled,
                         # which points at a marginal logic-side connection, not a dead chip).
INA260_ARM_6V_ADDR=0x44  # R3, 6V (DROK-6V) -> arm servo distribution. Reads 6.043V, which matches
                         # the DROK-6V's 12V->6.0V spec and nothing else in the system.
                         # ⚠ THIS IS NOT THE MOTOR BUS. It was named INA260_MOTOR_ADDR until
                         # 2026-09-15 and brain.py::_motor_rail_status() read it believing it was
                         # the +12V motor bus. That broke in both directions: a real motor-power
                         # cut collapses the 12V bus and leaves this rail untouched, so the cut
                         # was UNDETECTABLE; and this rail idles at 6.043V against a 6.0V
                         # threshold, so 43mV of arm-servo droop raised a false "motor rail lost".
INA260_BUS_12V_ADDR=0x45 # +12V bus (battery via F1/KCD4/Q1) -> both FeatherWing VIN. Reads
                         # 11.174V against an owner-metered pack of 11.36V -- the ~0.19V delta is
                         # the fuse and switch drop. This is the rail brain.py watches for a
                         # motor-power cut.
                         # Was named INA260_PI_ADDR and documented as "DROK 9V -> Witty Pi VIN".
                         # It is NOT the 9V rail: R1's 9V is monitored by the Witty Pi HAT itself,
                         # not by any INA260 (owner-stated 2026-09-15). The old "reads ~0A when
                         # the Pi runs on AC" note explained the low current under the wrong
                         # premise; the real reason is that this bus only draws when motors do.

# Witty Pi 5 HAT+ (UUGear) — RTC and power management. Uses only SDA/SCL (per its own user
# manual), no other GPIO — confirmed no conflict with anything else on this bus. Physically
# installed, `wp5`/`wp5d` software installed and configured 2026-08-21: power source priority
# VUSB first (matches wiring — Pi powered via USB-C, then Witty Pi outputs that same 5V to the
# Pi via its own VUSB output). "Default state when powered" set to ON with a 2s delay (so Willie
# boots when power is connected), hardware watchdog enabled at 200 missed heartbeats (~10-20s).
# ENABLE_WITTY_PI now True — 0x51 is included in brain.py's _EXPECTED_I2C self-test set.
# Witty Pi's 9V input comes from DROK-Pi (9V adjustable buck, R1). The HAT monitors that VIN
# itself -- no INA260 sits on R1 (corrected 2026-09-15; this line previously credited
# INA260_PI_ADDR, which is now INA260_BUS_12V_ADDR and watches the +12V bus instead).
# The manual's low-voltage-threshold registers (#22/#23) monitor VIN; exact thresholds are not
# live-tested. The existing software battery-tier system (config.BAT_SHUTDOWN_V, battery-voltage
# ADC) remains the primary safety mechanism.
ENABLE_WITTY_PI=True
WITTY_PI_ADDR=0x51

ADS_ADDR=0x48; ADS_CH_BATTERY=0  # AIN0 only; charge-sense divider not yet wired
# Re-trimmed 2026-09-17: AIN0 read 3.7229V (raw 29783) against a bench supply set and
# metered at 11.5V. New scale = 3.7229/11.5 = 0.3237.
#
# This is the re-trim the divider fitted 2026-09-02 had been waiting for. The previous
# 0.2386 (2026-08-16) belonged to the OLD divider and was producing 15.60V from an 11.5V
# input -- impossible for a 3S pack, and it passed every plausibility guard because the
# guards only catch readings that are too LOW.
#
# NOTE the implied divider is not the one the docs describe. Master Hardware Design v2.0
# §16 calls it 10k/3.197k = 0.2423; the measured 0.3237 is ~10k/4.7k (0.3197 nominal,
# within resistor tolerance). Meter the fitted parts before trusting either figure.
#
# HEADROOM WARNING: at PGA ±4.096V the ADC saturates at 4.096V, so this scale can only
# represent a pack up to 4.096/0.3237 = 12.65V. A fully charged 3S LiPo rests at 12.6V --
# about 50mV of margin. Above that the reading clips and UNDER-reports. Every threshold in
# the ladder below sits under 11.6V so the safety path is unaffected, but a full-charge or
# on-charger reading cannot be trusted. Drop to PGA ±6.144V if the top of the range ever
# needs to be real.
#
# Previous values: 0.2481 (MCP3008-era), 0.2865 (2026-08-02), 0.2386 (2026-08-16).
# If this ever disagrees with a meter again, check the physical divider connection before
# recalibrating -- that is what the 2026-08-16 trim did, and it was trimming around a
# hardware change nobody had recorded.
BATTERY_DIVIDER_SCALE=0.3237

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
# PLAUSIBILITY FLOOR. Below this, the reading is not a flat pack -- it is a broken sensor, and
# sensors.py refuses it instead of letting it drive the shutdown ladder.
#
# Why this exists: the 2026-08-24 change stopped a FAILED read from zeroing the value, because a
# loose I2C wire had made "the bus hiccupped" indistinguishable from "the pack is flat" and
# Willie powered himself off. It did not cover a SUCCESSFUL read of an impossible value, and
# that happened for real -- an unfed battery divider read A0 at 0.0146V, which scales to a pack
# voltage near 0.06V, passes every guard, and walks the ladder straight to shutdown.
#
# 5.0V is chosen to be unarguable rather than tight. The Pi runs from this same pack through
# DROK-Pi; at 5V a 3S pack is destroyed and nothing would be executing this code. It sits well
# BELOW BAT_SHUTDOWN_V on purpose -- a genuinely flat pack must still shut the rover down, so
# raising this above the shutdown threshold would disable the protection the ladder exists for.
BAT_IMPLAUSIBLE_V=5.0
BAT_WARN_V=11.4       # -> warn
BAT_RTH_V=10.8        # -> return-to-home / DOCK
BAT_SAFE_V=10.5        # -> SAFE_MODE (motion stop, arm holds)
BAT_SHUTDOWN_V=10.2   # -> controlled shutdown; also the 0% anchor for battery_pct
BAT_HYSTERESIS_V=0.2

# --- Battery cross-check (added 2026-09-15) -------------------------------------------------
# Two independent sources exist for pack voltage and until now nothing compared them:
#   * the ADS1115 divider on A0 -- the authority, because it taps V21 on the PACK side and keeps
#     reading no matter what is switched off downstream;
#   * INA260 INA260_BUS_12V_ADDR -- factory-calibrated, no divider, no scale constant.
# On 2026-09-15 they read 0.09V and 10.97V simultaneously for hours and nobody noticed until a
# diagnostics run happened to be read by eye.
#
# WHAT THIS ACTUALLY BUYS, and it is not the case you would first think of. A grossly wrong ADC
# reading is ALREADY caught: accept_battery_raw() rejects anything below BAT_IMPLAUSIBLE_V=5.0V
# and brain.py escalates the staleness through SENSOR_FAULT. The dangerous case is the one that
# passes that floor -- a divider drifting or partially failing so it reports, say, 7.5V from an
# 11.2V pack. That is plausible, so it is adopted, and it walks the tier ladder to rth/safe and
# eventually shutdown. Willie returns home or powers off for no reason, and the log says low
# battery. THAT is what a second opinion catches.
#
# DETECTION ONLY, exactly like _check_motor_rail(): it logs and shows on the face, it never
# stops, faults, or touches the tier. The whole point is not to add a new automatic halt path to
# a rover whose battery sensing is the thing under suspicion.
BAT_CROSSCHECK_MAX_DIFF_V=1.5
# Must clear the LEGITIMATE difference between the two taps, not just sensor noise. The bus sits
# downstream of F1/KCD4/Q1 (and, per §2.1's P3 row, SW-M), so it reads lower than the pack by the
# drop across them: measured 0.19V at 16mA idle on 2026-09-15. Under motor load that drop grows,
# and nobody has measured how much yet -- M-1/E-1 will produce that number, and this value should
# be TIGHTENED once they have. 1.5V is deliberately loose to start: a false "your battery sensor
# is lying" during first driving would be worse than a slightly late catch.
BAT_CROSSCHECK_GRACE_S=5.0   # sustained disagreement before reporting -- rides out motor inrush

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
BAT_ADC_STALE_S=5.0         # 2026-08-24: how long ADC.battery_volts may go without a successful
                            # read before is_healthy reports the value as stale. The ADC polls at
                            # 1.0s, so this tolerates ~4 consecutive misses -- long enough to ride
                            # out a transient I2C glitch, short enough that a genuinely dead bus is
                            # caught within a few seconds. Before this existed, a failed read was
                            # forced to 0.00V and read as a flat pack, silently powering the rover
                            # off (happened for real: a loose I2C wire self-terminated Willie with
                            # no warning). Staleness now escalates via SENSOR_FAULT instead.
# Self-test override (owner request 2026-08-24). While motion is gated off by a failed startup
# self-test, brain.py re-runs the test every SELFTEST_RETRY_S; after SELFTEST_OVERRIDE_AFTER
# consecutive failures for the SAME reason it offers an on-screen button to enable motion anyway.
# In-memory only -- a service restart clears it, so an override never outlives its session.
# Deliberately scoped to the startup self-test: TILT/STALL/SENSOR faults are NOT overridable.
SELFTEST_RETRY_S=30.0
SELFTEST_OVERRIDE_AFTER=3

# STUCK help-photo alert (owner request 2026-08-24). When Willie enters STUCK -- he has exhausted
# his own avoidance attempts and escalated -- he emails the owner a photo from the front camera
# plus pose/sonar/battery context, so the situation can be seen rather than guessed at.
# This is the ONLY path where Willie sends outbound mail without a human confirmation step (see
# email_client.py::send_alert for why that's a bounded exception to FR-2000-004). It can only
# ever send to EMAIL_OUTBOUND_ALLOWLIST[0], and it reports -- it never acts.
# Both limits below are load-bearing, not boilerplate: _go('STUCK') can recur, and this codebase
# has already been bitten once by an unthrottled per-tick action spinning at ~9Hz for an hour.
# Motor-power-loss detection (2026-08-24). G-1 (FRD v3.1) is that the E-stop is invisible to
# software -- it cuts motors and arm with no GPIO sense line, so the control loop keeps issuing
# drive commands into dead motor controllers with no idea anything happened. A sense wire is
# still the real fix, but an INA260 sits inline on the +12V motor bus, so a cut there
# IS observable today with no new hardware: bus voltage collapses toward zero.
# (That monitor is 0x45 / INA260_BUS_12V_ADDR as of 2026-09-15. This comment said 0x44, and
# brain.py duly read 0x44 -- which had been relocated to the 6V ARM rail, making the cut
# undetectable. Corrected; see the INA260 identity note above and tests/test_motor_rail_identity.py.)
# Deliberately DETECTION-ONLY for now -- it logs and shows on the face, it does NOT stop or
# fault. Adding a brand-new automatic halt path on the eve of first driving is how you get a
# rover that refuses to move for reasons nobody understands; prove the signal is clean first,
# then decide about escalation. Threshold is well below any real operating voltage (the bus
# measured 11.3-11.4V) but above the ~0V a genuine cut produces.
MOTOR_RAIL_MIN_V=6.0
MOTOR_RAIL_GRACE_S=1.0            # sustained below threshold before it's reported, not a blip
ENABLE_STUCK_ALERT_EMAIL=True
STUCK_ALERT_COOLDOWN_S=600.0      # min seconds between stuck alerts (10 min)
STUCK_ALERT_MAX_PER_SESSION=5     # hard cap per service run, regardless of cooldown
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
WAKEWORD_MODEL_PATH='models/hey_willie.onnx'; WAKEWORD_THRESHOLD=0.5
# 2026-08-24: back to 0.5. It was briefly raised to 0.65 on a theory that was then RULED OUT --
# Corrected note: raising this did NOT stop the false wakes. Neither did raising
# VOICE_ECHO_DECAY_S 0.6->2.0. The actual root cause was stale openwakeword smoothing state
# surviving the muted window -- fixed by calling Model.reset() in voice.py::_speaker_loop().
# See that function's comment for the real story; an earlier version of this comment asserted
# the dehumidifier-noise theory as established fact, which contradicted voice.py and would
# mislead whoever tunes this next.
# A dehumidifier IS genuinely running in the room, so some elevated threshold may still be
# worth keeping on its own merits -- but 0.65 is an untested-live guess that was never
# validated as necessary, and a higher threshold risks missing a real "Hey Willie", including
# the one preceding a spoken "stop". Revisit against 0.5 now that reset() is in place.
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
ENABLE_HAILO_LLM=True   # PRIMARY on-device reasoning (Hailo-10H NPU). 2026-09-01: enabled for autonomous thinking.
                        # STUCK state tries this first; falls back to Claude only if confidence < HAILO_LLM_CONFIDENCE_FLOOR.
HAILO_LLM_MODEL_PATH='models/hailo_qwen2_1_5b.hef'  # qwen2:1.5b, Hailo GenAI Model Zoo. ~1.6GB, not tracked in git.
HAILO_LLM_CONFIDENCE_FLOOR=0.7  # NOT a confidence threshold, despite the name. brain.py:1007
                        # compares this against AIResult.action_confidence, and
                        # ai_provider.py::_action_confidence() returns ONLY 1.0 (the action name is
                        # recognised and duration/speed are in range) or 0.0. So this is a boolean
                        # gate: every value in (0.0, 1.0] behaves identically. Tuning it does
                        # nothing. 0.0 would admit structurally invalid actions and >1.0 would
                        # reject every on-device decision, which are the only two changes that
                        # would have any effect at all.
                        # The model's OWN self-reported confidence is used elsewhere --
                        # voice.py:467 against LOCAL_LLM_CONFIDENCE_FLOOR -- not here.
                        # Pinned by tests/test_confidence_gate_semantics.py.

# Generation parameters for the on-device LLM. Until 2026-09-14 hailo_llm.py called
# generate_all(prompt) with NONE of these set, leaving temperature/top_p/top_k/max_generated_tokens
# at whatever the runtime defaults to -- i.e. sampling tuned for varied prose, on a model whose
# only job is emitting one small JSON object for a strict parser. Observed live, same prompt back
# to back: defaults produced valid JSON with the WRONG intent ("status" for a battery question),
# temperature=0.1/top_p=0.9 produced valid JSON with the correct one.
#
# These are tuned against experiments/llm_reliability_batch.py. If you change one, RE-RUN THAT
# BATCH -- the 32-case score in FRD G-6 is only meaningful for the values it was measured at, and
# HAILO_LLM_CONFIDENCE_FLOOR above is calibrated against the same run.
HAILO_LLM_TEMPERATURE=0.1   # Near-greedy. JSON-only output wants determinism, not creativity.
HAILO_LLM_TOP_P=0.9
HAILO_LLM_MAX_TOKENS=256    # 20 of 32 failures on 2026-09-14 broke at exactly char 96 -- the
                            # signature of truncation. This budget is well clear of a complete object.
# --- Audio device selection. Mic swap 2026-09-09: capture moved OFF the Waveshare mic+speaker
# puck and onto a dedicated capture-only USB mic. The puck stays as the SPEAKER (owner decision
# 2026-09-09) -- it is the only non-HDMI playback device on the rover.
#
# Matched by NAME, not by card index. `arecord -l` order follows USB enumeration and can change
# across reboots, so a pinned `hw:3,0` would silently start listening to the wrong device. The two
# names differ by exactly one word, so read this carefully before editing:
#     'USB PnP Sound Device'  = the capture-only mic   (08bb:2902, card 3 as of 2026-09-09)  <- IN
#     'USB PnP Audio Device'  = the Waveshare puck     (0c76:1203, card 2 as of 2026-09-09)
AUDIO_INPUT_DEVICE='USB PnP Sound Device'
# The mic's hardware offers ONLY 48000 and 44100 (`cat /proc/asound/card3/stream0`) -- it cannot do
# the 16000 openwakeword requires, and PortAudio exposes the raw `hw:` devices only (no plug, no
# default, no PipeWire route), so ALSA will not convert for us. voice.py captures at this rate and
# decimates to 16k itself. 48000 is chosen over 44100 because it is an exact 3:1 integer ratio;
# 44100 would force fractional resampling on the wake-word hot path. Must be a whole multiple of
# 16000 -- validate() enforces it. A future 16kHz-native mic sets this to 16000 and the conversion
# becomes a passthrough.
AUDIO_INPUT_RATE=48000
# NOT USED. Kept only to document that it is inert: all three playback sites in voice.py call
# `pw-play`, which routes to PipeWire's default sink, and nothing anywhere reads this value.
# Setting it does nothing. To change the output device, change PipeWire's default sink.
AUDIO_OUTPUT_DEVICE=None
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
VOICE_ECHO_DECAY_S=0.6        # 2026-08-24: back at 0.6 (its original value). It was raised
                              # to 2.0 mid-investigation on a theory that was then RULED OUT --
                              # raising it did NOT stop the false wakes. The real fix was
                              # Model.reset() (see voice.py::_speaker_loop). Reverted because at
                              # 2.0 this was a ~2.4s window (decay + blocking done-chirp) where
                              # Willie could not hear "Hey Willie, stop" after every reply. That
                              # was tolerable while he could not move; with motion enabled and
                              # vision arming come_here/follow/retrieve, it is not.
# Perceived latency: a short chirp the instant the wake word fires, so the interaction *starts*
# immediately even though STT/TTS still take seconds behind it. This is the "Gotcha" idea the
# Hailo NPU spec (SS6) deferred rather than rejected. Deliberately a tone and NOT speech: this
# mic+speaker puck has no echo cancellation (see voice.py), so a spoken ack would be recorded
# and transcribed as part of the command.
# How long a queued voice command stays valid. voice.py stamps every queued command with 'ts'
# but nothing read it until 2026-08-25, so a command issued during a running task executed
# whenever that task happened to end -- "turn right" said during a 30s retrieval turned the
# rover half a minute later. Acting late on a motion command is worse than not acting: by then
# the person has stopped expecting it and is no longer watching for it. 10s is long enough to
# survive a slow STT+intent pass (measured worst case ~38.6s total is dominated by the LLM,
# which happens BEFORE queueing) and short enough that nothing executes out of context.
# confirm_receipt is exempt -- see brain.py's _NON_EXPIRING_INTENTS.
VOICE_COMMAND_MAX_AGE_S=10.0
VOICE_ACK_ENABLED=True
VOICE_ACK_PATH='models/ack.wav'  # generated on first use, not provisioned -- models/ is gitignored
# 2026-08-23: owner-requested -- a second, audibly distinct chirp signalling Willie has finished
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

# --- FR-2100 person recognition. NOT ENABLED: identity.py (the store/matcher) exists, but the
# embedding source (recognition.py) and its ArcFace/SCRFD models do not, so nothing can produce a
# vector yet. Flag stays False until that half lands, matching the convention used by
# ENABLE_HAILO_LLM and ENABLE_OBJECT_RETRIEVAL.
ENABLE_FACE_RECOGNITION=False
# Biometric data lives in its OWN file, deliberately not a table inside memory.db (design §4):
# a wipe is then a file delete rather than a careful DELETE, and the embeddings sit on a visibly
# separate boundary from ordinary learned facts. That separation is what makes FR-2100-005's
# privacy position defensible.
IDENTITY_DB_PATH='identities.db'
# Three bands, not two -- cosine DISTANCE, so smaller is more similar.
#   d <  FACE_MATCH_MAX_DISTANCE    -> recognised, greet by name
#   in between                      -> UNCERTAIN: silent, recorded present but unnamed
#   d >= FACE_STRANGER_MIN_DISTANCE -> confidently unknown, ask who they are
# The middle band is not a nicety. With a single threshold every uncertain match becomes a loud
# "Stranger Danger!" at an enrolled person in poor lighting, which is the failure FR-2100-003
# exists to prevent. Announcing a stranger requires positive evidence of DISSIMILARITY, not
# merely the absence of a match.
#
# Both numbers are STARTING POINTS FOR TUNING, not measured values. Ship
# scripts/tune_face_threshold.py alongside and sweep them against real enrolments. This project
# already carries one threshold that reads as tunable and is not -- HAILO_LLM_CONFIDENCE_FLOOR=0.7,
# recorded in FRD G-6 as exactly that and still an open risk. Do not add a second.
FACE_MATCH_MAX_DISTANCE=0.40
FACE_STRANGER_MIN_DISTANCE=0.60
# Cap per identity, oldest evicted. Rescued matches (FR-2100-003) add vectors over time, so
# without a cap an identity accumulates hundreds and matching slows for no accuracy gain.
FACE_MAX_VECTORS_PER_IDENTITY=12
# A person is greeted once per session; a session ends once they have been unseen this long.
# Long enough that walking in and out of the room does not re-trigger it, short enough that
# coming back after lunch feels like being noticed.
FACE_GREET_SESSION_S=1800
MEMORY_REPLAY_SIMILARITY_FLOOR=0.6  # FR-1900-003: below this, report mismatch rather than replay
STUCK_TIMEOUT=3.0; BACK_UP_TIME=0.8; TURN_TIME_90=1.2; IDLE_TIMEOUT=30.0

# Owner decision 2026-08-20: autonomous ROAM relies on sonar alone for obstacle avoidance and was
# wandering into things it couldn't sense, tripping repeated STALL_FAULTs. Gate _idle()'s
# auto-ROAM behind this flag — default off. Manual/voice-commanded driving is unaffected, this
# only blocks the unprompted idle-timeout wander.
# NOTE 2026-08-21: the original note said "until vision is live-verified; flip to True then".
# Vision now IS live-verified (ENABLE_HAILO_VISION above) — but that does NOT satisfy this gate.
# Vision feeds world_model.py for planning/classification only; it is deliberately kept out of
# the reflex/obstacle path (see CLAUDE.md's "keep the NPU out of the safety path"), so ROAM is
# still sonar-only for avoidance and the 2026-08-20 reason is unchanged.
#
# OWNER DECISION 2026-09-07 — flipped to True with the sonar-only limitation ACCEPTED, not
# resolved. Nothing above was fixed: obstacle avoidance is still sonar-only, so the 2026-08-20
# failure mode (wandering into what sonar can't see, repeated STALL_FAULTs, once 5 of 6 wheels
# at a time) can recur unattended. Three items were open at the moment of the flip, all of
# which bear on unprompted driving:
#   1. MOTOR_PORT is unverified since 2026-09-04 — it replaced a bench-measured mapping with an
#      assumed one, so per-wheel stall attribution and odometry may name the wrong wheel.
#      See CLAUDE.md's motor-port pitfall and Master Hardware Design v2.0 §7.2.
#   2. The STUCK-state on-device reasoning that ROAM depends on is FRD v3.1 G-6. ~~The Hailo
#      LLM scored 0% on the 32-case intent batch and has not been re-benchmarked.~~ Root cause
#      found 2026-09-14: the prompt was sent without ChatML role framing, so the model echoed
#      the prompt template instead of answering it. Re-measured after the fix: 78% of utterances
#      now produce an action the rover can carry out, up from 16%. Better, NOT solved -- roughly
#      one in five still misfires, and the remaining errors are confident ones the 0.7 floor
#      cannot catch, so a wrong STUCK decision can still reach arbitration.
#   3. ~~HAILO_LLM_CONFIDENCE_FLOOR=0.7 is a guessed number, never tuned against real output.~~
#      It is a boolean structural gate, not a threshold -- there is nothing to tune. The real
#      residual risk on this path is a STRUCTURALLY VALID but semantically wrong action
#      ("forward, 2s" into the obstacle that caused the STUCK), which scores 1.0 and proceeds
#      without cloud review. safety.py's clamps and the reflex layer are what stand between that
#      and the wheels -- not this number.
#      ~~It can now be tuned for the first time.~~ Corrected hours later the same day: it
#      CANNOT be tuned, because it is compared against a binary structural check rather than the
#      model's self-report (see its own comment above). What IS measurable, and now measured, is
#      the self-report on the VOICE path: 88% of answers scoring >= 0.7 were right (73 of 83 over
#      96 calls, experiments/results/2026-09-14-hailo-qualification.json). Roughly one confident
#      answer in eight is wrong, and the wrong ones self-report 0.8-1.0.
# Set back to False if Willie starts tripping STALL_FAULTs unattended.
ENABLE_AUTONOMOUS_ROAM=True

# OWNER DECISION 2026-09-09 -- ENABLE_AUTONOMOUS_ROAM above no longer means "roams unattended"; it
# means "allowed to ASK". Willie now requests permission before starting an unprompted wander, and
# the grant lives for the session only (brain.py::_roam_allowed and friends). This does not fix any
# of the three open items listed above -- obstacle avoidance is still sonar-only and MOTOR_PORT is
# still unverified -- it puts a human in the loop each boot so those limitations are accepted
# knowingly rather than discovered by a STALL_FAULT nobody was there to see.
#
# Set False to restore the pre-2026-09-09 behaviour exactly: roams on the idle timeout and on
# charged-to-95%-at-the-dock with no ask, unattended.
ROAM_PERMISSION_REQUIRED=True
ROAM_ASK_TIMEOUT_S=30.0     # how long the spoken/on-screen ask stays open before it lapses
# A declined ask and an unanswered one land in the same place: this cooldown, then he asks again.
# Refusal is deliberately not permanent -- "no" usually means "not now", and nobody answering
# usually means nobody heard. 10 minutes is long enough not to nag.
ROAM_ASK_COOLDOWN_S=600.0

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

    i2c_addrs={'ENCODER_ADDR':ENCODER_ADDR,'INA260_5V_ADDR':INA260_5V_ADDR,
               'STEER_PCA_ADDR':STEER_PCA_ADDR,'ARM_PCA_ADDR':ARM_PCA_ADDR,
               'INA260_BUS_12V_ADDR':INA260_BUS_12V_ADDR,'INA260_ARM_6V_ADDR':INA260_ARM_6V_ADDR,
               'ADS_ADDR':ADS_ADDR,'IMU_ADDR':IMU_ADDR,
               'MOTORKIT_LEFT_ADDR':MOTORKIT_LEFT_ADDR,'MOTORKIT_RIGHT_ADDR':MOTORKIT_RIGHT_ADDR}
    seen={}
    for name,addr in i2c_addrs.items():
        if addr in seen: problems.append(f'duplicate I2C address {addr:#x}: {seen[addr]} and {name}')
        else: seen[addr]=name

    # 44100 is the trap here: the mic advertises it, it looks perfectly reasonable, and it is not
    # an integer ratio to openwakeword's 16000. Catch it here rather than on the audio thread.
    if AUDIO_INPUT_RATE%16000:
        problems.append(f'AUDIO_INPUT_RATE={AUDIO_INPUT_RATE} is not a whole multiple of 16000 '
                        f'(openwakeword frame rate); decimation would be fractional')

    gpio_pins={'SONAR_FRONT_TRIG':SONAR_FRONT_TRIG,'SONAR_FRONT_ECHO':SONAR_FRONT_ECHO,
               'SONAR_LEFT_TRIG':SONAR_LEFT_TRIG,'SONAR_LEFT_ECHO':SONAR_LEFT_ECHO,
               'SONAR_RIGHT_TRIG':SONAR_RIGHT_TRIG,'SONAR_RIGHT_ECHO':SONAR_RIGHT_ECHO}
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
