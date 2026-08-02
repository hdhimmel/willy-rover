# WildWilly Rover — Central Configuration v2
# 180x125mm chassis · 5" 800x480 landscape display

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

# Steering — PCA9685 @0x42, CH0-5 (§3.1/§10). Servo mode (500-2500/1000-2000/900-2100us) is
# unconfirmed per-unit — default to the narrowest documented range so a narrow-mode servo can't
# be driven into a mechanical bind. Widen only after a bench check confirms a unit's real range.
# Steering kinematics (wheel-angle coordination, crab/point-turn) are undesigned in the master
# doc (§10: "pending in software") — this pass only centers all six and holds them there.
STEER_PCA_ADDR=0x42
STEER_LF=0; STEER_RF=1; STEER_LM=2; STEER_RM=3; STEER_LR=4; STEER_RR=5
SERVO_CENTER_US=1500; SERVO_MIN_US=1000; SERVO_MAX_US=2000
SERVO_PWM_FREQ=50

# Arm — PCA9685 @0x43, CH0-6, base->gripper order (§11.1). J1a/J1b (shoulder) are a mirrored
# pair driving one physical axis — see arm.py. Wider nominal range than steering (manufacturer
# spec 500-2500us) though §11.5/§20.6 flag cheap-clone units may bind before the full sweep.
# No per-joint safe limits, presets, or IK exist yet pending §20.6 bench calibration — arm.py is
# a driver + manual jog tool only this pass, not autonomous motion.
ARM_PCA_ADDR=0x43
ARM_BASE=0; ARM_SHOULDER_A=1; ARM_SHOULDER_B=2; ARM_ELBOW=3
ARM_WRIST_ROT=4; ARM_WRIST_PITCH=5; ARM_GRIPPER=6
ARM_SERVO_MIN_US=500; ARM_SERVO_MAX_US=2500; ARM_SERVO_CENTER_US=1500

# Wheel encoders — MCP23017 @0x27 (§9.1), quadrature A/B per wheel. No interrupt line runs to
# the Pi (only the IMU has one) — Encoders (sensors.py) polls GPIOA/GPIOB best-effort, may miss
# edges at speed. counts/rev is a "starting value" from the motor listing, not bench-confirmed.
ENCODER_ADDR=0x27
ENCODER_PINS={'lf':('A',0,1),'lm':('A',2,3),'lr':('B',0,1),
              'rf':('A',4,5),'rm':('A',6,7),'rr':('B',2,3)}
ENCODER_COUNTS_PER_REV=3292  # §9.2: 823.1 PPR x4 quadrature decode

# Current monitoring — INA260 x3 (§5.2). Monitor/log only (FR-1100 diagnostics) — no numeric
# overcurrent trip thresholds exist anywhere in the documentation to hardcode a cutoff against.
INA260_SERVO_ADDR=0x40; INA260_PI_ADDR=0x44; INA260_MOTOR_ADDR=0x45

ADS_ADDR=0x48; ADS_CH_BATTERY=0  # AIN0 only; charge-sense divider not yet wired
# Re-trimmed for the ADS1115 2026-08-02: AIN0 read 3.2749V while a multimeter
# on the pack terminals read 11.43V (3.2749/11.43). Old MCP3008-era value was
# 0.2481 — different chip loads the divider less, so this had to be redone.
BATTERY_DIVIDER_SCALE=0.2865

# Battery threshold ladder (§13.2) — one-way toward safer states until voltage recovers above
# the next threshold up + hysteresis. Supersedes the old flat BAT_LOW/BAT_CRITICAL pair.
BAT_FULL_V=11.39      # display-only 100% anchor for battery_pct
BAT_WARN_V=11.4       # -> warn
BAT_RTH_V=10.8        # -> return-to-home / DOCK
BAT_SAFE_V=10.5        # -> SAFE_MODE (motion stop, arm holds)
BAT_SHUTDOWN_V=10.2   # -> controlled shutdown; also the 0% anchor for battery_pct
BAT_HYSTERESIS_V=0.2

CLAUDE_MODEL='claude-sonnet-4-20250514'
CLAUDE_MAX_TOKENS=300; CLAUDE_ESCALATE_AFTER=5
STUCK_TIMEOUT=3.0; BACK_UP_TIME=0.8; TURN_TIME_90=1.2; IDLE_TIMEOUT=30.0
