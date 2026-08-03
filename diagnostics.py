#!/usr/bin/env python3
# FR-1100-004: diagnostic test mode. Read-only — never imports motors/steering/arm, so it's
# safe to run any time (including mid-assembly) without risk of the rover moving. Mirrors the
# INIT self-test in brain.py but reports a full itemized table instead of a pass/fail reason
# string, and can be run standalone without starting the tick loop.
import sys,time,board,busio,config,logsetup
from sensors import SonarArray,IMU,ADC,Encoders,CurrentMonitor

log=logsetup.setup('diagnostics')

_EXPECTED_I2C={config.ENCODER_ADDR,config.INA260_SERVO_ADDR,config.STEER_PCA_ADDR,config.ARM_PCA_ADDR,
               config.INA260_PI_ADDR,config.INA260_MOTOR_ADDR,config.ADS_ADDR,config.IMU_ADDR,
               config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR,0x70}

def scan_i2c():
    i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
    while not i2c.try_lock(): pass
    found=set(i2c.scan()); i2c.unlock()
    return found

def main():
    print('WildWilly diagnostic test mode - read-only, no actuation.\n')
    found=scan_i2c()
    missing=_EXPECTED_I2C-found
    print(f'I2C devices found:  {", ".join(hex(a) for a in sorted(found))}')
    if missing: print(f'I2C devices MISSING: {", ".join(hex(a) for a in sorted(missing))}')
    else: print('I2C: all expected addresses present.')

    sonars=SonarArray(); imu=IMU(); adc=ADC(); encoders=Encoders(); current=CurrentMonitor()
    sonars.start(); imu.start(); adc.start(); encoders.start(); current.start()
    time.sleep(1.0)  # let threads take a first reading (current monitor is slowest, 10Hz)

    print(f'\nSonar    front={sonars.front.distance}cm left={sonars.left.distance}cm right={sonars.right.distance}cm')
    print(f'IMU      healthy={imu.is_healthy}  tilt={imu.tilt:.1f}deg  pitch={imu.pitch:.1f}  roll={imu.roll:.1f}')
    adc_healthy=adc.battery_volts>0
    print(f'Battery  healthy={adc_healthy}  volts={adc.battery_volts:.2f}V  pct={adc.battery_pct}%  charging={adc.is_charging}')
    print(f'Encoders healthy={encoders.is_healthy}  counts={encoders.counts}')
    print('Current rails:')
    for rail,vals in current.all_rails.items():
        print(f'  {rail:6s} {vals["current_a"]:.2f}A  {vals["voltage_v"]:.2f}V  {vals["power_w"]:.2f}W')
    print(f'  (current monitor healthy={current.is_healthy})')

    sonars.stop(); imu.stop(); adc.stop(); encoders.stop(); current.stop()

    ok=not missing and imu.is_healthy and adc_healthy and encoders.is_healthy and current.is_healthy
    print(f'\nOverall: {"PASS" if ok else "FAIL"}')
    log.info('Diagnostic test mode run - overall '+('PASS' if ok else 'FAIL')
              +(f'; I2C missing: {sorted(hex(a) for a in missing)}' if missing else ''))
    return 0 if ok else 1

if __name__=='__main__':
    sys.exit(main())
