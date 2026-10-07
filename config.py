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
# SIMULATION NEVER WRITES THE REAL STORES (2026-10-02). Running the test suite on the rover wrote
# simulated BATTERY_HALT events into the real logs/willy.log -- which feature_requests.py reads as
# evidence -- and full-sim brain tests open memory.db/world_model.db in the repo. Under
# WILLY_SIMULATE, any root not set explicitly goes to a throwaway directory instead.
if SIMULATE_HARDWARE:
    import tempfile as _tf
    _SIM_ROOT=os.path.join(_tf.gettempdir(),'willy-sim')
    for _env,_name in (('WILLY_DATA_ROOT','WILLY_DATA_ROOT'),('WILLY_MAP_ROOT','WILLY_MAP_ROOT'),
                       ('WILLY_MEMORY_ROOT','WILLY_MEMORY_ROOT'),('WILLY_LOG_ROOT','WILLY_LOG_ROOT')):
        if not os.environ.get(_env):
            globals()[_name]=os.path.join(_SIM_ROOT,'logs' if _name=='WILLY_LOG_ROOT' else '')
    os.makedirs(os.path.join(_SIM_ROOT,'logs'),exist_ok=True)

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
#
MOTOR_PORT={'lf':(MOTORKIT_LEFT_ADDR,3),'lm':(MOTORKIT_LEFT_ADDR,2),'lr':(MOTORKIT_LEFT_ADDR,1),
            'rf':(MOTORKIT_RIGHT_ADDR,3),'rm':(MOTORKIT_RIGHT_ADDR,2),'rr':(MOTORKIT_RIGHT_ADDR,1)}
# MIRRORED MOTORS, 2026-10-01. Every motor is mounted harness-end OUTWARD, so the left and
# right motors face opposite ways, and both sides are wired the same (owner-stated). The
# same throttle therefore turns the two sides opposite ways at the ground. Until this sign
# existed, motors._set() sent both sides the same value: forward() pivoted him in place and
# turn_left()/turn_right() drove him straight. Observed on the block the same day: +0.6 on
# lf rolled forward, +0.6 on rf rolled BACKWARD, so the right side is negated. Only lf and
# rf were watched; rm/rr follow on the owner's word that all six are mounted and wired
# alike. motors.py applies this at the one place it writes throttle, so everything above
# it -- _target, _actual, current_speed -- stays in rover terms (+ = forward). Scripts that
# drive a single wheel raw (wheel_current_test, breakaway_sweep) bypass it, which is fine:
# they measure current and |counts|, not direction. Phase-A-only counts have no sign, so
# telemetry cannot see a wrong entry here -- watch the wheels.
MOTOR_SIGN={'lf':1,'lm':1,'lr':1,'rf':-1,'rm':-1,'rr':-1}
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
# HISTORY, from when these were PWM duty -- SLOW 0.55 -> 0.60 on 2026-10-01, after the 170 RPM / 35.5:1 motors went in. The
# prediction that more reduction would drop breakaway well below 0.5 did not hold for
# every wheel: scripts/breakaway_sweep.py, wheels free, found 0.15-0.35 on four wheels
# but lm at 0.40-0.50 and rf at 0.45-0.55 from rest (rf failed to move at 0.50 twice
# across five sweeps). Owner accepted the motors as-is, expecting break-in, so SLOW
# carries margin over rf on the block -- loaded on the floor needs more, not less.
# Re-run the sweep after some hours of use; this should come down.
# SPEEDS IN MPH (owner, 2026-10-02): slow 0.5, cruise 1.0, cap 1.5. Since closed-loop wheel
# speed control (FR-500-004, motors.wheel_duty) the SPEED_* values below are FRACTIONS OF THE
# CAP, not PWM duty: 1.0 = SPEED_MAX_MPH. The motors top out near 147 RPM free (~1.8 mph), so
# the 1.5 mph cap leaves headroom for the loop; 3 mph would need ~250 RPM (different motors).
SPEED_MAX_MPH=1.5; SPEED_ROAM_MPH=1.0; SPEED_SLOW_MPH=0.5; SPEED_TURN_MPH=1.0
SPEED_MAX=1.0
SPEED_ROAM=SPEED_ROAM_MPH/SPEED_MAX_MPH; SPEED_SLOW=SPEED_SLOW_MPH/SPEED_MAX_MPH
SPEED_TURN=SPEED_TURN_MPH/SPEED_MAX_MPH
# FR-500-004 closed-loop wheel speed (2026-10-02). Each wheel's duty = feed-forward from its
# measured duty->RPM line + a PI trim from its encoder. Off -> feed-forward only (open loop).
WHEEL_SPEED_CONTROL=True
# Feed-forward per wheel: RPM ~= slope*(duty-d0), fitted to scripts/breakaway_sweep.py,
# wheels free, 2026-10-02 (rf was disconnected -> default). Loaded on the floor reads lower;
# the PI trim makes that up, and a re-fit after break-in keeps the trim small.
WHEEL_FF={'lf':(0.163,225.0),'lm':(0.229,195.0),'lr':(0.192,231.0),
          'rf':(0.22,225.0),'rm':(0.271,211.0),'rr':(0.285,273.0)}
WHEEL_KP=0.002        # duty per RPM of error
WHEEL_KI=0.008        # duty per RPM-second of error
WHEEL_TRIM_MAX=0.30   # the PI may move duty at most this far from feed-forward: a blocked
                      # wheel gets a bounded push, and stall detection still stops it at
                      # STALL_GRACE_S (Directive 5)
# Seconds of being stopped AND fully ramped down before the bridges are released and the
# two MotorKit PCA9685s are put to sleep. Measured 2026-09-30: the +12V motor branch idles
# at 0.019A holding six stopped wheels in adafruit_motor's hard-brake -- about 0.2W spent
# to hold nothing. brake() is exempt: ESTOP wants the wheels held, not coasting.
# ~ Raise this if the rover is ever parked on a slope; a released 35.5:1 gearbox has high
#   backdrive resistance but it is not a parking brake.
MOTOR_COAST_AFTER_S=2.0

# --- servo idle release -------------------------------------------------------------
# A servo holds its angle only while it is receiving pulses. Stop the pulses and it goes
# LIMP. That is the point -- and the hazard.
#
# WHY THIS IS NOT ABOUT BATTERY. Idle draw measured 2026-09-30 is 0.23W on R2 and 0.35W on
# R3, which is nothing against a ~333Wh pack (2x 3S 15000mAh since 2026-10-05). The real reason is arm.py's note: the servo
# fitted before 2026-09-17 "held ~8A at 1500us indefinitely and was destroyed by it". A
# servo stalling against its own mechanism cooks itself in minutes, and releasing an idle
# joint is what prevents that. Treat this as servo protection that happens to save power.
#
# ⚠ THE ARM WILL FALL when released, to wherever gravity and its stops take it. The delay
#   is longer than steering's for that reason, and the first test should be done with the
#   arm LOW and nothing underneath it. Set ARM_RELEASE_WHEN_IDLE=False to disable.
STEER_RELEASE_AFTER_S=2.0
ARM_RELEASE_AFTER_S=10.0
ARM_RELEASE_WHEN_IDLE=True
SPEED_RAMP_PER_S=2.0  # FR-400-003: max throttle change per second (slew rate), full range in 0.5s
TURN_INNER_SCALE=0.0

# Sonar (§8.1 master doc) — FRONT_ECHO/LEFT_ECHO were wired to GP11/GP19 here, which do not match
# the documented harness (GP26/GP14) and aren't connected to anything real — front/left obstacle
# detection has likely been silently reading 999cm (no obstacle) on every call. Fixed 2026-08-02.
# SONAR PIN CONSTANTS REMOVED 2026-09-30. They named GP5, GP13 and GP4, which the
# uart2-pi5 and uart4-pi5 overlays now claim as TXD2, RXD4 and RXD2 -- pinctrl confirms
# it. The three HC-SR04s are read by Pico B and arrive as $S frames over uart2-pi5, so
# nothing on the Pi times an ECHO line any more. Master Hardware Design section 4.7.
SONAR_INTERVAL=0.05
# Furthest a fresh "no echo" reading means. A -1 on a channel whose frame is FRESH is
# the Pico saying it pinged and heard nothing -- for a sensor pointed at an open room
# that is true, and it means clear, not broken. Distinct from a stale link, which means
# stop. Software Design S-9.
SONAR_MAX_CM=400.0
# How old a $S frame may be before sonar is treated as UNKNOWN, which means STOP.
# 33 Hz nominal, so this is ~10 missed frames -- long enough not to trip on jitter,
# short enough that a dead link cannot be driven through.
SONAR_STALE_S=0.30
DIST_STOP=20; DIST_SLOW=40; DIST_CLEAR=60; DIST_SIDE_CLEAR=25
# FR-1000-002 turn choice (avoidance.py, owner 2026-10-06): the front camera's detections bias
# WHICH WAY he turns. Never whether he stops -- Master Hardware Design §12 rule 15.
AVOID_USE_CAMERA=True
# Rotation mode (rotate.py, owner 2026-10-07): corners steered onto the turning circle, spin on IMU.
ROTATE_SPEED=1.0              # fraction of the mph cap for the corners; a skid turn needed full duty
ROTATE_SETTLE_S=0.6           # steering reaches its angle before any wheel drives
ROTATE_RESTEER_S=0.5          # re-assert the corner pulses, ahead of STEER_RELEASE_AFTER_S
ROTATE_STOP_EARLY_DEG=10.0    # stop this short; live 2026-10-07 he coasted ~6 deg past a 5 deg early stop
ROTATE_TIMEOUT_S=8.0          # a turn that is not happening, not a turn that is slow
ROTATE_CLEAR_CM=15.0          # anything nearer than this on any sonar/ToF stops the spin
# Pre-spin clearance on front/left/right (rotate.py _room_to_turn). Footprint ~0.42 x 0.41 m (length
# ESTIMATED as wheelbase + one wheel diameter; width owner-measured 41 cm): the corners sweep a
# 0.29 m radius, ~9 cm beyond the body on each side, plus margin. Arm or anything else sticking out
# is NOT included -- re-check if the arm rests outside the body.
ROTATE_START_CLEAR_CM=20.0
ROTATE_WRONG_WAY_DEG=10.0     # heading moving this far the wrong way = stop
# Blocked-turn stop (2026-10-07: spun into the couch, pushed 8 s until the timeout). After the spin
# has had ROTATE_STALL_ARM_S to break away and ramp, heading moving slower than this rate across
# the window = something is in the way. Live good turns ran ~25-50 deg/s.
ROTATE_STALL_ARM_S=1.0
ROTATE_STALL_WINDOW_S=0.7
ROTATE_STALL_MIN_RATE_DPS=5.0
ROTATE_STALL_WHEEL_CPS=100.0  # mean |counts/s| above this = wheels still turning (slip, not stall)
ROTATE_MIN_DEG=5.0
ROTATE_USE_CAMERA=True
ROTATE_CAMERA_HFOV_DEG=66.0   # imx708 standard lens, horizontal (datasheet), not bench-measured
ROTATE_REAR_CAMERA_HFOV_DEG=70.0  # rear Arducam OV9281 (UC599), global shutter -- NOT measured, a typical figure
ROTATE_CAMERA_MIN_RESPONSE=0.5    # phase-correlation quality; below it a frame is blurred = no measurement
ROTATE_CAMERA_MIN_MATCHED_DEG=20.0  # IMU rotation over a camera's clear frames before it may judge
ROTATE_CAMERA_MAX_DISAGREE_DEG=25.0
ROTATE_CAMERA_MAX_DISAGREE_FRAC=0.4
# First live run 2026-10-07: IMU 46 deg (owner: the turn was good) vs camera 17 deg -> stopped. The
# camera estimate under-reads; until the cause is found it can be set to log-only (False).
ROTATE_CAMERA_STOP=True
AVOID_CAMERA_CENTRE_DEG=5.0
AVOID_USE_ROTATION=True       # brain._avoid turns in rotation mode (rotate.py); False = the old skid turn   # a detection this close to dead ahead counts for neither side

# --- FR-1000-002 / FR-1200-005 multi-zone ToF (DFRobot SEN0628, Master Hardware Design §6.5).
# Front obstacle sensing ALONGSIDE the sonar, never replacing it: the two fail in opposite
# directions. Sonar is blind to chair legs, soft furnishings and angled surfaces; ToF looks
# straight THROUGH glass, which sonar reflects off perfectly well.
ENABLE_TOF=True             # fitted and answering (5/5 clean frames 2026-10-02). Reports NOTHING
                            # until scripts/calibrate_tof_floor.py has captured a floor profile.
TOF_POLL_S=0.05             # background reader cadence; a frame itself takes ~0.13 s
TOF_FRAME_MAX_AGE_S=0.5     # an older frame is no frame -> sonar alone
TOF_PORT='/dev/ttyAMA3'     # UART, not I2C -- keeps it off a bus that took the whole rover down
                            # twice on 2026-09-07/08. CONFIRM the Pi 5 overlay->pin mapping first
                            # (§6.5): the Pi 4 mapping does not carry over to the RP1.
TOF_BAUD=115200             # fixed in the sensor's firmware, not configurable
TOF_ZONES=64                # 8x8. A frame of any other length is a desynchronised UART, not data
TOF_ZONE_COLUMNS=8          # zone index % this = column
# Which zone columns look LEFT (FR-1000-002 turn choice, avoidance.py). RE-MEASURED 2026-10-07 after
# the sensor was refitted in a new housing ROTATED 180 deg: an upright tin on Willie's left (front-
# camera photo as witness) showed in columns 0-1 only. LEFT = columns 0-3; row 7 is the BOTTOM of the
# view (near floor). Before the rotation it was columns 4-7 and row 0 at the bottom. ANY remount
# re-opens this -- re-run the tin test. None means "unknown" and turns the ToF's side input off.
# New housing: the 0-5 cm window-edge returns are gone (2026-10-07 baseline, nothing under 36 cm).
TOF_LEFT_COLUMNS=(0,1,2,3)
# Rows the floor profile keeps (scripts/calibrate_tof_floor.py); all others are NO_DATA. MEASURED
# 2026-10-07 in this mounting: rows 6-7 see floor at 37-60 cm, even across all columns, repeatable to
# a cm or two between captures; rows 0-5 see the room at 1.3-1.8 m. Tied to the mount like the
# columns -- re-check after a remount. None = keep every row.
# TRADE-OFF: NO_DATA zones never report an obstacle, so the ToF now sees only what blocks its view of
# the floor band (anything nearer than ~60 cm low down). Sonar still covers the rest.
TOF_FLOOR_ROWS=(6,7)
# Floor-profile margin. A zone counts as an obstacle only when it returns this much SHORTER than
# its own stored floor distance, and as a drop when it returns this much LONGER (or nothing).
# Wide enough to absorb carpet pile, a rug edge and a few mm of ride height -- without a margin
# every surface change reads as an obstacle and he never moves.
TOF_FLOOR_MARGIN_MM=120.0
TOF_FLOOR_PROFILE_PATH='tof_floor_profile.json'
TOF_PROFILE_SAMPLES=10      # frames averaged when capturing; one frame carries per-zone noise
                            # straight into the baseline everything else is measured against

# I2C bus 1 clock. THE KERNEL IS AUTHORITATIVE, NOT THIS CONSTANT -- the bus speed is set by
# dtparam=i2c_arm_baudrate in /boot/firmware/config.txt and needs a reboot. This value exists so
# sensors.py has one number to pass to busio.I2C() instead of a hardcoded literal that silently
# disagrees with the kernel, and so the intended speed is recorded somewhere a reader will find.
# Keep the two in sync by hand; scripts/i2c_bus_check.py reports the kernel's actual value.
#
# 100000 is the Pi default and what this bus has always run at. 400000 is a candidate worth
# ~4x on every transaction -- the BNO085 alone is polled at IMU_POLL_HZ=100 and clock-stretches,
# which costs more at the lower speed. It is NOT a free change: Master Hardware Design v2.0 s3.2
# computes ~2.2us to threshold from the Pi's 1.8k pull-ups into ~400pF of cabling, against a
# 2.5us bit at 400kHz. That is marginal on paper, and the LTC4311 accelerator is fitted for
# exactly this reason. Validate with scripts/i2c_bus_check.py (20 consecutive clean roll-calls,
# zero new kernel i2c errors) BEFORE leaving it raised. Revert on any device dropping out.
I2C_BAUDRATE=100000

IMU_ADDR=0x4A; IMU_TILT_LIMIT=25; IMU_TILT_WARN=18; IMU_POLL_HZ=100  # BNO085, §8.2/§8.5
# Hardware-reset recovery, 2026-10-01 (sensors.IMU._poll_once). 10 consecutive failed reads is
# 0.1 s at IMU_POLL_HZ -- long enough that one I2C hiccup never pulses RST, short enough that
# recovery starts before anyone notices. At most one recovery per 10 s: a chip that will not
# come back must not be hammered, and brain.py's SENSOR_FAULT already stops motion while the
# IMU is down (is_healthy goes false on its own deadline).
IMU_RESET_AFTER_FAILS=10; IMU_RESET_MIN_INTERVAL_S=10.0
# A quaternion unchanged for this long is a FAILED read, not a still rover. Measured 2026-10-01
# at rest: 101 distinct values in 10 s (~10 Hz reports), longest identical run 0.50 s. The case
# it exists for: a reset the driver did not cause leaves it returning its cached value forever
# with no error, so without this, tilt would freeze and nothing would notice.
# 2026-10-02: raised to 3.0 and judged on quaternion PLUS raw acceleration. On the blocks,
# perfectly still, the fused quaternion stayed bit-identical for up to 3.7 s with the service
# stopped (reports had dropped to ~5 Hz), so the 1.5 s quaternion-only check latched a false
# SENSOR_FAULT every ~15 s. Accelerometer noise changes whenever a report actually arrives.
IMU_STALE_S=3.0
# RST: see the note below. It is no longer an expander pin.
# IMU_RST_MCP_PIN REMOVED 2026-09-30 with the expander that hosted it. Section 4.7
# consequence 1 moves the BNO085 reset to Pico B GP15, open-drain against R4, exposed as
# an explicit acknowledged RST command over uart2-pi5. That direction was dead until
# 2026-10-01 -- cold solder joints on the one wire, Pi phys 7 to c27 -- and is now proven:
# PING, ID and BOGUS all answered. RST itself has not yet been sent.

# Steering — PCA9685 @0x42, CH0-3 and CH8-9 since 2026-10-05 (§3.1/§10). Servo mode (500-2500/1000-2000/900-2100us) is
# unconfirmed per-unit — default to the narrowest documented range so a narrow-mode servo can't
# be driven into a mechanical bind. Widen only after a bench check confirms a unit's real range.
# Steering kinematics (wheel-angle coordination, crab/point-turn) are undesigned in the master
# doc (§10: "pending in software") — this pass only centers all six and holds them there.
STEER_PCA_ADDR=0x42
# Channels as re-plugged by the owner 2026-10-05, each one MEASURED 2026-10-06: one channel swung
# 1000<->2000us at a time with the owner naming the wheel. Not a pattern -- the fronts and rears
# have right on the lower channel, the middles have left. Do not "tidy" it.
# INA260 0x40 showed NO current change while a steering servo swung (0.51-0.54A flat), so the
# servo V+ is not on that monitor's path: current cannot confirm steering motion, only eyes can.
STEER_LF=3; STEER_RF=2; STEER_LM=0; STEER_RM=1; STEER_LR=9; STEER_RR=8
SERVO_CENTER_US=1500; SERVO_MIN_US=1000; SERVO_MAX_US=2000
# Per-corner straight-ahead pulse. All six were mechanically re-horned straight at 1500us on
# 2026-10-05, so 1500 is measured, not nominal; the earlier trims (1800/1350/1270) are void.
# Fine-tune with scripts/steer_jog.py if a wheel is visibly off.
STEER_CENTER_US={'lf':1500,'rf':1500,'lm':1500,'rm':1500,'lr':1500,'rr':1500}
# Steering direction and scale, owner-measured 2026-10-07 by eye, each corner ALONE to 1700 us:
# all four corners point RIGHT for +us, ~15 deg per 200 us. The rear servos are mounted reversed
# from the fronts, but the wheel still went right -- measure, don't infer from the mounting.
# Middles not measured (rotation keeps them straight). 1 = +us turns the wheel right.
STEER_RIGHT_SIGN={'lf':1,'rf':1,'lr':1,'rr':1}
STEER_US_PER_DEG=200/15.0
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
#   gripper  CH5 : INCREASING us closes, decreasing opens. LONGER FINGERS fitted by 2026-10-05:
#                  jaws now shut at ~2205us (0.39A); 2210us drew 0.49A = stalling. Widest open
#                  without load is 1150us (0.07A); the open stop is ~1100 and 1050us stalls at 0.8A. The ~1700us
#                  contact point and the current figures below are from the old, shorter fingers.
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
ARM_WAVE_STEP_S=0.06            # time between shoulder steps (2026-10-02, brain._wave)
ARM_WAVE_CYCLES=4
ARM_WAVE_LEG_S=0.35
# Where the wave returns to: ARM_POSE_REST with the wrist at 2300us, the low-current variant noted
# under ARM_POSE_REST (0.23A vs 0.87A at 2450). The elbow is clamped to ARM_SERVO_MAX_US by arm.py.
ARM_REST_WRIST_US=2300
#
# Any arm motion should watch INA260 ARM_6V current and release the arm when it stays above this
# for this long. A threshold checked only AFTER a move completes is useless -- that is how the
# first elbow servo was destroyed. ENFORCED since 2026-10-02 by brain._check_arm_current(), every
# tick (~20 Hz) rather than inside each movement loop, so it covers every arm motion. Arm.release()
# sleeps the whole PCA9685: EVERY arm channel goes limp, not just the straining one.
ARM_CURRENT_LIMIT_A=2.5
ARM_CURRENT_LIMIT_S=0.4
# FR-200-002 overcurrent, per INA260 rail (2026-10-02). Limits are 90% of the branch fuse
# (MHD §2.1: F2 10A motors, F4 10A DROK-5V), so software stops the load before the fuse goes.
# Held for OVERCURRENT_S, so a motor start or a steering slew does not trip it. The arm rail
# has its own, tighter limit above (servo protection, releases the arm).
OVERCURRENT_LIMIT_A={'bus_12v':9.0,'steering_5v':9.0}
OVERCURRENT_S=1.0

# Wheel encoders — Pico A over uart4-pi5 (§4.7). SIGNED x2 quadrature since firmware a-0.3
# (2026-10-01): both Phase A edges counted, Phase B sampled for direction; Phase B is alive on
# all six. ENCODER_COUNTS_PER_REV=763 is measured (one wheel, under power) -- see its own note.
# ENCODER_ADDR REMOVED 2026-09-30. The MCP23017 is off the bus; a live scan returns ten
# devices and none of them is 0x27. Encoder decode is Pico A's job now, over uart4-pi5.
PICO_A_DEVICE='/dev/ttyAMA4'   # uart4-pi5, Pi GP12/GP13 -- encoders + R5 rail sense
PICO_B_DEVICE='/dev/ttyAMA2'   # uart2-pi5, Pi GP4/GP5  -- sonar + BNO085 reset
# Identify a board by UID, never by port: the port follows the USB slot, not the board.
PICO_A_UID='643f69a756a232ea'
PICO_B_UID='ad25bbf0f1e1f160'
# $E arrives at 50 Hz. Ten missed frames before the encoders are considered unknown --
# at which point every wheel reads as stalled, which is the safe direction.
ENCODER_STALE_S=0.20
# R5 (the encoders' 3.3V rail) below Pico A's R5_WARN_MV (3000) for this long -> warn and name it.
# WARN ONLY, owner decision 2026-10-01: no stop on this. Nobody has measured the voltage these
# encoders quit at, and if they do quit, the stall and health checks already stop motion -- this
# makes the status and the stop reason say "encoder rail" instead of blaming six wheels, which is
# what the 2026-08-25 sag looked like. Grace so one low ADC sample does not raise it.
ENCODER_R5_GRACE_S=0.5
ENCODER_POLL_HZ=50.0
# MEASURED 2026-09-18 (E-1) -- LEFT AND RIGHT WERE TRANSPOSED, the same swap found on the
# motor boards the same day (see MOTOR_PORT above). The encoders were landed at the same time
# as the motors, so the same left/right confusion propagated into both. Master Hardware Design
# 7.2 predicted exactly this: the encoder column "may follow the physical wheels, or the port
# permutation, or neither".
#
# Method, SUPERSEDED 2026-09-29 and kept only because the reasoning still holds. It used to be:
# drive one wheel 1.0s and compare the MCP23017's resting state before and after, over six
# trials, because a pin on that wheel's encoder changes on most trials while one picking up PWM
# crosstalk changes rarely. That was a workaround for an I2C poll too slow to see edges.
# Pico A counts every edge in PIO, so the question is now answered directly: drive one wheel
# and read which channel's count moves. Done on blocks 2026-09-29, five wheels, unambiguous.
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
# ENCODER_PINS REMOVED 2026-09-30 with the expander. ⚠ AND IT WAS WRONG: it disagreed
# with the as-built landing in Master Hardware Design 16.6 by a left/right swap at every
# position, and the firmware's WHEELS tuple had inherited the same error. Proved on
# hardware 2026-09-29, one wheel at a time on blocks: driving lf counted on GP0/GP1, rf
# on GP4/GP5, lm on GP2/GP3, rm on GP6/GP7, rr on GP10/GP11 -- the as-built table, five
# for five. The order now lives in ONE place, firmware/pico_a.py's WHEELS, and reaches
# the Pi in the frame itself.
# 763 since Pico A firmware a-0.3 (2026-10-01): x2 quadrature, both edges of A with B sampled
# at each, SIGNED. That is exactly twice the x1 figure measured below the same day -- the same
# edges, both of them counted -- so it is derived from a measurement, not from a datasheet.
# The x1 measurement, for the record:
#
# MEASURED 2026-10-01: 382 counts per wheel revolution, on the fitted 170 RPM motors
# (JGA25-370-35.5K) and the then transport -- Pico A counting Phase A rising edges only (x1).
# Method: drove lf at 0.35 until Pico A had counted 3905, hard-braked (final 3911, 6 of coast);
# a tape mark on the tyre made 10.25 turns. 3911 / 10.25 = 381.6, +/- ~5 from judging the stop
# to an eighth of a turn. 2.3% under the 11 PPR x 35.5 = 390.5 prediction: the effective
# reduction is ~34.7:1, not the nominal 35.5. One wheel; the other five are the same part.
#
# MEASURE UNDER POWER, NOT BY HAND. Hand-turning lf ten times counted 459, then 0, while the
# same encoder counted ~475/s driven -- back-driving the gearbox slips the hub on the shaft.
# scripts/encoder_calibration.py's hand-turn method is not valid on this rover.
#
# THE CHAIN THIS ENDS, every link derived and none measured: 3292 ("823.1 PPR x4", a 74.8:1
# gearbox that never existed) -> 752 (11 x4 x 17.1, 2026-08-25) -> 422 (11 x4 x 9.6 from the
# vendor table, never set) -> 1562 (11 x4 x 35.5, assumed x4 quadrature this transport does
# not do). odometry.py divides by this, so at 752 every distance read 752/382 = 1.97x short.
#
# PHASE B WAS NEVER BROKEN ON THESE MOTORS: the dead greens were the old ones. Found alive on
# all six new motors 2026-10-01 and decoded from a-0.3 the same day. If the firmware ever moves
# to full x4, this doubles again (~1526) -- the frame format would not change, so re-measure.
ENCODER_COUNTS_PER_REV=763
# Which count sign is rover-FORWARD, per wheel. Pico A sends the board's raw sign; measured
# 2026-10-01 on a-0.3, each wheel alone on the block: +throttle -> +counts on all six. The
# motors are mirrored (MOTOR_SIGN), so forward is +counts on the left and -counts on the right.
# odometry.py applies this; Encoders.counts stays raw. Kept separate from MOTOR_SIGN because a
# swapped encoder pair on one motor would flip this and not that.
ENCODER_SIGN={'lf':1,'lm':1,'lr':1,'rf':-1,'rm':-1,'rr':-1}

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
WHEELBASE_M=0.320      # front axle to rear axle, centre to centre, owner-measured 2026-10-07
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
INA260_BUS_12V_ADDR=0x45 # +12V bus (battery via F1/SW-MAIN/Q1) -> both FeatherWing VIN. Reads
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

ADS_ADDR=0x48; ADS_CH_BATTERY=0  # AIN0 = battery divider. A1 spare (FSR402 removed 2026-10-04).
# GRIPPER POSITION FEEDBACK on AIN2 (2026-10-04, replaces the FSR402). The gripper MG90S (arm CH5)
# is modified: a wire is soldered to its pot wiper and runs to a 47k/47k divider + 100 nF at the
# ADS1115 end (MHD §6.6). The divider is there because the wiper swings toward the 6V arm rail and
# the ADS1115 runs on 3.3V. 47k keeps the load on the servo's own pot to ~1%. Not yet calibrated:
# scripts/grip_feedback_curve.py records wiper volts against commanded us.
ADS_CH_GRIP_FB=2
GRIP_FB_DIVIDER_SCALE=0.5  # 47k/(47k+47k); ADS1115 input impedance pulls the reading ~0.4% low
# Gripper end points with the longer fingers, measured 2026-10-05 (see the CH5 note above).
GRIP_OPEN_US=1150; GRIP_CLOSED_US=2205
GRIP_OPEN_WIDTH_MM=73   # jaw gap at GRIP_OPEN_US, owner-measured; 0 at GRIP_CLOSED_US
# Re-trimmed 2026-10-01: AIN0 read 2.7653V (raw ~22120, 40 samples) against the pack metered at
# 11.37V at the divider input. Scale = 2.7653/11.37 = 0.2432 -- within 0.4% of the 10k/3.197k
# = 0.2423 that Master Hardware Design §16 specifies. The divider now matches its design.
#
# WHY IT MOVED: the 2026-09-17 trim (0.3237, ~10k/4.7k) was measured against the OLD bus node
# board, whose low side was ~4.7k rather than the drawn 3.2k. The rev 15.1 board is built to the
# drawn value (MHD §6.2), which already flagged 0.3237 as wrong for it. Nobody re-trimmed, and
# the stale 0.3237 read a healthy 11.37V pack as 8.53V: below BAT_SHUTDOWN_V, so Willie walked
# IDLE->SHUTDOWN on his own. A scale change this size is a divider change, not drift.
# ONE-POINT calibration: §6.2 asks for two points across the range -- repeat near 12.6V
# (full) and near 10.5V when the chance arises.
#
# HEADROOM: at PGA ±4.096V the ADC now represents up to 4.096/0.2432 = 16.8V, so a full or
# on-charger 3S pack (12.6V) reads correctly. The 12.65V ceiling of the 0.3237 era is gone.
#
# Previous values: 0.2481 (MCP3008-era), 0.2865 (2026-08-02), 0.2386 (2026-08-16),
# 0.3237 (2026-09-17, old bus node board). If this ever disagrees with a meter again, check the physical
# divider connection before recalibrating.
BATTERY_DIVIDER_SCALE=0.2432

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
BAT_RTH_V=10.8        # -> graceful halt while ENABLE_DOCKING=False; return-to-home / DOCK otherwise
BAT_SAFE_V=10.5        # -> SAFE_MODE (motion stop, arm holds)
BAT_SHUTDOWN_V=10.2   # -> controlled shutdown; also the 0% anchor for battery_pct
BAT_HYSTERESIS_V=0.2
# DOCKING IS DEFERRED (owner, 2026-10-01). With no dock, the 'rth' tier has nowhere to return
# to, so it runs FR-200-005's proactive graceful shutdown instead of driving DOCK. Flip this
# only when a dock and a route to it exist.
ENABLE_DOCKING=False
SONAR_FAULT_DEBOUNCE_S=2.0   # FR-800-004: a sonar must fail (or recover) for this long to be reported
# FR-1000-003 IMU heading in odometry (2026-10-02). OFF until checked on the rover: the BNO085's
# mounting sets the sign of its yaw relative to odometry's (CCW-positive) heading. To enable:
# turn left on the spot, confirm odometry heading and IMU.heading both increase (else set
# IMU_YAW_SIGN=-1), then set ODOM_USE_IMU_HEADING=True.
ODOM_USE_IMU_HEADING=False
IMU_YAW_SIGN=1
# FR-1000-006 search sweep: look for PURSUIT_LOOK_TICKS ticks, then turn PURSUIT_SEARCH_TURN_S,
# up to PURSUIT_SEARCH_STEPS times. Skid-turn timing is uncalibrated -- tune on the floor.
PURSUIT_LOOK_TICKS=10
PURSUIT_SEARCH_STEPS=8
PURSUIT_SEARCH_TURN_S=0.4
# FR-1200-005/006 stairs (2026-10-02). Owner decision 2026-09-11: in floor mode Willie holds
# STAIR_STANDOFF_M clear of a mapped stair edge. Stairs are labelled by voice ("stairs ahead")
# with Willie facing them; the edge is placed STAIR_LABEL_AHEAD_M in front of his centre.
# The standoff is only as good as odometry -- dead-reckoning drift moves the edge with it.
STAIR_STANDOFF_M=0.15
STAIR_DEFAULT_WIDTH_M=0.9
STAIR_LABEL_AHEAD_M=0.30
MOBILITY_MODE='floor'   # FR-1200-002: power-on default; 'stair' mode is not built
# A battery-tier halt (FR-200-004/005) powers the Pi off, so it must not fire on a transient:
# the reading has to stay below the tier's threshold, with the rover already stopped, for this
# long. Motors stopped means load sag has recovered, so this is close to a resting reading.
BAT_HALT_CONFIRM_S=10.0

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
# downstream of F1/SW-MAIN/Q1 (and, per §2.1's P3 row, SW-M), so it reads lower than the pack by the
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
# FR-1000-006 shut door (come-to-me design §4.7), ask-only -- the knock is not built.
# Blocked counts as a door only at a LABELLED doorway waypoint and within this radius of it. Wider
# than NAV_ARRIVAL_RADIUS_M because a shut door stops him DIST_STOP short of the doorway point,
# plus however far the label sits from the door leaf.
DOOR_BLOCKED_RADIUS_M=0.8
DOOR_WAIT_S=15.0               # between asks, re-checking front clearance every tick
DOOR_MAX_ASKS=3
NAV_HEADING_DEADBAND_DEG=15.0  # within this heading error, drive forward instead of turning first
NAV_TURN_STEP_S=0.2            # duration of each incremental heading-correction turn while seeking

CLAUDE_MODEL='claude-sonnet-5-5'   # owner decision 2026-10-02: Claude (not Gemini) is the cloud provider
CLAUDE_MAX_TOKENS=2000; CLAUDE_ESCALATE_AFTER=5   # headroom for adaptive thinking (Sonnet 5.5 cannot disable it)
CLAUDE_EFFORT='low'   # short structured answers; low effort keeps thinking and latency small
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
BUS_TO_PACK_DROP_V=0.08   # F1 + SW-MAIN + Q1 between the pack and the 0x45 bus monitor (11.98 vs 11.90)
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
# FR-500-003, inverse case (2026-10-02): wheels turning with NO wheel commanded -- being pushed,
# rolling down a slope, or a driver fault. Reported, not braked (an idle rover coasts on purpose,
# see motors.py). Grace covers the coast-down after a stop.
UNCOMMANDED_COUNTS_PER_S=50.0   # ~2 cm/s at 763 counts/rev on a 0.1016 m wheel
UNCOMMANDED_GRACE_S=2.0

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
# Remote commands IN from Home Assistant / Google Home (remote_cmd.py, owner 2026-10-01). Fixed
# intents only: status, battery, stop, come_here. Never starts without the token file.
ENABLE_REMOTE_CMD=True
REMOTE_CMD_PORT=8765
REMOTE_CMD_TOKEN_PATH='secrets/remote_cmd_token.txt'
REMOTE_CMD_REPLY_TIMEOUT_S=8.0   # under HA rest_command's timeout, so HA always gets an answer
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
OWNER_NAME='Howard'   # how Willie names the owner aloud ("Howard emailed: ...")
# FR-2000-012/013 email commands (owner decision 2026-09-11, built 2026-10-02). Only the owner,
# only with Gmail's own Authentication-Results showing DKIM pass ALIGNED with the From domain,
# only with a subject starting EMAIL_COMMAND_PREFIX, only if fresher than
# EMAIL_COMMAND_MAX_AGE_S, one per poll. Everything then goes through the same queue and
# Directive gating as a spoken command. Set False to shut the channel if the account is ever
# suspected compromised.
ENABLE_EMAIL_COMMANDS=True
EMAIL_COMMAND_PREFIX='willie'          # subject "Willie: go to the kitchen" (':' or ',' after)
EMAIL_COMMAND_MAX_AGE_S=600.0          # mirrors VOICE_COMMAND_MAX_AGE_S: late motion is worse than none
EMAIL_AUTHSERV_ID='mx.google.com'      # only this receiver's Authentication-Results is trusted
# FR-2200 feature requests (built 2026-10-02, feature_requests.py). Evidence-grounded, composed
# by the cloud model, approved by DKIM-verified owner email, then one Markdown file committed.
ENABLE_FEATURE_REQUESTS=True
FEATURE_REQUEST_MAX_PER_DAY=1
FEATURE_REQUEST_MIN_EVENTS=5          # a category needs this many events in the window to count
FEATURE_REQUEST_WINDOW_DAYS=7
FEATURE_REQUEST_EXPIRE_DAYS=7         # unapproved requests are discarded after this
FEATURE_REQUEST_REPROPOSE_DAYS=30     # the same problem is not proposed again within this
FEATURE_REQUEST_FIRST_CHECK_S=600     # first look 10 min after start
FEATURE_REQUEST_CHECK_S=21600         # then every 6 h
FEATURE_REQUEST_PENDING_PATH='secrets/pending_feature_request.json'
FEATURE_REQUEST_HISTORY_PATH='secrets/feature_request_history.json'
FEATURE_REQUEST_PUSH_PENDING_PATH='secrets/feature_request_push_pending.json'
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
AUDIO_QUEUE_BLOCKS=50   # ~4 s of 80 ms blocks between the capture callback and the wake loop
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
# The RETRIEVE TASK itself (voice 'fetch the X'), separate from the camera backend flags around
# it. Off until FR-1700 is safe: the grasp drives the elbow to its forbidden centre and
# hand-off releases on a timer because nothing reads the gripper feedback yet (2026-10-02 FRD audit;
# the FSR402 was replaced by servo position feedback on ADS1115 A2 2026-10-04). The arm
# current limit IS enforced (brain._check_arm_current), but it only limits the damage. A misheard bare "Hey Willie" was classified as 'retrieve' on
# 2026-10-01 -- with this off, that is answered, not acted on.
ENABLE_RETRIEVAL_TASK=False
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
# 2026-10-07: by-id, NOT /dev/videoN. The rear camera was /dev/video8 when this was written and
# /dev/video0 on 2026-10-07 -- Linux renumbers video nodes across boots, and the rotation test
# opened the wrong node and got no frames. The by-id name follows the camera itself.
CAMERA_DEVICE='/dev/v4l/by-id/usb-Arducam_Technology_Co.__Ltd._Arducam_OV9281_USB_Camera_UC599-video-index0'
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

# --- FR-2100 person recognition. Built 2026-10-02: identity.py (store/matcher) + recognition.py
# (OpenCV YuNet detector + SFace 128-d embedding, CPU). recognition.py disables itself if the
# models in models/ are missing or the camera is unavailable. Faces only -- pets wait on the
# design's §10 spike.
ENABLE_FACE_RECOGNITION=True
FACE_DET_MODEL_PATH='models/face_detection_yunet_2023mar.onnx'
FACE_REC_MODEL_PATH='models/face_recognition_sface_2021dec.onnx'
FACE_DET_SCORE=0.8              # YuNet confidence for a face
FACE_SCAN_S=2.0                 # one frame every this long, IDLE only
FACE_ENROL_FRAMES=6; FACE_ENROL_S=2.0       # FR-2100-001: ~2 s of frames, one face each
FACE_ENROL_AUTHORISED=('Howard','Carolyn')  # FR-2100-006 soft gate (deterrent, not enforcement)
FACE_ENROL_SEEN_WINDOW_S=600
FACE_ENROL_CODE_TTL_S=86400     # the email approval code expires after a day
FACE_STRANGER_CONFIRM_N=3       # consecutive confidently-unknown scans before he asks
FACE_ASK_TIMEOUT_S=8.0          # how long he listens for a name after "who are you?"
FACE_SPEAKER_WINDOW_S=120       # FR-2100-004: last recognised face = "who am I talking to"
FACE_PENDING_ENROL_PATH='secrets/pending_enrolments.json'
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
# 2026-10-02: re-based for SFace, whose published same-person threshold is cosine SIMILARITY
# 0.363 (distance 0.637). Recognised needs clearly better than that; stranger needs clearly
# worse. Still starting points -- tune against real enrolments.
FACE_MATCH_MAX_DISTANCE=0.55
FACE_STRANGER_MIN_DISTANCE=0.78
# Cap per identity, oldest evicted. Rescued matches (FR-2100-003) add vectors over time, so
# without a cap an identity accumulates hundreds and matching slows for no accuracy gain.
FACE_MAX_VECTORS_PER_IDENTITY=12
# A person is greeted once per session; a session ends once they have been unseen this long.
# Long enough that walking in and out of the room does not re-trigger it, short enough that
# coming back after lunch feels like being noticed.
FACE_GREET_SESSION_S=1800
MEMORY_REPLAY_SIMILARITY_FLOOR=0.6  # FR-1900-003: below this, report mismatch rather than replay
# FR-1900-001/002 demonstrations (2026-10-02): "watch me, learn the way to the kitchen" follows
# the person (camera) or records while driven, sampling the pose every DEMO_POINT_SPACING_M.
# Replay similarity is positional: 1.0 within DEMO_START_NEAR_M of where the demonstration
# began, falling linearly to 0 at DEMO_START_FAR_M -- so with the 0.6 floor he refuses to
# replay a route from more than ~1.3 m away from its start.
DEMO_POINT_SPACING_M=0.30
DEMO_MIN_POINTS=3
DEMO_START_NEAR_M=0.5
DEMO_START_FAR_M=2.5
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
#   1. ~~MOTOR_PORT is unverified since 2026-09-04 — it replaced a bench-measured mapping with
#      an assumed one, so per-wheel stall attribution and odometry may name the wrong wheel.~~
#      CLOSED 2026-09-18 by M-1: each port driven alone by raw address, owner naming the wheel
#      that turned. LEFT AND RIGHT WERE TRANSPOSED; corrected above (0x61=left, 0x60=right).
#      This note went stale the day it was measured and was still saying "unverified" on
#      2026-09-27 — nine days. ⚠ It RE-OPENS when the 170 RPM motors are fitted: six motors
#      re-landed in one pass is exactly how the transposition happened. Re-run M-1 then.
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

    i2c_addrs={'INA260_5V_ADDR':INA260_5V_ADDR,
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

    # The GPIO duplicate check went with the sonar pins on 2026-09-30. Nothing in this
    # config names a raw Pi GPIO any more: the sonars answer through Pico B, the encoders
    # through Pico A, and the only Pi pins still in play are claimed by device-tree
    # overlays (uart2-pi5, uart3-pi5, uart4-pi5), which the kernel arbitrates, not us.
    # ⚠ If a raw Pi GPIO is ever reintroduced here, restore this check with it. The pins
    #   it used to guard -- GP4, GP5, GP13 -- are now TXD2, RXD2 and RXD4, and a constant
    #   naming one of those is a conflict the kernel will not warn about.

    # The MCP23017 pin-collision check is gone with the expander (2026-09-30). It used to
    # verify that twelve encoder bits and IMU_RST_MCP_PIN did not land on the same pin of
    # 0x27. There is no 0x27: encoder decode is Pico A's, and the BNO085 reset is Pico B
    # GP15. The equivalent risk now lives in firmware/pico_a.py's WHEELS tuple, which is
    # checked on hardware rather than here -- and WAS wrong until 2026-09-29, by a
    # left/right swap at every position.

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
    for corner,center in STEER_CENTER_US.items():
        if not (SERVO_MIN_US<center<SERVO_MAX_US):
            problems.append(f'STEER_CENTER_US[{corner!r}]={center} outside SERVO_MIN_US..SERVO_MAX_US')

    for name,speed in (('SPEED_ROAM',SPEED_ROAM),('SPEED_TURN',SPEED_TURN),('SPEED_SLOW',SPEED_SLOW)):
        if not (0<speed<=SPEED_MAX):
            problems.append(f'{name}={speed} must be in (0, SPEED_MAX={SPEED_MAX}]')
    if not (0<SPEED_MAX<=1.0):
        problems.append(f'SPEED_MAX={SPEED_MAX} must be in (0, 1.0]')

    if MAX_COMMAND_DURATION_S<=0:
        problems.append(f'MAX_COMMAND_DURATION_S={MAX_COMMAND_DURATION_S} must be positive')

    return problems
