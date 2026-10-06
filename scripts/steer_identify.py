#!/usr/bin/env python3
"""Steering channel identification -- which wheel is on which PCA9685 0x42 channel.

Moves real servos, ONE channel at a time, and waits for you before each one. Stop the service
first so nothing else drives 0x42:

    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/steer_identify.py            # the six wired channels 0 1 2 3 8 9
    venv/bin/python3 scripts/steer_identify.py 4 5 6 7    # any channels you name
    sudo systemctl start willy-rover

Each channel gets a small wiggle about 1500us (every wheel is horned straight there,
2026-10-05) and ends back at 1500. Answer with the corner that moved -- lf rf lm rm lr rr --
or n (nothing moved), r (repeat), q (quit). The result is printed as the config.STEER_* line.
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from motors import Steering

CORNERS=('lf','rf','lm','rm','lr','rr')
WIGGLE_US=150        # +-150 about 1500: visible, well inside SERVO_MIN_US..SERVO_MAX_US


def wiggle(s,ch):
    for us in (1500+WIGGLE_US,1500-WIGGLE_US,1500+WIGGLE_US,1500):
        s._set_pulse(ch,us); time.sleep(0.4)


def main(argv):
    channels=[int(a) for a in argv] if argv else [0,1,2,3,8,9]
    s=Steering(); found={}
    for ch in channels:
        try: input(f'\nch{ch}: watch the wheels, Enter to wiggle (Ctrl-C to stop) ')
        except (EOFError,KeyboardInterrupt): print(); break
        while True:
            wiggle(s,ch)
            try: ans=input(f'ch{ch}: which wheel moved? [{" ".join(CORNERS)} / n / r / q] ').strip().lower()
            except (EOFError,KeyboardInterrupt): ans='q'
            if ans=='r': continue
            break
        if ans=='q': break
        if ans in CORNERS:
            if ans in found: print(f'  {ans} was already ch{found[ans]} -- keeping both, check the wiring')
            found.setdefault(ans,ch)
        elif ans!='n': print(f'  unrecognised {ans!r}, ch{ch} skipped')
    print('\nFound:',{c:found[c] for c in CORNERS if c in found})
    missing=[c for c in CORNERS if c not in found]
    if missing: print('Not found:',' '.join(missing))
    else:
        print('config.py:')
        print('STEER_LF={lf}; STEER_RF={rf}; STEER_LM={lm}; STEER_RM={rm}; STEER_LR={lr}; STEER_RR={rr}'.format(**found))
    return 0


if __name__=='__main__':
    sys.exit(main(sys.argv[1:]))
