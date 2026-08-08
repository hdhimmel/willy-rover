# §19 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: minimal in-memory stand-ins used by
# motors.py/sensors.py/arm.py when config.SIMULATE_HARDWARE is set. Each mock only implements the
# handful of attributes its real counterpart's caller actually touches (e.g. `.throttle=`,
# `.channels[n].duty_cycle=`) — not a faithful protocol-level simulation of the real I2C device,
# just enough surface area that the *calling* code (DriveBase/Steering/Arm/IMU/ADC/Encoders/
# SonarArray) runs unmodified and produces plausible, safe values.

class SimMotor:
    """Stand-in for one adafruit_motor DCMotor — DriveBase's ramp loop only ever reads/writes
    .throttle, so that's all this needs."""
    __slots__=('throttle',)
    def __init__(self): self.throttle=0.0

class _SimPWMChannel:
    __slots__=('duty_cycle',)
    def __init__(self): self.duty_cycle=0

class SimServoBank:
    """Stand-in for a PCA9685 — Steering/Arm only use .frequency= and .channels[n].duty_cycle=."""
    def __init__(self,n_channels=16):
        self.frequency=50
        self.channels=[_SimPWMChannel() for _ in range(n_channels)]
