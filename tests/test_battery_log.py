import os,sys,csv
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config,battery_log

# Battery log (2026-10-13): every 2 h to a CSV; publish, and retry while offline.

class Clock:
    def __init__(self,t=1_000_000.0): self.t=t
    def __call__(self): return self.t

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_LOG_ROOT',str(tmp_path))
    clk=Clock(); results=[]
    def publish(path): results.append(path); return publish.ok
    publish.ok=False
    lg=battery_log.BatteryLogger(lambda:{'volts':11.64,'percent':35,'bus_volts':11.48,'bus_amps':0.02},
                                 clock=clk,publish=publish,start_thread=False)
    return lg,clk,publish,results,tmp_path

def test_records_every_interval_and_offline_waits_for_the_next_cycle(setup):
    lg,clk,publish,results,tmp=setup
    lg.tick(); assert not os.path.exists(tmp/config.BATTERY_LOG_CSV)          # not yet due
    clk.t+=config.BATTERY_LOG_FIRST_S; lg.tick()
    rows=list(csv.DictReader(open(tmp/config.BATTERY_LOG_CSV)))
    assert len(rows)==1 and rows[0]['volts']=='11.64' and rows[0]['percent']=='35'
    assert len(results)==1                                                     # tried once, offline
    clk.t+=config.BATTERY_LOG_INTERVAL_S-1; lg.tick(); assert len(results)==1   # no retry
    publish.ok=True
    clk.t+=1; lg.tick()
    assert len(results)==2 and len(list(csv.DictReader(open(tmp/config.BATTERY_LOG_CSV))))==2

def test_hours_on_charge_resets_when_the_voltage_jumps(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_LOG_ROOT',str(tmp_path))
    v=[12.5]; clk=Clock()
    lg=battery_log.BatteryLogger(lambda:{'volts':v[0],'percent':90},clock=clk,publish=lambda p:True,start_thread=False)
    clk.t+=3600; assert lg.record(clk.t)['hours_on_charge']==0               # first ever: starts the count
    clk.t+=7200; v[0]=12.2; assert lg.record(clk.t)['hours_on_charge']==2.0   # ran straight through
    clk.t+=86400                                                             # switched off a day...
    lg2=battery_log.BatteryLogger(lambda:{'volts':12.1,'percent':80},clock=clk,publish=lambda p:True,start_thread=False)
    clk.t+=120; assert lg2.record(clk.t)['hours_on_charge']==2.03             # ...only the 2 min since boot count
    clk.t+=7200; v[0]=12.55; assert lg.record(clk.t)['hours_on_charge']==0   # charged

def test_publish_ha_without_a_token_is_inert(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'GOOGLE_HOME_CREDS_PATH',str(tmp_path/'none.json'))
    assert battery_log.publish_ha({'volts':11.6,'percent':35}) is False
