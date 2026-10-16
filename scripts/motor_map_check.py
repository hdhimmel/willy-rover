#!/usr/bin/env python3
"""Motor port + encoder map check over Pico A (bench procedure M-1, 2026-10-16).

Replaces scripts/encoder_map_check.py, which read the MCP23017 expander -- removed from the
bus with the Pico cutover (Master Hardware Design §4.7). Encoders are now counted by Pico A
and read over uart4-pi5 (sensors.Encoders, signed x2 since firmware a-0.3).

For each wheel in turn: drive that MOTOR_PORT alone in ROVER-forward terms (MOTOR_SIGN
applied, as motors.py does) for PULSE_S, then report every wheel's count change. A correct
row moves ONLY its own wheel's encoder, and by a POSITIVE amount (forward = +). Watch the
wheels too: the script can tell which encoder moved, only your eyes can tell which wheel did.

RUN ON BLOCKS, WHEELS FREE. Stop the service first (it owns the ports and Pico A's UART):

    sudo systemctl stop willy-rover
    python3 scripts/motor_map_check.py            # all six, or name wheels: lf rr
    sudo systemctl start willy-rover
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

DUTY=0.60           # above the ~0.5 breakaway on this chassis
PULSE_S=1.0
SETTLE_S=0.6        # let the wheel stop and the counts settle before reading
MIN_COUNTS=50       # below this a wheel did not really turn (1 s at 0.6 duty is ~1000+)

def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this test needs the real hardware.',file=sys.stderr); return 1
    wheels=sys.argv[1:] or list(config.MOTOR_PORT)
    bad=[w for w in wheels if w not in config.MOTOR_PORT]
    if bad:
        print(f'unknown wheel(s): {" ".join(bad)}; valid: {" ".join(config.MOTOR_PORT)}',file=sys.stderr); return 1
    import board,busio
    from adafruit_motorkit import MotorKit
    from sensors import Encoders
    i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
    kits={a:MotorKit(i2c=i2c,address=a) for a in (config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR)}
    motors={w:getattr(kits[a],f'motor{p}') for w,(a,p) in config.MOTOR_PORT.items()}
    enc=Encoders(); enc.start(); time.sleep(1.0)
    if not enc.is_healthy:
        print('Pico A is not reporting encoder counts -- check the link (sensors.Encoders).',file=sys.stderr)
        enc.stop(); return 1
    order=list(config.MOTOR_PORT)
    print(f'duty {DUTY}, {PULSE_S}s pulse, rover-forward (MOTOR_SIGN applied). Count change per encoder:')
    print(f'{"driven":7}{"port":13}'+''.join(f'{w:>8}' for w in order)+'   verdict')
    fails=0
    try:
        for w in wheels:
            before=dict(enc.counts)
            m=motors[w]; m.throttle=DUTY*config.MOTOR_SIGN[w]
            time.sleep(PULSE_S); m.throttle=0; time.sleep(SETTLE_S)
            after=dict(enc.counts); d={k:after[k]-before[k] for k in order}
            moved=[k for k in order if abs(d[k])>=MIN_COUNTS]
            if moved==[w] and d[w]>0: verdict='OK'
            elif moved==[w]: verdict='OWN ENCODER, BACKWARDS (MOTOR_SIGN or encoder A/B)'
            elif not moved: verdict='NOTHING MOVED (wiring/port/power -- check wires first)'
            else: verdict=f'WRONG/EXTRA ENCODER(S): {" ".join(moved)} (MOTOR_PORT or J3 wiring)'
            fails+=verdict!='OK'
            a,p=config.MOTOR_PORT[w]
            print(f'{w:7}{f"0x{a:02x} M{p}":13}'+''.join(f'{d[k]:>8}' for k in order)+f'   {verdict}')
    finally:
        for m in motors.values(): m.throttle=0
        enc.stop()
    print(f'\n{len(wheels)-fails}/{len(wheels)} OK. Also confirm by eye that each driven wheel was the one named and rolled FORWARD.')
    return 1 if fails else 0

if __name__=='__main__':
    sys.exit(main())
