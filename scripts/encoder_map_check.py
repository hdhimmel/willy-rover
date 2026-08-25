#!/usr/bin/env python3
"""Establish the real ENCODER_PINS mapping by driving one wheel at a time.

WHY THIS EXISTS: section 7.2 of the Master Hardware Design flags the Encoder A/B column as
UNVERIFIED. The motor ports turned out not to follow position order (M1=middle, M2=front,
M3=rear, corrected 2026-08-24), and since the encoders were landed at the same time as each
motor they plausibly carry the same error. Nothing had ever tested it.

WHY IT DRIVES RATHER THAN HAND-TURNS: scripts/encoder_calibration.py asks the owner to turn a
wheel by hand, and on 2026-08-25 that was found not to work at all on this rover -- 30s of
hand-turning produced ONE distinct pin state, while 3s of driving produced seven. The encoder
sits on the motor shaft behind the 17.1:1 gearbox, and turning the wheel does not back-drive it.
Any encoder measurement on this hardware has to be taken under power.

Reads the MCP23017's GPIO registers directly rather than going through sensors.Encoders, because
the decode in that class assumes the very mapping this script is trying to verify.

RUN THE ROVER ON A BLOCK, WHEELS FREE. Stop the service first:

    sudo systemctl stop willy-rover
    python3 scripts/encoder_map_check.py
    sudo systemctl start willy-rover
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_IODIRA=0x00; _IODIRB=0x01; _GPPUA=0x0C; _GPPUB=0x0D
_GPIOA=0x12; _GPIOB=0x13
_DUTY=0.6
_DRIVE_S=2.5
_SETTLE_S=0.5
_MIN_EDGES=20      # below this, treat as PWM crosstalk rather than a real quadrature signal

def _pin_name(i): return f'A{i}' if i<8 else f'B{i-8}'

def _expected():
    """{pin_index: wheel} from the CURRENT config, for comparison against measurement."""
    out={}
    for w,(bank,a,bb) in config.ENCODER_PINS.items():
        base=0 if bank=='A' else 8
        out[base+a]=f'{w}.A'; out[base+bb]=f'{w}.B'
    return out

def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this needs the real bus.',file=sys.stderr); return 1
    try:
        import smbus2
    except ImportError:
        print('smbus2 not installed',file=sys.stderr); return 1
    from motors import DriveBase

    bus=smbus2.SMBus(1); addr=config.ENCODER_ADDR
    for reg,val in ((_IODIRA,0xFF),(_IODIRB,0xFF),(_GPPUA,0xFF),(_GPPUB,0xFF)):
        bus.write_byte_data(addr,reg,val)

    def count_edges(seconds):
        """Edges per pin over the window. Edges, not states: a quadrature channel under power
        toggles continuously, while crosstalk shows up as a few isolated flips."""
        tog=[0]*16
        pa=bus.read_byte_data(addr,_GPIOA); pb=bus.read_byte_data(addr,_GPIOB)
        end=time.time()+seconds
        while time.time()<end:
            try:
                ga=bus.read_byte_data(addr,_GPIOA); gb=bus.read_byte_data(addr,_GPIOB)
            except OSError:
                continue
            for i in range(8):
                if ((ga>>i)&1)!=((pa>>i)&1): tog[i]+=1
                if ((gb>>i)&1)!=((pb>>i)&1): tog[8+i]+=1
            pa,pb=ga,gb
            time.sleep(0.002)
        return tog

    drive=DriveBase()
    exp=_expected()
    print(f'driving each wheel at {_DUTY} for {_DRIVE_S}s, watching MCP23017 0x{addr:02x}')
    print(f'(pins with fewer than {_MIN_EDGES} edges are treated as crosstalk)\n')
    findings={}
    try:
        for w in ('lf','lm','lr','rf','rm','rr'):
            for m in drive._motors.values(): m.throttle=None
            time.sleep(_SETTLE_S)
            drive._motors[w].throttle=_DUTY
            tog=count_edges(_DRIVE_S)
            drive._motors[w].throttle=None
            active=sorted(((n,i) for i,n in enumerate(tog) if n>=_MIN_EDGES),reverse=True)
            findings[w]=active
            if not active:
                print(f'  {w}: NOTHING TOGGLED -- encoder not reporting for this wheel')
                continue
            desc=', '.join(f'{_pin_name(i)}={n} edges (config says {exp.get(i,"unused")})'
                           for n,i in active)
            print(f'  {w}: {desc}')
    finally:
        for m in drive._motors.values(): m.throttle=None
        try: drive.cleanup()
        except Exception: pass

    print('\n=== proposed ENCODER_PINS from measurement ===')
    for w,active in findings.items():
        if len(active)<2:
            print(f"  {w}: INCONCLUSIVE ({len(active)} active pin(s)) -- need a clean pair")
            continue
        pins=sorted(i for _n,i in active[:2])
        bank='A' if pins[0]<8 else 'B'
        if (pins[0]<8)!=(pins[1]<8):
            print(f'  {w}: pins span both banks ({_pin_name(pins[0])},{_pin_name(pins[1])}) '
                  f'-- suspicious, re-run before trusting')
            continue
        base=0 if bank=='A' else 8
        print(f"  '{w}':('{bank}',{pins[0]-base},{pins[1]-base})"
              f"   config has {config.ENCODER_PINS[w]}")
    print('\nA/B order within each pair is NOT determined here -- this shows which pins belong to '
          'which wheel, not which is channel A. Getting A/B backwards only inverts that wheel\'s '
          'count sign, which is the easier half to fix once direction is checked under drive.')
    return 0

if __name__=='__main__':
    sys.exit(main() or 0)
