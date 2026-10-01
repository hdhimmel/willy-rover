#!/usr/bin/env python3
"""FSR grip curve -- close the gripper on a real object in small steps, record A1 at each.

WHY THIS EXISTS: Master Hardware Design §6.6 says the FSR402 must be calibrated "with
whatever actually contacts the pad in service -- not with a fingertip on the bench", and
that its response is logarithmic, so a linear scale gives plausible wrong numbers. The
first powered read (2026-10-01) was a fingertip: it jumped from ~1 mV straight to ~3.1 V,
which proves the wiring and says nothing about the curve. This uses the gripper itself.

WHAT IT MEASURES IS NOT NEWTONS. config.py records that grip force is set by CURRENT, not
position -- the jaws close on whatever is held and the servo pushes harder as it draws more.
So the x-axis here is the arm rail's current (INA260 0x44, R3 6V), the thing the gripper
actually controls, and the y-axis is A1. That is enough to set thresholds for "holding
something" and "it was pulled out of my hand", which is what retrieval_task.py needs.
Absolute force needs a reference load (a kitchen scale under the jaw) and is a later step.

STOPS AT _STOP_A. config.py: "Stop feeding past ~0.4-0.5A: it grips there, and beyond that
it is stalling and heating." Only the gripper channel is driven; every other joint is left
alone, so the rail current is the gripper's.

    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/fsr_grip_curve.py
    sudo systemctl start willy-rover

Put the object between the jaws, positioned so it presses on the pad, before starting.
"""
import os,sys,time,statistics
_HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.dirname(_HERE)); sys.path.insert(0,_HERE)
import config
from wheel_current_test import _read_amps

_RAIL=config.INA260_ARM_6V_ADDR
_OPEN_US=1500        # well open: 0.075A, nowhere near contact
_START_US=1600       # below the ~1700us jaw contact config.py records
_STOP_US=1780        # config.py measured 1.049A here -- the hard ceiling
_STEP_US=5
_DWELL_S=0.6         # let the servo arrive and the pad settle before reading
_STOP_A=0.50         # rail current at which to stop closing


def _fsr_k(v):
    """FSR resistance in kΩ from the divider: Vout = 3.3 x 10k / (R + 10k)."""
    return 10.0*(3.3/v-1) if v>0.01 else float('inf')


def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this needs the real gripper.',file=sys.stderr)
        return 1
    from smbus2 import SMBus
    import arm,sensors
    a=arm.Arm(); adc=sensors.ADC()
    def a1():
        return statistics.median(adc.read_channel(1)*adc._LSB for _ in range(5))
    def amps(bus):
        return statistics.mean(_read_amps(bus,_RAIL) for _ in range(6))

    rows=[]
    with SMBus(1) as bus:
        a.set_pulse('gripper',_OPEN_US); time.sleep(1.0)
        print(f'open {_OPEN_US}us: rail {amps(bus):.3f} A, A1 {a1():.3f} V\n')
        print(f'{"us":>5} {"A":>6} {"A1 V":>6} {"R_fsr k":>8}')
        try:
            for us in range(_START_US,_STOP_US+1,_STEP_US):
                a.set_pulse('gripper',us); time.sleep(_DWELL_S)
                i=amps(bus); v=a1(); rows.append((us,i,v))
                print(f'{us:5d} {i:6.3f} {v:6.3f} {_fsr_k(v):8.1f}',flush=True)
                if i>=_STOP_A:
                    print(f'\nstopped at {_STOP_A} A'); break
        finally:
            a.set_pulse('gripper',_OPEN_US); time.sleep(1.0)
            print(f'released: A1 {a1():.3f} V')

    touched=[r for r in rows if r[2]>0.05]
    if not touched:
        print('\nA1 never rose. The object is not pressing on the pad, or the pad is not on '
              'the jaw face that closes -- check before suspecting the sensor.')
        return 1
    print(f'\nfirst contact at {touched[0][0]}us / {touched[0][1]:.3f} A '
          f'({touched[0][2]:.3f} V)')
    return 0

if __name__=='__main__':
    sys.exit(main() or 0)
