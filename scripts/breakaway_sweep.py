#!/usr/bin/env python3
"""Breakaway sweep -- the lowest duty at which each wheel starts turning from rest.

WHY THIS EXISTS: SPEED_SLOW=0.55 was set on 2026-08-24 from breakaway measured on the old
620 RPM gearbox. The fitted motors are 170 RPM / 35.5:1 with far more torque, so that floor
is probably much higher than it needs to be. The sweeps that found the bad lf and lm motors
on 2026-09-30 were typed into a terminal; this is that test, committed, so the number that
sets SPEED_SLOW can be repeated.

Each step starts from REST: every wheel coasts and the rail settles before the pulse, so a
wheel that is already spinning cannot carry momentum into the next duty. The sweep runs to
the top duty either way, so the table also gives each wheel's speed and draw when properly
spinning -- late breakaway AND slow-and-hungry at the top is a dragging wheel. A wheel has
broken away when Pico A's Phase A count rate clears _MOVING_CPS. Current comes from the +12V motor
bus INA260 as a delta over the stopped baseline, the same method as wheel_current_test.py,
so a high-current/low-speed wheel (the dragging-motor signature) stands out in the table.

WHEELS FREE, ROVER ON A BLOCK. Free wheels break away lower than wheels carrying the
rover's weight on carpet, so treat the result as a floor: SPEED_SLOW needs margin above
the worst wheel, not equality with it.

    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/breakaway_sweep.py            # all six
    venv/bin/python3 scripts/breakaway_sweep.py lm rm      # just these
    sudo systemctl start willy-rover
"""
import os,sys,time
_HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.dirname(_HERE)); sys.path.insert(0,_HERE)
import config
from encoder_calibration import PicoEncoders,_delta
from wheel_current_test import _mean_amps,_RAIL,_BUS,_SETTLE_S

_DUTIES=[round(0.10+0.05*i,2) for i in range(11)]     # 0.10 .. 0.60
_SPINUP_S=0.4        # let it get going; breakaway is about whether it moves, not inrush
_WINDOW_S=1.0        # count rate measured over this window
_MOVING_CPS=20       # below this, line noise or a twitch, not rotation
_MARGIN=0.10         # suggested SPEED_SLOW = worst breakaway + this


def _rpm(cps):
    return cps*60.0/config.ENCODER_COUNTS_PER_REV     # measured 2026-10-01


def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this needs the real motors.',file=sys.stderr)
        return 1
    wheels=sys.argv[1:] or list(config.MOTOR_PORT)
    bad=[w for w in wheels if w not in config.MOTOR_PORT]
    if bad:
        print(f'unknown wheel(s): {" ".join(bad)}  valid: {" ".join(config.MOTOR_PORT)}',
              file=sys.stderr)
        return 1
    from smbus2 import SMBus
    import board,busio
    from adafruit_motorkit import MotorKit

    enc=PicoEncoders(); enc.start(); time.sleep(1.0)
    if enc.counts is None:
        print('No $E frames from Pico A -- see encoder_calibration.py for the checks.',
              file=sys.stderr)
        enc.stop(); return 1

    i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
    kits={a:MotorKit(i2c=i2c,address=a) for a in (config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR)}
    motors={w:getattr(kits[a],f'motor{p}') for w,(a,p) in config.MOTOR_PORT.items()}
    def coast():
        for m in motors.values(): m.throttle=None

    print(f'rail 0x{_RAIL:02x}  moving > {_MOVING_CPS} counts/s  RPM at '
          f'{config.ENCODER_COUNTS_PER_REV} counts/rev (measured, Phase A only)\n')
    breakaway={}; top={}
    try:
        with SMBus(_BUS) as bus:
            for w in wheels:
                print(f'{w}:  ',end='',flush=True)
                breakaway[w]=None
                for duty in _DUTIES:
                    coast(); time.sleep(_SETTLE_S)
                    base=_mean_amps(bus)
                    motors[w].throttle=duty; time.sleep(_SPINUP_S)
                    c0=enc.counts[w]; t0=time.monotonic()
                    amps=_mean_amps(bus)
                    time.sleep(max(0.0,_WINDOW_S-(time.monotonic()-t0)))
                    cps=_delta(enc.counts[w],c0)/(time.monotonic()-t0)
                    coast()
                    print(f'{duty:.2f}={cps:.0f}c/s ',end='',flush=True)
                    if cps>_MOVING_CPS and breakaway[w] is None:
                        breakaway[w]=(duty,cps,amps-base)
                    top[w]=(cps,amps-base)
                print()
    finally:
        coast(); enc.stop()

    print(f'\n{"wheel":6} {"breakaway":>9} {"c/s":>6} {"RPM":>6} {"A":>7}   '
          f'{"RPM@"+format(_DUTIES[-1],".2f"):>8} {"A":>7}')
    for w,r in breakaway.items():
        if r is None:
            print(f'{w:6} {"NONE":>9}  -- never moved up to {_DUTIES[-1]:.2f}; check wiring '
                  f'before the motor')
        else:
            d,cps,a=r
            tc,ta=top[w]
            print(f'{w:6} {d:9.2f} {cps:6.0f} {_rpm(cps):6.1f} {a:7.3f}   '
                  f'{_rpm(tc):8.1f} {ta:7.3f}')
    moved=[r[0] for r in breakaway.values() if r]
    if moved and len(moved)==len(breakaway):
        worst=max(moved)
        print(f'\nworst wheel breaks away at {worst:.2f}.  SPEED_SLOW is {config.SPEED_SLOW}; '
              f'worst + {_MARGIN} margin = {worst+_MARGIN:.2f}')
    return 0 if all(breakaway.values()) else 1

if __name__=='__main__':
    sys.exit(main() or 0)
