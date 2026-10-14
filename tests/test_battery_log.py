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

def test_hours_on_charge_counts_running_time_across_restarts(tmp_path,monkeypatch):
    # 2026-10-14: restarts every few minutes used to add only 2 min each (0.83 h logged for ~6.7 h)
    monkeypatch.setattr(config,'WILLY_LOG_ROOT',str(tmp_path))
    v=[12.5]; clk=Clock()
    def run(minutes,volts):
        v[0]=volts
        lg=battery_log.BatteryLogger(lambda:{'volts':v[0],'percent':90},clock=clk,publish=lambda p:True,start_thread=False)
        for _ in range(minutes): clk.t+=60; lg.tick()
        return lg
    lg=run(1,12.5); assert lg.record(clk.t)['hours_on_charge']==0           # first ever: starts the count
    run(30,12.4); run(30,12.3)                                                # two half-hour runs...
    clk.t+=86400                                                              # ...switched off a day...
    lg=run(60,12.2)
    assert lg.record(clk.t)['hours_on_charge']==2.0                           # 1+30+30+60 min, not the day off
    v[0]=12.6; assert lg.record(clk.t)['hours_on_charge']==0                  # charged

def test_a_restart_does_not_write_its_own_row(setup):
    lg,clk,publish,results,tmp=setup
    clk.t+=config.BATTERY_LOG_FIRST_S; lg.tick()
    lg2=battery_log.BatteryLogger(lambda:{'volts':11.6,'percent':34},clock=clk,publish=lambda p:True,start_thread=False)
    for _ in range(10): clk.t+=60; lg2.tick()
    assert len(list(csv.DictReader(open(tmp/config.BATTERY_LOG_CSV))))==1       # no row 2 min after restart
    clk.t+=config.BATTERY_LOG_INTERVAL_S; lg2.tick()
    assert len(list(csv.DictReader(open(tmp/config.BATTERY_LOG_CSV))))==2

def test_publish_ha_without_a_token_is_inert(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'GOOGLE_HOME_CREDS_PATH',str(tmp_path/'none.json'))
    assert battery_log.publish_ha({'volts':11.6,'percent':35}) is False
