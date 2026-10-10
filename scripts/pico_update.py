#!/usr/bin/env python3
"""Update a Pico's firmware over its UART (2026-10-10). Run ON WILLIE, service stopped:

    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/pico_update.py b                 # firmware/pico_b.py -> Pico B
    venv/bin/python3 scripts/pico_update.py a --file other.py
    sudo systemctl start willy-rover

The board must already run firmware/launcher.py as main.py and have uartupd.py (one USB install,
firmware/README.md). Sequence: BEGIN -> DATA chunks (each acknowledged) -> END (board verifies
size + adler32) -> COMMIT (board swaps app.py, marks it on trial, resets) -> wait for the new
board's I frame -> its version must match the file's VERSION -> CONFIRM. If the new firmware
never comes up, the board's launcher puts the old one back by itself after two failed boots.
"""
import argparse,os,re,subprocess,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

CHUNK=128           # bytes per DATA line -> 256 hex chars, inside the board's 600-char line limit
ACK_TIMEOUT_S=1.0
RETRIES=5
BOOT_TIMEOUT_S=20.0


def adler32(data,a=1,b=0):
    for x in data:
        a=(a+x)%65521; b=(b+a)%65521
    return (b<<16)|a

def file_version(text):
    m=re.search(r'^VERSION\s*=\s*"([^"]+)"',text,re.M)
    return m.group(1) if m else None


class Link:
    """Line I/O with the board, picking $U and $I frames out of the telemetry stream."""
    def __init__(self,ser): self.ser=ser; self.buf=b''
    def send(self,line): self.ser.write(line.encode()+b'\n'); self.ser.flush()
    def wait(self,kinds,timeout):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.buf+=self.ser.read(256) or b''
            while b'\n' in self.buf:
                raw,self.buf=self.buf.split(b'\n',1)
                raw=raw.strip()
                if not raw.startswith(b'$'): continue
                body=raw[1:].split(b'*',1)[0].decode(errors='replace')
                if body.split(',',1)[0] in kinds: return body
        return None


def transfer(link,data,log=print):
    """Send `data` and verify it on the board. Raises RuntimeError on failure; nothing on the
    board has changed until this returns and commit() is called."""
    link.send(f'UPD BEGIN {len(data)} {adler32(data):08x}')
    r=link.wait({'U'},3.0)
    if r!='U,ready': raise RuntimeError(f'BEGIN: {r}')
    n=(len(data)+CHUNK-1)//CHUNK
    for seq in range(n):
        line=f'UPD DATA {seq} {data[seq*CHUNK:(seq+1)*CHUNK].hex()}'
        for attempt in range(RETRIES):
            link.send(line)
            r=link.wait({'U'},ACK_TIMEOUT_S)
            if r==f'U,ack,{seq}': break
            if r and r.startswith('U,err'): raise RuntimeError(f'chunk {seq}: {r}')
        else:
            link.send('UPD ABORT'); raise RuntimeError(f'chunk {seq}: no ack after {RETRIES} tries')
    link.send('UPD END')
    r=link.wait({'U'},5.0)
    if r!='U,ok': raise RuntimeError(f'verify failed: {r}')
    log(f'sent and verified: {len(data)} bytes in {n} chunks')


def commit_and_confirm(link,expect_version,log=print):
    link.send('UPD COMMIT')
    r=link.wait({'U'},3.0)
    if r!='U,commit': raise RuntimeError(f'COMMIT: {r}')
    log('board resetting into the new firmware...')
    end=time.monotonic()+BOOT_TIMEOUT_S; ident=None
    while time.monotonic()<end and ident is None:
        link.send('ID')
        ident=link.wait({'I'},1.0)
    if ident is None:
        raise RuntimeError('no I frame after reset -- the board will roll back on its own after two failed boots')
    ver=ident.split(',')[-1]
    if expect_version and ver!=expect_version:
        raise RuntimeError(f'board reports {ver}, expected {expect_version} -- NOT confirmed; '
                           f'send UPD ROLLBACK or retry')
    link.send('UPD CONFIRM')
    r=link.wait({'U'},3.0)
    if r!='U,confirmed': raise RuntimeError(f'CONFIRM: {r}')
    log(f'confirmed: board runs {ver}')
    return ver


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('board',choices=('a','b'))
    ap.add_argument('--file')
    ap.add_argument('--force',action='store_true',help='run even if the service looks active')
    args=ap.parse_args()
    root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path=args.file or os.path.join(root,'firmware',f'pico_{args.board}.py')
    port=config.PICO_A_DEVICE if args.board=='a' else config.PICO_B_DEVICE
    if not args.force:
        st=subprocess.run(['systemctl','is-active','willy-rover'],capture_output=True,text=True).stdout.strip()
        if st=='active':
            print('willy-rover is running and owns this UART. Stop it first (sudo systemctl stop willy-rover).'); return 2
    data=open(path,'rb').read()
    ver=file_version(data.decode('utf-8',errors='replace'))
    import serial
    with serial.Serial(port,config.PICO_BAUD if hasattr(config,'PICO_BAUD') else 115200,timeout=0.05) as ser:
        ser.reset_input_buffer()
        link=Link(ser)
        link.send('ID'); cur=link.wait({'I'},2.0)
        print(f'{port}: board says {cur!r}; sending {os.path.basename(path)} ({len(data)} bytes, version {ver})')
        try:
            transfer(link,data); commit_and_confirm(link,ver)
        except RuntimeError as e:
            print(f'FAILED: {e}'); return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
