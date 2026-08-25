#!/usr/bin/env python3
"""Per-wheel current test — drives one wheel at a time and reports what it draws.

WHY THIS EXISTS: on 2026-08-24 the left middle motor (0x60 M1) read zero current
at every duty in both directions while every healthy motor pulled ~0.11 A free-
running. That test was typed by hand into a terminal, so the measurement that
found the fault could not be repeated to confirm the repair. This is that test,
committed.

It answers one question per wheel: does commanding this port actually put
current through a motor? The motor rail INA260 at 0x44 is the witness --
baseline with everything stopped, then again mid-pulse. The delta is that
wheel's draw.

    delta ~0.11 A   -> healthy, motor is turning
    delta ~0.00 A   -> OPEN CIRCUIT. Nothing is connected to that port.
                       Check the connector, the crimp and the screw terminal
                       BEFORE suspecting the motor or the driver channel
                       (the 2026-08-24 fault was a disconnected connector).
    delta varies between attempts at the same duty
                    -> commutator dead spot, i.e. the motor itself

A stall reads HIGHER than healthy, not lower -- a motor that hums without
turning is still drawing. Zero means the circuit is open, full stop.

RUN THE ROVER ON A BLOCK, WHEELS FREE. This drives real motors.
Stop the service first -- it drives the same ports and shares the bus:

    sudo systemctl stop willy-rover
    python3 scripts/wheel_current_test.py
    sudo systemctl start willy-rover
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_RAIL=0x44          # motor 12V bus. NOT 0x45 (Pi 9V feed) -- those two were
                    # transposed in the docs until 2026-08-24.
_BUS=1
_DUTY=0.60          # above the ~0.5 breakaway measured on this chassis, below
                    # a speed that walks the rover off its block.
_PULSE_S=0.8
_SETTLE_S=0.4       # let the rail settle after a stop before the next baseline
_OPEN_A=0.04        # below this, treat the port as an open circuit

def _read_amps(bus,addr):
    """Amps from one INA260. Raises OSError if the device NAKs."""
    d=bus.read_i2c_block_data(addr,0x01,2); raw=(d[0]<<8)|d[1]   # 1.25mA/LSB, signed
    if raw>32767: raw-=65536
    return raw*1.25/1000.0

def _mean_amps(bus,n=6,period=0.05):
    """Averaged, because a PWM'd motor rail is noisy sample to sample."""
    vals=[]
    for _ in range(n):
        try: vals.append(_read_amps(bus,_RAIL))
        except OSError: pass
        time.sleep(period)
    return sum(vals)/len(vals) if vals else float('nan')

def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this test needs the real bus.',file=sys.stderr)
        return 1
    try:
        from smbus2 import SMBus
    except ImportError:
        print('smbus2 not installed in this interpreter',file=sys.stderr); return 1
    import board,busio
    from adafruit_motorkit import MotorKit

    wheels=sys.argv[1:] or list(config.MOTOR_PORT)
    bad=[w for w in wheels if w not in config.MOTOR_PORT]
    if bad:
        print(f'unknown wheel(s): {" ".join(bad)}',file=sys.stderr)
        print(f'valid: {" ".join(config.MOTOR_PORT)}',file=sys.stderr); return 1

    i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)
    kits={a:MotorKit(i2c=i2c,address=a) for a in (config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR)}
    motors={w:getattr(kits[a],f'motor{p}') for w,(a,p) in config.MOTOR_PORT.items()}

    print(f'rail 0x{_RAIL:02x}  duty {_DUTY}  pulse {_PULSE_S}s  open-circuit threshold {_OPEN_A} A')
    print(f'{"wheel":6} {"port":10} {"fwd A":>8} {"rev A":>8}  verdict')
    results={}
    with SMBus(_BUS) as bus:
        for w in wheels:
            addr,port=config.MOTOR_PORT[w]
            draws=[]
            for duty in (_DUTY,-_DUTY):
                for m in motors.values(): m.throttle=None   # coast, so nothing else loads the rail
                time.sleep(_SETTLE_S)
                base=_mean_amps(bus)
                motors[w].throttle=duty
                time.sleep(0.25)                            # spin-up; inrush is not what we want
                driven=_mean_amps(bus)
                motors[w].throttle=None
                draws.append(driven-base)
            fwd,rev=draws
            worst=min(abs(fwd),abs(rev))
            verdict='OPEN CIRCUIT -- check connector/crimp/terminal' if worst<_OPEN_A else 'ok'
            results[w]=(fwd,rev,verdict)
            print(f'{w:6} 0x{addr:02x} M{port:<5} {fwd:8.3f} {rev:8.3f}  {verdict}')
    for m in motors.values(): m.throttle=None
    return 1 if any(v[2]!='ok' for v in results.values()) else 0

if __name__=='__main__':
    sys.exit(main() or 0)
