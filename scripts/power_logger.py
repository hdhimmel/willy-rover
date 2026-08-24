#!/usr/bin/env python3
"""Standalone rail logger — captures the power trace across a shutdown.

WHY THIS EXISTS: on 2026-08-24 Witty Pi powered Willy down three times with
`Shutdown reason: Vin < Vlow` (8.0V threshold against the DROK 9V feed) at 84%
battery. Each event destroyed its own evidence: journald on this machine runs
volatile (`--list-boots` only ever shows boot 0), so nothing survived the
reboot. Only /var/log/wp5d.log persisted, and it records the verdict without
the measurements behind it.

This logger answers the one open question — is VIN genuinely sagging, or is
Witty Pi misreading it — by writing INA260 0x45 voltage AND current together.
The pair is what discriminates:

    voltage falls, current PINNED FLAT   -> DROK in constant-current mode;
                                            the CC trimpot is the root cause
    voltage falls, current still RISING  -> resistance in the wire/terminal
    voltage HOLDS ~9V through a cutoff   -> Witty Pi's VIN reading is wrong,
                                            or the drop is downstream of 0x45

Deliberately independent of willy-rover.service: it must keep sampling when
the brain is stopped, faulted, or mid-shutdown. It only ever READS the bus.

DURABILITY: every row is flushed and fsync'd. A row that reached the file but
not the platter is a row we lose to exactly the event we're trying to catch —
which is how the first two shutdowns got away.
"""
import csv,os,sys,time

_RAILS=[(0x40,'servo_5v'),(0x44,'motor_12v'),(0x45,'pi_9v')]
_BUS=1
_PERIOD_S=0.5   # 2 Hz. Fast enough to catch a CC transition, light enough that
                # it can't starve the encoder thread on the shared bus (the
                # 2026-08-24 busy-loop regression is the cautionary tale here).
_OUT=os.environ.get('WILLY_POWER_LOG','/home/hhimmel/rover/logs/power_trace.csv')

def _read_ina260(bus,addr):
    """(volts, amps) from one INA260. Raises OSError if the device NAKs."""
    def rd(reg):
        d=bus.read_i2c_block_data(addr,reg,2); return (d[0]<<8)|d[1]
    volts=rd(0x02)*1.25/1000.0          # bus voltage register, 1.25mV/LSB
    raw=rd(0x01)                         # current register, 1.25mA/LSB, signed
    if raw>32767: raw-=65536
    return volts,raw*1.25/1000.0

def _throttled():
    """Raw get_throttled word, or '' if vcgencmd isn't answering. Bits 0-3 are
    live conditions, 16-19 sticky-since-boot — the same source the on-face
    power indicator reads."""
    try:
        import subprocess
        out=subprocess.run(['vcgencmd','get_throttled'],capture_output=True,
                           text=True,timeout=3).stdout.strip()
        return out.split('=')[1] if '=' in out else ''
    except Exception:
        return ''

def main():
    try:
        from smbus2 import SMBus
    except ImportError:
        print('smbus2 not installed in this interpreter',file=sys.stderr); return 1
    os.makedirs(os.path.dirname(_OUT),exist_ok=True)
    new=not os.path.exists(_OUT) or os.path.getsize(_OUT)==0
    cols=['iso_time','mono_s']+[f'{n}_{u}' for _,n in _RAILS for u in ('v','a')]+['throttled']
    with open(_OUT,'a',newline='') as fh:
        w=csv.writer(fh)
        if new: w.writerow(cols)
        # A boot marker makes each power cycle findable in one file — and the
        # LAST row before a marker is the final measurement before shutdown,
        # which is the whole point of running this.
        w.writerow(['# boot',time.strftime('%Y-%m-%d %H:%M:%S')]+['']*(len(cols)-2))
        fh.flush(); os.fsync(fh.fileno())
        n=0
        while True:
            row=[time.strftime('%Y-%m-%d %H:%M:%S'),f'{time.monotonic():.1f}']
            try:
                with SMBus(_BUS) as bus:
                    for addr,_ in _RAILS:
                        try:
                            v,a=_read_ina260(bus,addr)
                            row+= [f'{v:.3f}',f'{a:.3f}']
                        except OSError:
                            # Per-rail isolation, same rule sensors.py follows:
                            # one dead INA260 must not blind the other two.
                            row+=['','']
            except Exception:
                row+=['']*(2*len(_RAILS))
            # vcgencmd forks a process; at 2Hz that's wasteful and it can't
            # change faster than the thermal/PMIC path updates it anyway.
            row.append(_throttled() if n%10==0 else '')
            w.writerow(row)
            fh.flush(); os.fsync(fh.fileno())
            n+=1
            time.sleep(_PERIOD_S)

if __name__=='__main__':
    sys.exit(main() or 0)
