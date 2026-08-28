#!/usr/bin/env python3
"""Per-servo current test for the STEERING servos -- catches an unplugged connector.

WHY THIS EXISTS: three connector faults turned up in one week (arm servo connectors found
unplugged, left middle motor disconnected, left rear motor open after a teardown). The motor
half of that is now checkable in 40 seconds by scripts/wheel_current_test.py. This is the same
technique for the steering servos: command one corner to move, watch its rail, and a connector
that is not making contact draws nothing while a healthy one clearly does.

SCOPE -- READ THIS BEFORE EXPECTING IT TO COVER THE ARM. It does not, and cannot:

    R2  5V  DROK buck     steering servos + sonar VCC + Pi screen INA260 0x40
    R3  6V  DROK buck     ARM servo distribution                  (no sensor)

The arm servos sit on their own 6V rail with NO current sensor on it, so nothing here can see
them. Standard PWM servos give no feedback either, so an unplugged arm joint remains an
inspect-by-eye fault until an INA260 is added to R3. That is worth doing next time that section
of the power tree is open -- it is the one change that would make arm connectors as diagnosable
as motor connectors now are.

RUN THE ROVER ON A BLOCK. This moves the steering. Stop the service first -- it holds the
servos centered and shares the bus:

    sudo systemctl stop willy-rover
    python3 scripts/servo_current_test.py
    sudo systemctl start willy-rover

Takes corner names as arguments (lf rf lm rm lr rr) or tests all six.
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_RAIL=config.INA260_SERVO_ADDR   # 0x40, the 5V UBEC rail
_BUS=1
_SWEEP_DEG=15.0     # modest: enough current to measure, well inside the clamped half-span, and
                    # not enough to bind a corner against its mechanical stop
_SETTLE_S=0.6       # let the rail settle and the servo finish before taking a baseline
_MOVE_SAMPLE_S=0.5  # sample window during motion -- a servo draws while moving, far less holding
_UNPLUGGED_A=0.05   # PROVISIONAL. Below this, treat the connector as not making contact.
                    # Derived from nothing but expectation -- the first real run measures what a
                    # healthy steering servo actually draws on this rover, and this number should
                    # be set from that, the same way the wheel test's threshold needs revisiting
                    # (its documented 0.11A reference measured 0.066-0.093A in practice).

def _read_amps(bus,addr):
    """Amps from one INA260. Raises OSError if the device NAKs."""
    d=bus.read_i2c_block_data(addr,0x01,2); raw=(d[0]<<8)|d[1]   # 1.25mA/LSB, signed
    if raw>32767: raw-=65536
    return raw*1.25/1000.0

def _mean_amps(bus,n=8,period=0.05):
    """Averaged: this rail also carries the AMS1117 and the Pi screen, so it is never quiet."""
    vals=[]
    for _ in range(n):
        try: vals.append(_read_amps(bus,_RAIL))
        except OSError: pass
        time.sleep(period)
    return sum(vals)/len(vals) if vals else float('nan')

def _peak_amps(bus,seconds):
    """Peak, not mean: a servo's draw is a burst while it slews, and a mean over a window that
    includes the settled tail understates it badly."""
    end=time.time()+seconds; peak=0.0
    while time.time()<end:
        try: peak=max(peak,abs(_read_amps(bus,_RAIL)))
        except OSError: pass
        time.sleep(0.02)
    return peak

def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this test needs the real bus.',file=sys.stderr)
        return 1
    try:
        from smbus2 import SMBus
    except ImportError:
        print('smbus2 not installed in this interpreter',file=sys.stderr); return 1
    from motors import Steering

    corners=sys.argv[1:] or ['lf','rf','lm','rm','lr','rr']
    valid=('lf','rf','lm','rm','lr','rr')
    bad=[c for c in corners if c not in valid]
    if bad:
        print(f'unknown corner(s): {" ".join(bad)}',file=sys.stderr)
        print(f'valid: {" ".join(valid)}',file=sys.stderr); return 1

    steer=Steering()
    steer.center_all(); time.sleep(1.0)
    print(f'rail 0x{_RAIL:02x}  sweep +/-{_SWEEP_DEG}deg  unplugged threshold {_UNPLUGGED_A} A')
    print(f'{"corner":7} {"ch":4} {"idle A":>8} {"peak A":>8} {"delta A":>8}  verdict')
    failures=0
    with SMBus(_BUS) as bus:
        for c in corners:
            ch=Steering._CORNERS[c]
            steer.set_angle(c,0.0); time.sleep(_SETTLE_S)
            idle=_mean_amps(bus)
            # Move away from centre and measure the slew, then come back.
            steer.set_angle(c,_SWEEP_DEG)
            peak=_peak_amps(bus,_MOVE_SAMPLE_S)
            steer.set_angle(c,-_SWEEP_DEG)
            peak=max(peak,_peak_amps(bus,_MOVE_SAMPLE_S))
            steer.set_angle(c,0.0); time.sleep(_SETTLE_S)
            delta=peak-idle
            ok=delta>=_UNPLUGGED_A
            if not ok: failures+=1
            verdict='ok' if ok else 'NO DRAW -- check connector at the servo and the PCA header'
            print(f'{c:7} CH{ch:<2} {idle:8.3f} {peak:8.3f} {delta:8.3f}  {verdict}')
    steer.center_all()
    print('\nAll corners returned to centre.')
    if failures:
        print(f'{failures} corner(s) drew nothing. Wires first: the connector at the servo, then '
              f'the PCA9685 header pin, then the servo itself.')
    else:
        print('If every corner reads similarly, record the healthy range and set '
              '_UNPLUGGED_A from it rather than leaving the provisional value.')
    return 1 if failures else 0

if __name__=='__main__':
    sys.exit(main() or 0)
