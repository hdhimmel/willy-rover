import os,sys,types,importlib
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest

# Firmware update over the Pi UART (2026-10-10). Drives the REAL board-side receiver
# (firmware/uartupd.py) with the REAL Pi-side sender (scripts/pico_update.py), in a temp dir
# standing in for the Pico's flash, and the REAL launcher's trial/rollback logic.

FW=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'firmware')

@pytest.fixture
def board(tmp_path,monkeypatch):
    resets=[]
    monkeypatch.setitem(sys.modules,'machine',types.SimpleNamespace(reset=lambda: resets.append(1)))
    monkeypatch.syspath_prepend(FW)
    monkeypatch.chdir(tmp_path)
    (tmp_path/'app.py').write_text('VERSION = "b-0.1"\n')
    import uartupd; importlib.reload(uartupd)
    monkeypatch.setattr(uartupd.Receiver,'_reset',staticmethod(lambda: resets.append(1)))
    return uartupd,tmp_path,resets

class _Wire:
    """Pi Link <-> board Receiver, in-process. drop=set of DATA seqs whose first ack is lost."""
    def __init__(self,rx,drop=()):
        self.rx=rx; self.out=[]; self.drop=set(drop); self.version='b-0.2'
    def send(self,line):
        if line=='ID': self.out.append(f'I,B,uid,{self.version}'); return
        before=len(self.out)
        self.rx.handle(line.encode())
        if line.startswith('UPD DATA'):
            seq=int(line.split()[2])
            if seq in self.drop: self.drop.discard(seq); del self.out[before:]
    def wait(self,kinds,timeout):
        while self.out:
            m=self.out.pop(0)
            if m.split(',',1)[0] in kinds: return m
        return None

def _tool():
    sys.path.insert(0,os.path.join(os.path.dirname(FW),'scripts'))
    import pico_update; importlib.reload(pico_update); return pico_update

def test_full_update_swaps_files_and_confirms(board):
    uartupd,d,resets=board
    tool=_tool()
    new=('VERSION = "b-0.2"\n'+'x=1\n'*400).encode()
    w=_Wire(None); w.rx=uartupd.Receiver(lambda body: w.out.append(body))
    tool.transfer(w,new,log=lambda *a: None)
    assert not (d/'trial').exists() and (d/'app.py').read_text().startswith('VERSION = "b-0.1"')  # nothing changed yet
    tool.commit_and_confirm(w,'b-0.2',log=lambda *a: None)
    assert (d/'app.py').read_bytes()==new and (d/'app_prev.py').read_text().startswith('VERSION = "b-0.1"')
    assert resets==[1] and not (d/'trial').exists()          # confirmed -> off trial

def test_a_lost_ack_is_resent_without_writing_twice(board):
    uartupd,d,resets=board
    tool=_tool()
    new=bytes(range(256))*3
    w=_Wire(None,drop={1}); w.rx=uartupd.Receiver(lambda body: w.out.append(body))
    tool.transfer(w,new,log=lambda *a: None)                  # verify passes: no duplicate chunk
    assert (d/'app.new').read_bytes()==new

def test_a_corrupt_transfer_changes_nothing(board):
    uartupd,d,resets=board
    out=[]; rx=uartupd.Receiver(out.append)
    rx.handle(b'UPD BEGIN 4 00000000')                        # wrong checksum on purpose
    rx.handle(b'UPD DATA 0 41424344')
    rx.handle(b'UPD END')
    assert out[-1].startswith('U,err,verify')
    rx.handle(b'UPD COMMIT')
    assert out[-1]=='U,err,not verified' and (d/'app.py').read_text()=='VERSION = "b-0.1"\n' and resets==[]

def test_version_mismatch_is_not_confirmed(board):
    uartupd,d,resets=board
    tool=_tool()
    w=_Wire(None); w.version='b-0.1'; w.rx=uartupd.Receiver(lambda body: w.out.append(body))
    tool.transfer(w,b'VERSION = "b-0.2"\n',log=lambda *a: None)
    with pytest.raises(RuntimeError,match='NOT confirmed'):
        tool.commit_and_confirm(w,'b-0.2',log=lambda *a: None)
    assert (d/'trial').exists()                               # stays on trial -> launcher can roll back

def _run_launcher(d,monkeypatch,app_src):
    (d/'app.py').write_text(app_src)
    monkeypatch.setitem(sys.modules,'machine',types.SimpleNamespace(reset=lambda: (_ for _ in ()).throw(SystemExit('reset'))))
    monkeypatch.setitem(sys.modules,'time',types.SimpleNamespace(sleep=lambda s: None))
    sys.modules.pop('app',None)
    src=open(os.path.join(FW,'launcher.py')).read()
    with pytest.raises(SystemExit):
        exec(compile(src,'launcher.py','exec'),{'__name__':'launcher'})

def test_launcher_rolls_back_after_two_failed_trial_boots(board,monkeypatch):
    uartupd,d,resets=board
    monkeypatch.syspath_prepend(str(d))
    (d/'app_prev.py').write_text('def main(): raise SystemExit("good old firmware ran")\n')
    (d/'trial').write_text('0')
    bad='def main(): raise RuntimeError("new firmware crashes")\n'
    _run_launcher(d,monkeypatch,bad)            # boot 1 on trial: crash -> reset
    assert (d/'trial').read_text()=='1'
    _run_launcher(d,monkeypatch,bad)            # boot 2: crash -> reset
    assert (d/'trial').read_text()=='2'
    sys.modules.pop('app',None)
    src=open(os.path.join(FW,'launcher.py')).read()
    with pytest.raises(SystemExit,match='good old firmware'):
        exec(compile(src,'launcher.py','exec'),{'__name__':'launcher'})   # boot 3: rolled back
    assert not (d/'trial').exists() and (d/'app_bad.py').exists()
