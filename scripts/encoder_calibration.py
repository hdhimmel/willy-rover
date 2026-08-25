#!/usr/bin/env python3
"""Measure ENCODER_COUNTS_PER_REV by hand-turning a wheel, and confirm A/B channel mapping.

WHY THIS EXISTS: config.ENCODER_COUNTS_PER_REV=3292 was derived as "823.1 PPR x4 quadrature",
and 823.1 PPR from an 11 PPR motor-shaft encoder implies a 74.8:1 gearbox. A JGA25-370 at 74.8:1
runs about 130 RPM on 12V -- which is the "6V, 100-200 RPM" motor spec that turned out on
2026-08-25 to be WRONG. The real motors are 12V 620 RPM, implying roughly 15:1, so the true
counts per wheel revolution is likely in the 700-850 region and the configured value is four to
five times too high.

That matters more than it sounds. odometry.py computes distance as
counts x circumference / ENCODER_COUNTS_PER_REV, so a value 4x too high makes Willy report about
a quarter of the distance he actually travels -- a larger error than the wheel-diameter fix
applied the same day, and in the same direction.

This measures it instead of deriving it from another assumed gear ratio, which is exactly how
the wrong number got there in the first place.

IT ALSO SETTLES THE A/B CHANNEL MAPPING. Section 7.2 of the Master Hardware Design flags the
Encoder A/B column as unverified: the motor ports turned out not to follow position order, so the
encoder channels cannot be assumed to either. Turning ONE wheel and seeing which entry moves
answers that directly -- if you turn the left front and the 'lm' row counts, the mapping is
wrong the same way MOTOR_PORT was.

HOW TO RUN. The service must be stopped: it drives its own Encoders instance and shares the bus.

    sudo systemctl stop willy-rover
    python3 scripts/encoder_calibration.py lf 10
    sudo systemctl start willy-rover

Mark the tyre with tape, then turn that wheel EXACTLY the stated number of full revolutions,
steadily, in the forward direction, during the countdown. Direction matters only for sign.
More revolutions is better: any error in judging a single turn is divided by the count.
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_DEFAULT_REVS=10
_DEFAULT_WINDOW_S=45.0

def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this needs the real encoders.',file=sys.stderr)
        return 1
    wheel=sys.argv[1] if len(sys.argv)>1 else None
    if wheel not in config.ENCODER_PINS:
        print(f'usage: encoder_calibration.py <wheel> [revolutions] [seconds]',file=sys.stderr)
        print(f'valid wheels: {" ".join(config.ENCODER_PINS)}',file=sys.stderr)
        return 1
    revs=float(sys.argv[2]) if len(sys.argv)>2 else _DEFAULT_REVS
    window=float(sys.argv[3]) if len(sys.argv)>3 else _DEFAULT_WINDOW_S

    from sensors import Encoders
    enc=Encoders(); enc.start()
    time.sleep(0.5)
    start=dict(enc.counts())
    print(f'Turn the {wheel.upper()} wheel exactly {revs:g} full revolutions over the next '
          f'{window:g}s.')
    print(f'configured ENCODER_COUNTS_PER_REV = {config.ENCODER_COUNTS_PER_REV}\n')
    try:
        end_t=time.time()+window
        while time.time()<end_t:
            time.sleep(2.0)
            now=enc.counts()
            live={w:now[w]-start[w] for w in now if now[w]!=start[w]}
            remaining=max(0.0,end_t-time.time())
            print(f'  {remaining:5.1f}s left  counts so far: {live or "(nothing moving yet)"}',
                  flush=True)
    finally:
        final=dict(enc.counts())
        try: enc.stop()
        except Exception: pass

    deltas={w:final[w]-start[w] for w in final}
    moved={w:d for w,d in deltas.items() if abs(d)>20}   # 20 counts of slop ignores bus noise
    print('\n=== result ===')
    for w,d in sorted(deltas.items()):
        mark='  <-- MOVED' if w in moved else ''
        print(f'  {w:4} {d:+8d} counts{mark}')

    if not moved:
        print('\nNothing counted. Either the wheel was not turned, or that encoder is not '
              'reporting -- check the 6-pin JST at the motor before assuming the numbers.')
        return 1
    if len(moved)>1:
        print(f'\nMore than one wheel counted: {sorted(moved)}. Either several were turned, or '
              f'channels are crosstalking. Re-run turning only one.')
    if wheel not in moved:
        print(f'\nMAPPING IS WRONG: you turned {wheel.upper()} but {sorted(moved)} counted. '
              f'config.ENCODER_PINS attributes this wheel to the wrong channel pair -- the same '
              f'failure MOTOR_PORT had. Fix ENCODER_PINS and section 7.2 together.')
    measured=abs(deltas[wheel]) if wheel in moved else abs(list(moved.values())[0])
    per_rev=measured/revs
    print(f'\nmeasured {per_rev:.1f} counts per revolution over {revs:g} revs')
    print(f'configured {config.ENCODER_COUNTS_PER_REV}  ->  ratio {config.ENCODER_COUNTS_PER_REV/per_rev:.2f}x')
    print(f'\nDistances reported so far were off by that ratio. Set '
          f'ENCODER_COUNTS_PER_REV={per_rev:.0f} and re-check against a driven, measured distance '
          f'before trusting it -- hand-turning removes load, so this is the geometric number, not '
          f'the number under slip.')
    return 0

if __name__=='__main__':
    sys.exit(main() or 0)
