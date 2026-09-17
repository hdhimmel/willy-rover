import config
import hw_sim
if not config.SIMULATE_HARDWARE:
    import board, busio
    from adafruit_pca9685 import PCA9685
    _i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)

# FR-700-002 (preset positions): NOT implemented -- no named poses exist, per this
# class's own comment below (no per-joint safe limits, preset poses, or IK yet).
# FR-700-003 (joint limits) -- PARTIAL: _drive() below clamps to manufacturer-default
# ARM_SERVO_MIN_US/MAX_US, but real per-joint calibrated limits haven't been bench-set.
# FR-700-004 (arm stops on E-stop) -- PARTIAL: safety.SafetyController still only holds a
# drive_base reference (see safety.py's __init__), never an Arm instance, and
# emergency_stop() only calls self._drive.brake() -- there is no explicit "freeze the arm"
# call anywhere. What was a bigger problem until this fixed (2026-08-18): retrieval_task.py's
# _grasp() used to run its whole pulse sequence through blocking time.sleep() calls inside a
# single tick, so a tilt/battery/sensor-fault abort() had no way to even run until the arm had
# already finished moving. _grasp() is now a non-blocking, tick-serviced step sequence, so
# brain.py's Directive 1-4 abort() calls can land between any two arm-motion steps -- the arm
# still has no independent brake distinct from "stop commanding new pulses" (a PWM servo simply
# holds its last position, unlike a spinning drive motor, so this is a smaller residual gap than
# it looks), but the previous total blackout window is closed. brain.py's own wave-hello gesture
# was the other known blocking culprit (~1.5s via time.sleep()) -- also converted to a
# non-blocking, tick-serviced step machine (_start_wave()/_wave()) the same day, once it became
# clear the "IDLE-only, low risk" reasoning for leaving it alone assumed no systemd watchdog was
# configured, which turned out to be wrong (WatchdogSec=500ms is real -- see FRD v3.1 G-5).
class Arm:
    # PCA9685 @0x43, CH1-7 (CH0 unused, shifted 2026-08-21), base->gripper order (§11.1). No
    # per-joint safe limits, preset poses,
    # or IK exist yet — §20.6 bench calibration hasn't been run. This is a driver + primitive
    # set_pulse interface only, clamped to manufacturer defaults; arm_jog.py is the tool for
    # producing real calibration numbers. No autonomous motion is wired to this class anywhere.
    # Channel numbers corrected against hardware 2026-09-17 -- see the map in config.py. The old
    # names shoulder_a/shoulder_b implied a mirrored pair; CH2 and CH3 are not one.
    _JOINTS={'base':config.ARM_BASE,'shoulder':config.ARM_SHOULDER,'shoulder_b':config.ARM_SHOULDER_B,
             'elbow':config.ARM_ELBOW,'wrist_rot':config.ARM_WRIST_ROT,'wrist_pitch':config.ARM_WRIST_PITCH,
             'gripper':config.ARM_GRIPPER}
    _PERIOD_US=1_000_000/config.SERVO_PWM_FREQ
    def __init__(self):
        self._pca=hw_sim.SimServoBank() if config.SIMULATE_HARDWARE else PCA9685(_i2c,address=config.ARM_PCA_ADDR)
        self._pca.frequency=config.SERVO_PWM_FREQ
        self._pulse=dict.fromkeys(self._JOINTS,config.ARM_SERVO_CENTER_US)
    def _drive(self,joint,us):
        us=max(config.ARM_SERVO_MIN_US,min(config.ARM_SERVO_MAX_US,us))
        self._pca.channels[self._JOINTS[joint]].duty_cycle=int(us/self._PERIOD_US*65535)
        self._pulse[joint]=us
        return us
    # FR-700-001 (control all arm joints): each joint on its own channel.
    #
    # THE MIRRORED-PAIR DERIVATION WAS REMOVED 2026-09-17. This used to drive
    # shoulder_b = 2*center - shoulder_a, per the FRD's J1a/J1b spec. Hardware says CH2 and CH3
    # are not a mirrored pair: commanding them mirrored and commanding them the same drew
    # statistically identical current (0.197A vs 0.176A avg), where a genuine shared axis driven
    # the wrong way would fight hard. Keeping the derivation was actively harmful -- with the
    # shoulder at its verified 750us waving position it would have driven CH3 to 2250us.
    # CH3's actual function is still unidentified; it is addressable but nothing here uses it.
    def set_pulse(self,joint,us):
        return self._drive(joint,us)
    def pulse(self,joint): return self._pulse[joint]
    @property
    def joints(self): return list(self._JOINTS)
    # THE ELBOW IS EXCLUDED, DELIBERATELY. ARM_SERVO_CENTER_US drives CH1 into the top of Willy:
    # the servo fitted before 2026-09-17 held ~8A at 1500us indefinitely and was destroyed by it.
    # Centring every joint on startup would repeat that on every boot. The elbow has no known
    # safe centre until §20.6 calibration establishes one, so it is left where it is.
    def center_all(self):
        for j in self.joints:
            if j=='elbow': continue
            self.set_pulse(j,config.ARM_SERVO_CENTER_US)
