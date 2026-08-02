#!/usr/bin/env python3
"""Interactive arm bench-calibration jog tool (§20.6). Run directly on the Pi — this moves
real servos. Small steps only; watch the arm while jogging. Existence of this tool is what
lets the real per-joint safe limits and preset-pose pulse-widths eventually get recorded into
config.py — none of that exists yet, arm.py has no autonomous motion to fall back on."""
import sys, os
sys.path.insert(0,os.path.dirname(__file__))
import config
from arm import Arm

def main():
    a=Arm()
    joints=a.joints
    cur=joints[0]; step=25.0
    print("Arm jog tool — small steps only, watch the arm.")
    print(f"Joints: {', '.join(joints)}")
    print("Commands: j <joint>  |  + | -  |  step <us>  |  center  |  center-all  |  q")
    while True:
        try:
            parts=input(f"[{cur} @ {a.pulse(cur):.0f}us, step={step:.0f}]> ").strip().split()
        except (EOFError,KeyboardInterrupt):
            print(); break
        if not parts: continue
        c=parts[0]
        if c=='q': break
        elif c=='j' and len(parts)>1 and parts[1] in joints: cur=parts[1]
        elif c=='j': print("usage: j <joint>")
        elif c=='+': print(f"{cur}: {a.set_pulse(cur,a.pulse(cur)+step):.0f}us")
        elif c=='-': print(f"{cur}: {a.set_pulse(cur,a.pulse(cur)-step):.0f}us")
        elif c=='step' and len(parts)>1:
            try: step=float(parts[1])
            except ValueError: print("bad step value")
        elif c=='center': print(f"{cur}: {a.set_pulse(cur,config.ARM_SERVO_CENTER_US):.0f}us")
        elif c=='center-all': a.center_all(); print("all joints centered")
        else: print("unknown command:", c)
    print("Final pulses:", {j:round(a.pulse(j)) for j in joints})

if __name__=='__main__':
    main()
