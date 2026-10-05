#!/usr/bin/env python3
"""Steering calibration jog -- find each corner's straight-ahead pulse (STEER_CENTER_US).

Moves real servos. Stop the service first so nothing else drives PCA9685 0x42:

    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/steer_jog.py              # interactive
    venv/bin/python3 scripts/steer_jog.py lf 1540      # one shot: set one corner, exit
    venv/bin/python3 scripts/steer_jog.py center       # every corner to its STEER_CENTER_US
    sudo systemctl start willy-rover

Corners: lf rf lm rm lr rr. Pulses are clamped to SERVO_MIN_US..SERVO_MAX_US (1000-2000),
the narrowest documented servo range, so a narrow-mode unit cannot be driven into a bind.

A corner is calibrated when its wheel points dead ahead, sighted along the chassis side.
Copy the final numbers into config.STEER_CENTER_US. The PCA9685 keeps outputting the last
pulse after this exits until Steering's idle release or a restart; the wheel stays put either
way, because the linkage backdrives stiffly.
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from motors import Steering

CORNERS=('lf','rf','lm','rm','lr','rr')


def main(argv):
    s=Steering()
    pulse={c:Steering.center_us(c) for c in CORNERS}
    if argv and argv[0]=='center':
        s.center_all(); time.sleep(0.6); print({c:round(v) for c,v in pulse.items()}); return 0
    if len(argv)==2 and argv[0] in CORNERS:
        us=s.set_pulse(argv[0],float(argv[1])); time.sleep(0.6)
        print(f'{argv[0]}: {us:.0f}us'); return 0
    if argv:
        print(__doc__); return 2

    cur='lf'; step=10.0
    print('Steering jog -- small steps, watch the wheel.')
    print('Commands: c <corner> | + | - | step <us> | set <us> | center | show | q')
    s.set_pulse(cur,pulse[cur])
    while True:
        try:
            parts=input(f'[{cur} @ {pulse[cur]:.0f}us, step={step:.0f}]> ').strip().split()
        except (EOFError,KeyboardInterrupt):
            print(); break
        if not parts: continue
        c=parts[0]
        if c=='q': break
        elif c=='c' and len(parts)>1 and parts[1] in CORNERS:
            cur=parts[1]; pulse[cur]=s.set_pulse(cur,pulse[cur])
        elif c in ('+','-'):
            pulse[cur]=s.set_pulse(cur,pulse[cur]+(step if c=='+' else -step))
        elif c=='step' and len(parts)>1: step=float(parts[1])
        elif c=='set' and len(parts)>1: pulse[cur]=s.set_pulse(cur,float(parts[1]))
        elif c=='center': s.center_all(); pulse={k:Steering.center_us(k) for k in CORNERS}
        elif c=='show': print({k:round(v) for k,v in pulse.items()})
        else: print('unknown command:',c)
    print('STEER_CENTER_US=',{k:round(v) for k,v in pulse.items()})
    return 0


if __name__=='__main__':
    sys.exit(main(sys.argv[1:]))
