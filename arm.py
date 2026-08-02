import board, busio, config
from adafruit_pca9685 import PCA9685

_i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)

class Arm:
    # PCA9685 @0x43, CH0-6, base->gripper order (§11.1). No per-joint safe limits, preset poses,
    # or IK exist yet — §20.6 bench calibration hasn't been run. This is a driver + primitive
    # set_pulse interface only, clamped to manufacturer defaults; arm_jog.py is the tool for
    # producing real calibration numbers. No autonomous motion is wired to this class anywhere.
    _JOINTS={'base':config.ARM_BASE,'shoulder_a':config.ARM_SHOULDER_A,'shoulder_b':config.ARM_SHOULDER_B,
             'elbow':config.ARM_ELBOW,'wrist_rot':config.ARM_WRIST_ROT,'wrist_pitch':config.ARM_WRIST_PITCH,
             'gripper':config.ARM_GRIPPER}
    _PERIOD_US=1_000_000/config.SERVO_PWM_FREQ
    def __init__(self):
        self._pca=PCA9685(_i2c,address=config.ARM_PCA_ADDR)
        self._pca.frequency=config.SERVO_PWM_FREQ
        self._pulse=dict.fromkeys(self._JOINTS,config.ARM_SERVO_CENTER_US)
    def _drive(self,joint,us):
        us=max(config.ARM_SERVO_MIN_US,min(config.ARM_SERVO_MAX_US,us))
        self._pca.channels[self._JOINTS[joint]].duty_cycle=int(us/self._PERIOD_US*65535)
        self._pulse[joint]=us
        return us
    def set_pulse(self,joint,us):
        # J1a/J1b (shoulder) are a mirrored pair driving one physical pitch axis (§11.1/§11.4) —
        # command shoulder_a only; shoulder_b is derived, not independently addressable.
        if joint=='shoulder_b':
            raise ValueError("shoulder_b is a mirrored slave of shoulder_a, not independently settable")
        actual=self._drive(joint,us)
        if joint=='shoulder_a':
            self._drive('shoulder_b',2*config.ARM_SERVO_CENTER_US-actual)
        return actual
    def pulse(self,joint): return self._pulse[joint]
    @property
    def joints(self): return [j for j in self._JOINTS if j!='shoulder_b']
    def center_all(self):
        for j in self.joints: self.set_pulse(j,config.ARM_SERVO_CENTER_US)
