#!/usr/bin/env python3
import sys,os,signal
sys.path.insert(0,os.path.dirname(__file__))

# FR-100 (startup): detect a fully offline I2C bus (e.g. the Pi physically disconnected from the
# rover harness mid-hardware-work) BEFORE constructing any hardware object. brain.py's own
# RoverBrain.__init__() calls DriveBase()/IMU()/Encoders()/etc. unconditionally, and each one's
# constructor raises immediately if its specific chip doesn't ack (e.g. MotorKit's
# ValueError('No I2C device at address: 0x60')) -- crashing the whole process before
# RoverBrain._self_test()'s existing "report a reason, don't crash" gate ever gets a chance to
# run. Found 2026-08-19: this crash-loops willy-rover.service (systemd's Restart=on-failure)
# indefinitely with no operator-visible signal beyond the journal, every RestartSec, until
# someone notices and reconnects the hardware.
#
# Forcing WILLY_SIMULATE=1 for this run instead reuses the already-tested hw_sim no-op hardware
# path (motors.py/arm.py/sensors.py's own SIMULATE_HARDWARE branches) rather than inventing a new
# degraded-mode code path — every I2C-dependent subsystem becomes a safe stand-in, while
# voice/vision/email/cloud-AI/display/world_model (none of which gate on SIMULATE_HARDWARE) are
# unaffected. This is a one-time check at process startup, not a background poller: restart the
# service once hardware is reconnected to re-check (matches how config.SIMULATE_HARDWARE is read
# once at each module's import time everywhere else in this codebase, not polled).
if not os.environ.get('WILLY_SIMULATE'):
    import smbus2
    import config
    def _i2c_bus_online():
        addrs=(config.ENCODER_ADDR,config.IMU_ADDR,config.ADS_ADDR,config.STEER_PCA_ADDR,
               config.ARM_PCA_ADDR,config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR,
               config.INA260_SERVO_ADDR,config.INA260_PI_ADDR,config.INA260_MOTOR_ADDR)
        try:
            with smbus2.SMBus(1) as bus:
                for addr in addrs:
                    try:
                        bus.read_byte(addr); return True
                    except OSError:
                        continue
        except (FileNotFoundError,OSError):
            pass  # no /dev/i2c-1 at all -- also offline
        return False
    # Found 2026-08-21: a single pass through every address can transiently miss all of them at
    # once during a brief startup-inrush moment even when the bus is genuinely healthy (this same
    # session root-caused a real under-voltage issue separately -- fixed, but some residual
    # transient sensitivity remains). A single unlucky check shouldn't be enough to declare the
    # bus offline and silently degrade a fully-working rover -- retry a few times with a short
    # gap first.
    import time
    _bus_online=False
    for _attempt in range(3):
        if _i2c_bus_online(): _bus_online=True; break
        time.sleep(0.3)
    if not _bus_online:
        print('I2C bus offline at startup (no expected device acked on bus 1) -- forcing '
              'WILLY_SIMULATE=1 for this run so the service comes up in a safe no-op state '
              'instead of crash-looping. Restart willy-rover.service once hardware is '
              'reconnected to re-check.',file=sys.stderr)
        os.environ['WILLY_SIMULATE']='1'; os.environ['WILLY_I2C_FORCED_SIMULATE']='1'
        # Setting the env var alone is not enough: config.py already ran its module-level
        # `SIMULATE_HARDWARE=os.environ.get('WILLY_SIMULATE','0')=='1'` assignment at the
        # `import config` above, and Python caches that result in sys.modules -- every later
        # `import config` elsewhere (motors.py, sensors.py, arm.py, brain.py itself) returns the
        # same cached module object without re-running it, so it would otherwise keep seeing the
        # stale False from before this branch ran. Patch the already-imported module directly.
        config.SIMULATE_HARDWARE=True

from brain import RoverBrain
if __name__=='__main__':
    # systemd sends SIGTERM on stop/restart; route it through the same KeyboardInterrupt path
    # run() already handles for SIGINT so shutdown (and RoverBrain.stop()'s cleanup) actually runs.
    signal.signal(signal.SIGTERM,signal.default_int_handler)
    RoverBrain().run()
