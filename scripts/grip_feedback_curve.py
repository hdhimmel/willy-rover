#!/usr/bin/env python3
"""Gripper feedback curve -- step the gripper closed, record the pot wiper (ADS1115 A2) at each.

WHY THIS EXISTS: the FSR402 was replaced 2026-10-04 by position feedback from the gripper
MG90S itself (arm CH5): a wire on the servo's pot wiper, 47k/47k divider + 100 nF at the
ADS1115 end, AIN2 (Master Hardware Design §6.6). Nothing has a curve for it yet.

WHAT TO LOOK FOR. Run it twice:
  1. Jaws EMPTY. Wiper volts should track commanded us all the way -- that line is the
     free-travel curve (roughly linear; slope and offset are what we store).
  2. An object BETWEEN the jaws. The wiper should follow the empty curve, then flatten where
     the jaws meet the object while commanded us keeps rising and rail current climbs.
     The gap between commanded and actual position is the "holding something" signal
     retrieval_task.py needs; a sudden jump back onto the empty curve is "it was taken".

Rail current (INA260 0x44, R3 6V) is printed alongside because config.py records grip force
is set by CURRENT, not position. Stops at _STOP_A: "Stop feeding past ~0.4-0.5A: it grips
there, and beyond that it is stalling and heating." Only the gripper channel is driven.

    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/grip_feedback_curve.py
    sudo systemctl start willy-rover
"""
import os,sys,time,statistics
_HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.dirname(_HERE)); sys.path.insert(0,_HERE)
import config
from wheel_current_test import _read_amps

_RAIL=config.INA260_ARM_6V_ADDR
_OPEN_US=1500        # well open: 0.075A, nowhere near contact
_START_US=1500
_STOP_US=1780        # config.py measured 1.049A here -- the hard ceiling
_STEP_US=5
_DWELL_S=0.6         # let the servo arrive before reading (the 100 nF settles in ~10 ms)
_STOP_A=0.50         # rail current at which to stop closing


def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this needs the real gripper.',file=sys.stderr)
        return 1
    from smbus2 import SMBus
    import arm,sensors
    a=arm.Arm(); adc=sensors.ADC()
    def wiper():
        return statistics.median(adc.grip_feedback_volts() for _ in range(5))
    def amps(bus):
        return statistics.mean(_read_amps(bus,_RAIL) for _ in range(6))

    rows=[]
    with SMBus(1) as bus:
        a.set_pulse('gripper',_OPEN_US); time.sleep(1.0)
        print(f'open {_OPEN_US}us: rail {amps(bus):.3f} A, wiper {wiper():.3f} V\n')
        print(f'{"us":>5} {"A":>6} {"wiper V":>8} {"dV/step":>8}')
        try:
            prev=None
            for us in range(_START_US,_STOP_US+1,_STEP_US):
                a.set_pulse('gripper',us); time.sleep(_DWELL_S)
                i=amps(bus); v=wiper(); rows.append((us,i,v))
                dv='' if prev is None else f'{(v-prev)*1000:+7.1f}m'
                print(f'{us:5d} {i:6.3f} {v:8.3f} {dv:>8}',flush=True); prev=v
                if i>=_STOP_A:
                    print(f'\nstopped at {_STOP_A} A'); break
        finally:
            a.set_pulse('gripper',_OPEN_US); time.sleep(1.0)
            print(f'released: wiper {wiper():.3f} V')

    span=rows[-1][2]-rows[0][2] if len(rows)>1 else 0.0
    if abs(span)<0.02:
        print('\nWiper never moved. Check the wiper wire, the divider and that A2 is the input '
              'actually wired -- wires before code before parts.')
        return 1
    us_span=rows[-1][0]-rows[0][0]
    print(f'\n{rows[0][0]}->{rows[-1][0]}us moved the wiper {span:+.3f} V '
          f'({span*1000/us_span:+.2f} mV/us average)')
    return 0

if __name__=='__main__':
    sys.exit(main() or 0)
