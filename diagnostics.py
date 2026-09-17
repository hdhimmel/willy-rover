#!/usr/bin/env python3
# FR-1100-004: diagnostic test mode. Read-only — never imports motors/steering/arm, so it's
# safe to run any time (including mid-assembly) without risk of the rover moving. Mirrors the
# INIT self-test in brain.py but reports a full itemized table instead of a pass/fail reason
# string, and can be run standalone without starting the tick loop.
import sys,time,board,busio,config,logsetup
from sensors import SonarArray,IMU,ADC,Encoders,CurrentMonitor

log=logsetup.setup('diagnostics')

# I2C addresses expected present per §5.2's authoritative map. Deliberately excludes 0x70 (PCA9685
# all-call broadcast) — PCA9685.reset() clears MODE1's ALLCALL bit during motors.py/arm.py's
# construction in RoverBrain.__init__, which runs before this self-test, so 0x70 legitimately
# never answers by the time we scan; it was never a real device to begin with. See brain.py.
_EXPECTED_I2C={config.ENCODER_ADDR,config.INA260_5V_ADDR,config.STEER_PCA_ADDR,config.ARM_PCA_ADDR,
               config.INA260_BUS_12V_ADDR,config.INA260_ARM_6V_ADDR,config.ADS_ADDR,config.IMU_ADDR,
               config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR}
# Witty Pi 5 joins only when enabled, mirroring brain.py:71 exactly. THIS LINE WAS MISSING until
# 2026-09-14: brain.py's self-test expected eleven devices while this expected ten, so
# `python3 diagnostics.py` reported a clean bus on a rover whose Witty Pi had dropped off it.
# The failure direction was the bad one -- a read-only report that cannot see an absent device.
# tests/test_expected_i2c_agreement.py now compares the two sets so they cannot drift again.
if config.ENABLE_WITTY_PI: _EXPECTED_I2C.add(config.WITTY_PI_ADDR)

def scan_i2c():
    i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
    while not i2c.try_lock(): pass
    found=set(i2c.scan()); i2c.unlock()
    return found

def main():
    print('WildWilly diagnostic test mode - read-only, no actuation.\n')
    config_problems=config.validate()
    if config_problems:
        print(f'Config validation: {len(config_problems)} problem(s):')
        for p in config_problems: print(f'  - {p}')
    else:
        print('Config validation: clean.')
    found=scan_i2c()
    missing=_EXPECTED_I2C-found
    print(f'I2C devices found:  {", ".join(hex(a) for a in sorted(found))}')
    if missing: print(f'I2C devices MISSING: {", ".join(hex(a) for a in sorted(missing))}')
    else: print('I2C: all expected addresses present.')

    sonars=SonarArray(); imu=IMU(); adc=ADC(); encoders=Encoders(); current=CurrentMonitor()
    sonars.start(); imu.start(); adc.start(); encoders.start(); current.start()
    time.sleep(1.0)  # let threads take a first reading (current monitor is slowest, 10Hz)

    # CAPTURE EVERY HEALTH FLAG BEFORE ANYTHING IS STOPPED, and build the verdict from these
    # locals -- never by re-reading .is_healthy further down.
    #
    # Fixed 2026-09-16. `is_healthy` is a STALENESS flag: (perf_counter() - last_ok) < window,
    # where the window is 0.5s for the IMU and 1.0s for encoders and the current monitor, kept
    # fresh by each sensor's own thread. The verdict used to be computed AFTER the stop() line
    # below -- by which point nothing has updated anything for the whole shutdown, measured at
    # 1.147s on the rover against the IMU's 0.5s window. So `ok` read imu.is_healthy as False
    # every single time and diagnostics.py COULD NEVER PRINT PASS, on any hardware, in any
    # state -- while printing 'IMU healthy=True' four lines earlier from the same property.
    # It also returns exit 1, so anything gating on this tool saw a permanent failure.
    # Same family as the 2026-09-14 ten-versus-eleven-device bug: the tool was wrong, not the
    # rover. A diagnostic that cries wolf is worse than none, because the next real fault is
    # the one nobody believes.
    imu_healthy=imu.is_healthy
    adc_healthy=adc.battery_volts>0
    encoders_healthy=encoders.is_healthy
    current_healthy=current.is_healthy

    print(f'\nSonar    front={sonars.front.distance}cm left={sonars.left.distance}cm right={sonars.right.distance}cm')
    print(f'IMU      healthy={imu_healthy}  tilt={imu.tilt:.1f}deg  pitch={imu.pitch:.1f}  roll={imu.roll:.1f}')
    print(f'Battery  healthy={adc_healthy}  volts={adc.battery_volts:.2f}V  pct={adc.battery_pct}%  charging={adc.is_charging}')
    print(f'Encoders healthy={encoders_healthy}  counts={encoders.counts}')
    print('Current rails:')
    for rail,vals in current.all_rails.items():
        print(f'  {rail:9s} {vals["current_a"]:.2f}A  {vals["voltage_v"]:.2f}V  {vals["power_w"]:.2f}W')
    print(f'  (current monitor healthy={current_healthy})')

    sonars.stop(); imu.stop(); adc.stop(); encoders.stop(); current.stop()

    ok=(not missing and not config_problems and imu_healthy and adc_healthy
        and encoders_healthy and current_healthy)
    print(f'\nOverall: {"PASS" if ok else "FAIL"}')
    log.info('Diagnostic test mode run - overall '+('PASS' if ok else 'FAIL')
              +(f'; I2C missing: {sorted(hex(a) for a in missing)}' if missing else '')
              +(f'; config problems: {len(config_problems)}' if config_problems else ''))
    return 0 if ok else 1

if __name__=='__main__':
    sys.exit(main())
