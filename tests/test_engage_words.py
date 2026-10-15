# tests/test_engage_words.py
import os,sys,time,types,threading
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config,engage_words as ew
from ai_provider import AIResult

def T(kind,facts,question=False): return types.SimpleNamespace(kind=kind,subject='s',facts=facts,question=question,bearing_deg=None)

def cloud(reply=None,delay=0.0,available=True,raises=False):
    def ask_sync(prompt,system=None,schema=None):
        time.sleep(delay)
        if raises: raise RuntimeError('net')
        return reply
    return types.SimpleNamespace(available=available,ask_sync=ask_sync)

def test_when_words():
    now=time.mktime((2026,10,15,15,0,0,0,0,-1))
    assert ew.when_words(now-60,now)=='just now'
    assert ew.when_words(time.mktime((2026,10,15,9,0,0,0,0,-1)),now)=='this morning'
    assert ew.when_words(time.mktime((2026,10,14,20,0,0,0,0,-1)),now)=='yesterday evening'
    assert ew.when_words(now-3*86400,now)=='3 days ago'

def test_template_fills_facts_and_skips_missing_fields():
    assert ew.template(T('ask_thing',{'thing':'ball'}))=='Whose ball is that?'
    assert ew.template(T('greet_known',{'name':'Howard','when':'this morning'},),n=0)=='Hi Howard!'
    t=T('callback',{'about':'thing','label':"Storm's ball",'when':'yesterday'})
    assert ew.template(t)=="There's Storm's ball. I last saw it yesterday."

def test_line_uses_the_cloud():
    r=AIResult(True,1.0,None,True,'  Hey Howard, nice to see you!  ','')
    assert ew.line(T('greet_known',{'name':'Howard'}),cloud(r))=='Hey Howard, nice to see you!'

def test_bad_cloud_lines_fall_back():
    t=T('ask_thing',{'thing':'ball'},question=True)
    for payload in ('','x'*500,'{"intent":"chat"}',"I'm sorry, I can't help with that."):
        assert ew.line(t,cloud(AIResult(True,1.0,None,True,payload,'')))=='Whose ball is that?'
    assert ew.line(t,cloud(raises=True))=='Whose ball is that?'
    assert ew.line(t,cloud(available=False))=='Whose ball is that?'
    assert ew.line(t,None)=='Whose ball is that?'

def test_line_slow_cloud_times_out():
    t=T('ask_room',{},question=True)
    t0=time.time(); out=ew.line(t,cloud(AIResult(True,1.0,None,True,'Late.',''),delay=2.0),timeout_s=0.2)
    assert time.time()-t0<1.0 and out in config.ENGAGE_TEMPLATES['ask_room']

def test_extract_from_cloud():
    t=T('ask_thing',{'thing':'sports ball'},question=True)
    r=AIResult(True,0.9,None,True,{'label':"Storm's ball",'owner':'Storm'},'')
    assert ew.extract(t,"It's Storm's",cloud(r))=={'label':"Storm's ball",'owner':'Storm'}

def test_extract_offline_patterns():
    off=cloud(available=False)
    assert ew.extract(T('greet_stranger',{},True),"My name is Alice.",off)=={'name':'Alice'}
    assert ew.extract(T('greet_stranger',{},True),"Bob",off)=={'name':'Bob'}
    assert ew.extract(T('ask_room',{},True),"This is the kitchen.",off)=={'room':'kitchen'}
    assert ew.extract(T('ask_room',{},True),"Living room",off)=={'room':'living room'}
    assert ew.extract(T('ask_thing',{'thing':'sports ball'},True),"It's Storm's.",off)=={'owner':'Storm','label':"Storm's sports ball"}
    assert ew.extract(T('ask_person',{'name':'Howard'},True),"Pretty busy, fixing the arm.",off)=={'note':'pretty busy, fixing the arm'}

def test_extract_unusable_is_none():
    off=cloud(available=False)
    assert ew.extract(T('greet_stranger',{},True),"",off) is None
    assert ew.extract(T('greet_stranger',{},True),"I don't know what you mean by that",off) is None
    assert ew.extract(T('ask_room',{},True),"No.",off) is None
