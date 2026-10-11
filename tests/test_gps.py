import os,sys,types,json
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# FR-2300 GPS (2026-10-11). Real sentences captured from Willie's PA1010D in the basement (no fix),
# plus synthetic ones with a fix (checksums computed, so they pass the same validation).

REAL_NOFIX=[b'$GNRMC,000035.869,V,,,,,0.00,0.00,060180,,,N*5D\r\n',
            b'$GNGGA,000036.869,,,,,0,0,,,M,,M,,*54\r\n',b'$GPGSA,A,1,,,,,,,,,,,,,,,*1E\r\n']

def _s(body):
    x=0
    for ch in body: x^=ord(ch)
    return f'${body}*{x:02X}\r\n'.encode()

def _fix_lines(lat='4042.7666',ns='N',lon='07400.3584',ew='W',sats=8,hdop=0.9):
    return [_s(f'GNRMC,153000.000,A,{lat},{ns},{lon},{ew},0.00,0.00,111026,,,A'),
            _s(f'GNGGA,153000.000,{lat},{ns},{lon},{ew},1,{sats},{hdop},10.0,M,,M,,')]

class Clock:
    def __init__(self,t=1000.0): self.t=t
    def __call__(self): return self.t

def _gps(tmp_path,monkeypatch,clock=None):
    import gps
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    return gps.GPS(start=False,clock=clock or Clock())

def test_checksum_and_parse_of_real_no_fix_output():
    import gps
    assert all(gps.nmea_ok(l.decode().strip()) for l in REAL_NOFIX)
    assert not gps.nmea_ok('$GNRMC,000035.869,V,,,,,0.00,0.00,060180,,,N*00')
    r=gps.parse(REAL_NOFIX[0].decode().strip())
    assert r['kind']=='RMC' and r['valid'] is False and r['lat'] is None

def test_no_fix_is_present_but_has_no_position(tmp_path,monkeypatch):
    g=_gps(tmp_path,monkeypatch)
    for l in REAL_NOFIX: g.feed(l)
    assert g.present and g.fix() is None

def test_a_fix_is_parsed_and_goes_stale(tmp_path,monkeypatch):
    clk=Clock(); g=_gps(tmp_path,monkeypatch,clk)
    for l in _fix_lines(): g.feed(l)
    f=g.fix()
    assert f['lat']==pytest.approx(40.712777,abs=1e-5) and f['lon']==pytest.approx(-74.005973,abs=1e-5)
    assert f['sats']==8 and f['hdop']==0.9
    clk.t+=config.GPS_STALE_S+1
    assert g.fix() is None                         # never a stale position as current

def test_split_chunks_and_padding_are_reassembled(tmp_path,monkeypatch):
    g=_gps(tmp_path,monkeypatch)
    raw=b''.join(_fix_lines())
    for i in range(0,len(raw),32): g.feed(raw[i:i+32])           # 32-byte reads split sentences
    g.feed(b'\n'*32)                                              # nothing more: 0x0A padding
    assert g.fix() is not None

def test_relative_phrase_and_map_link():
    import gps
    home={'lat':40.0,'lon':-74.0}
    north={'lat':40.0+30/111195,'lon':-74.0}
    assert gps.relative_phrase(north,home)=='about 30 metres north of home'
    assert gps.relative_phrase(home,home)=='at home'
    assert gps.map_link(40.0,-74.0)=='https://maps.google.com/?q=40.000000,-74.000000'

def test_wander_alert_is_debounced_repeats_and_says_back():
    import gps
    w=gps.WanderWatch(); home={'lat':40.0,'lon':-74.0}
    far={'lat':40.0+200/111195,'lon':-74.0}; near=dict(home)
    t=0.0; evs=[]
    evs.append(w.tick(far,home,t))                 # one wild fix: nothing
    evs.append(w.tick(near,home,t+1))
    assert evs==[None,None]
    out=[w.tick(far,home,t+2+i) for i in range(config.GPS_WANDER_CONFIRM)]
    assert out[-1]=='left' and out[:-1]==[None]*(config.GPS_WANDER_CONFIRM-1)
    assert w.tick(far,home,t+10+config.GPS_ALERT_REPEAT_S)=='update'
    back=[w.tick(near,home,t+1000+i) for i in range(config.GPS_WANDER_CONFIRM)]
    assert back[-1]=='back'
    assert w.tick(None,home,t+2000) is None        # no fix, no events

def test_learn_home_averages_or_refuses(tmp_path,monkeypatch):
    clk=Clock(); g=_gps(tmp_path,monkeypatch,clk)
    def step(_): clk.t+=1.0; [g.feed(l) for l in _fix_lines()]
    res=[]
    import threading
    monkeypatch.setattr(threading,'Thread',lambda target,**k: types.SimpleNamespace(start=target))
    g.learn_home(lambda ok,msg: res.append((ok,msg)),duration_s=30,sleep=step)
    assert res[0][0] and g.home and json.load(open(tmp_path/config.GPS_HOME_PATH))['fixes']>=20
    clk2=Clock(); g2=_gps(tmp_path/'..',monkeypatch,clk2)
    def tick2(_): clk2.t+=1.0                       # time passes, but no fixes arrive
    res2=[]; g2.learn_home(lambda ok,msg: res2.append((ok,msg)),duration_s=5,sleep=tick2)
    assert res2 and not res2[0][0] and 'sky' in res2[0][1]

def test_set_home_script(tmp_path,monkeypatch):
    import importlib
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'scripts'))
    import set_gps_home; importlib.reload(set_gps_home)
    assert set_gps_home.main(['x','40.7128,','-74.0060'])==0
    h=json.load(open(tmp_path/config.GPS_HOME_PATH))
    assert h['lat']==40.7128 and h['source']=='entered'
    assert set_gps_home.main(['x','95','0'])==2

@pytest.mark.parametrize('said,intent',[('this is home','learn_home'),('Willie, this is your home.','learn_home'),
                                        ('go home','go_home'),('head home','go_home')])
def test_phrases(said,intent):
    import voice
    v=object.__new__(voice.VoicePipeline)
    assert v._fast_path(said)['intent']==intent


def test_home_address(tmp_path,monkeypatch):
    import importlib,voice
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'scripts'))
    import set_gps_home; importlib.reload(set_gps_home)
    assert set_gps_home.main(['x','40.7','-74.3','--address','1 Test Lane, Town NJ'])==0
    assert json.load(open(tmp_path/config.GPS_HOME_PATH))['address']=='1 Test Lane, Town NJ'
    v=object.__new__(voice.VoicePipeline)
    for said in ("what's your address","where do you live","what is your home address"):
        assert v._fast_path(said)['intent']=='home_address'


@pytest.mark.parametrize('said',['who is your owner','who are your parents','who owns you','Willie, who do you belong to?'])
def test_owners(said):
    import voice
    v=object.__new__(voice.VoicePipeline)
    r=v._fast_path(said)
    assert r['intent']=='chat' and 'Carolyn and Howard Himmel' in r['reply']
