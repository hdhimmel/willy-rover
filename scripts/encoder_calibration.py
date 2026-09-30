#!/usr/bin/env python3
"""Measure ENCODER_COUNTS_PER_REV by hand-turning a wheel, reading Pico A over uart4-pi5.

WHY THIS EXISTS: odometry.py computes distance as counts x circumference /
ENCODER_COUNTS_PER_REV, so that one constant scales every distance, speed and closed-loop
correction on the rover. It has been wrong twice by deriving it from an assumed gear ratio
instead of measuring it. This measures it.

REPOINTED AT PICO A 2026-09-29. It used to read sensors.Encoders over the MCP23017 at 0x27.
That expander is off the bus (a live scan finds ten devices and no 0x27), and the counts now
arrive as $E frames on /dev/ttyAMA4. Nothing else about the method changes.

TWO REASONS THE CONFIGURED VALUE IS WRONG TODAY, and they compound:

  1. WRONG GEARBOX. config.ENCODER_COUNTS_PER_REV=752 is "11 PPR x4 quadrature x17.1:1",
     the old 620 RPM gearing. The fitted motors are the 170 RPM / 35.5:1 units
     (owner-stated 2026-09-29), which is what config.ENCODER_COUNTS_PER_REV_170RPM=1562
     was put there for -- it is still marked "not active".

  2. WRONG DECODE, and this one is easy to miss. Both 752 and 1562 assume x4 quadrature.
     pico_a.py's PIO program counts RISING EDGES ON PHASE A ONLY, because all six Phase B
     greens have read dead since 2026-09-18. So the Pico-path figure is x1, not x4:

         11 PPR x 35.5 = ~390.5 counts per wheel revolution

     Treat that as the number to CHECK THIS MEASUREMENT AGAINST, not as the answer. 11 PPR
     is vendor-table data, and this rover has already been bitten once by trusting a vendor
     table over a bench measurement -- that is how 3292 and then 752 got into config.py.

  When Phase B is repaired and the firmware moves to a quadrature decoder, this number
  quadruples. Re-run this script that day; the wire protocol does not change but the
  constant does.

IT ALSO SETTLES THE CHANNEL MAPPING, which currently needs settling. On 2026-09-29 the
encoder harness was found LEFT/RIGHT TRANSPOSED on Pico A's J3: driving lf spun the
left-front wheel while its counts arrived on the rf channel. Turn ONE wheel and see which
row moves -- that is the direct test, and it is how the transposition was found.

HOW TO RUN. Stop the service first; it opens its own reader.

    sudo systemctl stop willy-rover
    python3 scripts/encoder_calibration.py lf 10
    sudo systemctl start willy-rover

Mark the tyre with tape, then turn that wheel EXACTLY the stated number of full revolutions,
steadily, during the countdown. Direction does not matter -- Phase A edge counting has no
sign, which is also why a reversed motor is invisible to odometry. More revolutions is
better: an error in judging one turn is divided by the count.
"""
import os,sys,threading,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import sensors

_DEFAULT_REVS=10
_DEFAULT_WINDOW_S=45.0
_DEVICE='/dev/ttyAMA4'          # Pico A, uart4-pi5, Pi GP12/GP13
_BAUD=115200
# $E field order. NOT a local copy any more: this is imported from sensors.Encoders so
# there is one definition. It was ('rf','rm','lf','lm','rr','lr') until 2026-09-30 --
# copied out of firmware/README.md, which was itself wrong -- and it would have
# attributed every measurement to the wheel on the other side of the rover. The one
# thing this script exists to do is assign counts to the right wheel.
_WHEELS=sensors.Encoders._ORDER
_PHASE_A_ONLY_EXPECTED=11*35.5            # see the docstring -- a check, not an answer


def _xor(body):
    c=0
    for ch in body: c^=ord(ch)
    return c


class PicoEncoders:
    """Newest counts from Pico A's $E stream. Checksum-verified, wrap-safe."""
    def __init__(self,device=_DEVICE):
        self._device=device; self._counts=None; self._frames=0; self._bad=0
        self._stop=threading.Event(); self._thread=None
    @property
    def counts(self):
        c=self._counts
        return dict(zip(_WHEELS,c)) if c else None
    def start(self):
        import serial
        self._serial=serial.Serial(self._device,_BAUD,timeout=0.2)
        self._thread=threading.Thread(target=self._read,daemon=True); self._thread.start()
    def _read(self):
        buf=b''
        with self._serial as sp:
            sp.reset_input_buffer()
            while not self._stop.is_set():
                n=sp.in_waiting
                if not n:
                    time.sleep(0.005); continue
                buf+=sp.read(n)
                while b'\n' in buf:
                    line,buf=buf.split(b'\n',1)
                    s=line.strip().decode('ascii','replace')
                    if not s.startswith('$E,') or '*' not in s: continue
                    body,_,cs=s[1:].rpartition('*')
                    if cs.upper()!='%02X'%_xor(body): self._bad+=1; continue
                    self._counts=[int(x) for x in body.split(',')[3:9]]; self._frames+=1
    def stop(self):
        self._stop.set()
        if self._thread: self._thread.join(timeout=1.0)


def _delta(after,before):
    return (after-before)&0xFFFFFFFF     # PIO counter is unsigned 32-bit


def main():
    if config.SIMULATE_HARDWARE:
        print('SIMULATE_HARDWARE is on -- this needs the real encoders.',file=sys.stderr)
        return 1
    wheel=sys.argv[1] if len(sys.argv)>1 else None
    if wheel not in _WHEELS:
        print('usage: encoder_calibration.py <wheel> [revolutions] [seconds]',file=sys.stderr)
        print(f'valid wheels: {" ".join(_WHEELS)}',file=sys.stderr)
        return 1
    revs=float(sys.argv[2]) if len(sys.argv)>2 else _DEFAULT_REVS
    window=float(sys.argv[3]) if len(sys.argv)>3 else _DEFAULT_WINDOW_S

    enc=PicoEncoders(); enc.start()
    time.sleep(1.0)
    if enc.counts is None:
        print(f'No $E frames on {_DEVICE}. Pico A is not talking -- check main.py is '
              f'installed (not pico_a.py), the board LED is lit and winking, and that '
              f'pinctrl get 12,13 reads TXD4/RXD4.',file=sys.stderr)
        enc.stop(); return 1
    start=dict(enc.counts)
    print(f'Turn the {wheel.upper()} wheel exactly {revs:g} full revolutions over the next '
          f'{window:g}s.')
    print(f'configured ENCODER_COUNTS_PER_REV = {config.ENCODER_COUNTS_PER_REV}  '
          f'(expect ~{_PHASE_A_ONLY_EXPECTED:.0f} on this transport)\n')
    try:
        end_t=time.time()+window
        while time.time()<end_t:
            time.sleep(2.0)
            now=enc.counts or start
            live={w:_delta(now[w],start[w]) for w in now if _delta(now[w],start[w])}
            remaining=max(0.0,end_t-time.time())
            print(f'  {remaining:5.1f}s left  counts so far: {live or "(nothing moving yet)"}',
                  flush=True)
    finally:
        final=dict(enc.counts or start)
        enc.stop()

    deltas={w:_delta(final[w],start[w]) for w in final}
    moved={w:d for w,d in deltas.items() if d>20}   # 20 counts of slop ignores line noise
    print(f'\n=== result ===   {enc._frames} frames, {enc._bad} bad checksums')
    for w,d in sorted(deltas.items()):
        print(f'  {w:4} {d:+8d} counts' + ('  <-- MOVED' if w in moved else ''))

    if not moved:
        print('\nNothing counted. Either the wheel was not turned, or that channel is not '
              'reporting -- check the 12-way at J3 and the 6-pin JST at the motor before '
              'assuming the numbers. A motor open at its terminals counts as neither.')
        return 1
    if len(moved)>1:
        print(f'\nMore than one row counted: {sorted(moved)}. Either several wheels were '
              f'turned, or channels are crosstalking. Re-run turning only one.')
    if wheel not in moved:
        print(f'\nMAPPING IS WRONG: you turned {wheel.upper()} but {sorted(moved)} counted. '
              f'As of 2026-09-29 the J3 harness is left/right transposed at the same position '
              f'({wheel} landing on {sorted(moved)[0]} is exactly that). Fix the harness, not '
              f'the config -- MOTOR_PORT was confirmed correct by watching the wheels.')
    measured=deltas[wheel] if wheel in moved else list(moved.values())[0]
    per_rev=measured/revs
    print(f'\nmeasured {per_rev:.1f} counts per revolution over {revs:g} revs')
    print(f'configured {config.ENCODER_COUNTS_PER_REV}  ->  ratio '
          f'{config.ENCODER_COUNTS_PER_REV/per_rev:.2f}x')
    print(f'against the Phase-A-only prediction of {_PHASE_A_ONLY_EXPECTED:.0f}  ->  ratio '
          f'{_PHASE_A_ONLY_EXPECTED/per_rev:.2f}x')
    print(f'\nSet ENCODER_COUNTS_PER_REV={per_rev:.0f} and re-check against a driven, measured '
          f'distance before trusting it -- hand-turning removes load, so this is the geometric '
          f'number, not the number under slip. If it lands near '
          f'{_PHASE_A_ONLY_EXPECTED*4:.0f} instead, the firmware is decoding quadrature and '
          f'this script\'s x1 assumption is stale.')
    return 0

if __name__=='__main__':
    sys.exit(main() or 0)
