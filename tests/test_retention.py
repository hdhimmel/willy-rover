import os,sys,time,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config

# FR-1800-004: diagnostic/log retention has a defined maximum period. The log is capped by size
# by its RotatingFileHandler; the daily sweep adds the DATA_RETENTION_DAYS time cap on the
# rotated backups, and never touches the live file.

def _touch(path,age_days):
    with open(path,'w') as f: f.write('x')
    t=time.time()-age_days*86400; os.utime(path,(t,t))

def test_sweep_removes_old_rotated_logs_and_keeps_the_rest(tmp_path,monkeypatch):
    import brain
    monkeypatch.setattr(config,'WILLY_LOG_ROOT',str(tmp_path))
    live=tmp_path/config.LOG_FILE; old=tmp_path/f'{config.LOG_FILE}.4'; new=tmp_path/f'{config.LOG_FILE}.1'
    other=tmp_path/'power_trace.csv'
    _touch(live,90); _touch(old,config.DATA_RETENTION_DAYS+1); _touch(new,1); _touch(other,90)
    purged=[]
    b=object.__new__(brain.RoverBrain); b._retention_t=0.0
    b.memory=types.SimpleNamespace(purge_expired=lambda:purged.append('memory'))
    b._retention_sweep()
    assert purged==['memory']
    assert not old.exists()
    assert live.exists() and new.exists() and other.exists()

def test_sweep_runs_at_most_once_a_day(tmp_path,monkeypatch):
    import brain
    monkeypatch.setattr(config,'WILLY_LOG_ROOT',str(tmp_path))
    calls=[]
    b=object.__new__(brain.RoverBrain); b._retention_t=0.0
    b.memory=types.SimpleNamespace(purge_expired=lambda:calls.append(1))
    b._retention_sweep(); b._retention_sweep()
    assert calls==[1]
