# tests/test_engage.py
import os,sys,time,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import config
from engage import Engagement,FaceSeen,Topic,bearing_of
from identity import RECOGNISED,UNCERTAIN,UNKNOWN
from memory_store import MemoryStore

T0=time.mktime((2026,10,15,10,0,0,0,0,-1))
P=types.SimpleNamespace(x=1.0,y=2.0)

class Clock:
    def __init__(self,t=T0): self.t=t
    def __call__(self): return self.t

def det(cls,cx=0.5): return {'class':cls,'bbox':(cx*1280-20,300,cx*1280+20,400),'frame_w':1280,'frame_h':720}
def me(name='Howard',bearing=0.0): return FaceSeen(RECOGNISED,name,bearing)
def stranger(): return FaceSeen(UNKNOWN,None,5.0)

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    clk=Clock(); m=MemoryStore('e.db')
    return Engagement(m,clock=clk),m,clk

def tick(e,state='IDLE',dets=(),faces=None,room=None,busy=False,prev=None):
    return e.tick(state,list(dets),faces,P,room,busy,prev or {})

def test_bearing_of():
    assert bearing_of(det('cup',0.5))==pytest.approx(0.0)
    assert bearing_of(det('cup',0.0))==pytest.approx(config.CAM_FRONT_HFOV_DEG/2)    # left edge = +
    assert bearing_of(det('cup',1.0))==pytest.approx(-config.CAM_FRONT_HFOV_DEG/2)

def test_greets_a_known_person_once_per_visit(env):
    e,m,clk=env
    t=tick(e,faces=[me()])
    assert t.kind=='greet_known' and t.facts['name']=='Howard' and not t.question
    clk.t+=60; assert tick(e,faces=[me()]) is None                       # same visit
    clk.t+=config.ENGAGE_VISIT_S+1; assert tick(e,faces=[me()]).kind=='greet_known'   # new visit

def test_greet_once_after_restart(env,tmp_path):
    e,m,clk=env
    assert tick(e,faces=[me()]).kind=='greet_known'
    e2=Engagement(m,clock=clk); clk.t+=5
    assert tick(e2,faces=[me()]).kind=='greet_known'                     # one greeting, not a storm
    clk.t+=5; assert tick(e2,faces=[me()]) is None

def test_greeting_mentions_last_time_when_long_ago(env):
    e,m,clk=env
    t=tick(e,faces=[me()],prev={'saw:Howard':T0-5*3600})
    assert t.facts.get('about')=='back' and t.facts['when']

def test_two_known_faces_greeted_one_per_tick(env):
    e,m,clk=env
    both=[me('Howard'),me('Carolyn')]
    a=tick(e,faces=both); b=tick(e,faces=both); c=tick(e,faces=both)
    assert {a.facts['name'],b.facts['name']}=={'Howard','Carolyn'} and c is None

def test_stranger_needs_three_scans_and_is_asked_once(env):
    e,m,clk=env
    assert tick(e,faces=[stranger()],room='den') is None
    assert tick(e,faces=[stranger()],room='den') is None
    t=tick(e,faces=[stranger()],room='den')
    assert t.kind=='greet_stranger' and t.question
    for _ in range(5): assert tick(e,faces=[stranger()],room='den') is None
    assert tick(e,faces=None,room='den') is None                                    # no new scan: no change

def test_uncertain_face_is_silent(env):
    e,m,clk=env
    for _ in range(5): assert tick(e,faces=[FaceSeen(UNCERTAIN,'Howard',0.0)],room='den') is None

def test_nothing_in_other_states_or_when_busy(env):
    e,m,clk=env
    for st in ('AVOID','STUCK','RETRIEVE','WAVE','ROTATE','ENGAGE'):
        assert tick(e,state=st,faces=[me()]) is None
    assert tick(e,faces=[me()],busy=True) is None
    assert tick(e,state='ROAM',faces=[me()]).kind=='greet_known'

def test_no_person_no_questions(env):
    e,m,clk=env
    assert tick(e,dets=[det('sports ball')]) is None
    t=tick(e,dets=[det('sports ball',0.2),det('person')])
    assert t.kind in ('ask_room','ask_thing')

def test_ask_room_in_an_unnamed_spot_once_an_hour(env):
    e,m,clk=env
    t=tick(e,dets=[det('person')])
    assert t.kind=='ask_room' and t.question
    clk.t+=config.ENGAGE_GAP_S+1; assert tick(e,dets=[det('person')]) is None
    clk.t+=config.ENGAGE_ASK_ROOM_GAP_S
    assert e.tick('IDLE',[det('person')],None,types.SimpleNamespace(x=4.0,y=2.0),None,False,{}).kind=='ask_room'

def test_ask_thing_then_gap_then_no_repeat_today(env):
    e,m,clk=env
    t=tick(e,dets=[det('sports ball',0.2),det('person')],room='kitchen')
    assert t.kind=='ask_thing' and t.facts['thing']=='sports ball' and t.question
    assert t.bearing_deg==pytest.approx(bearing_of(det('sports ball',0.2)))
    clk.t+=10; assert tick(e,dets=[det('cup'),det('person')],room='kitchen') is None   # 5-min gap
    clk.t+=config.ENGAGE_GAP_S
    assert tick(e,dets=[det('cup'),det('person')],room='kitchen').facts['thing']=='cup'
    clk.t+=config.ENGAGE_GAP_S+1
    assert tick(e,dets=[det('sports ball'),det('person')],room='kitchen') is None      # said today

def test_a_named_thing_is_not_asked_about(env):
    e,m,clk=env
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball")
    assert tick(e,dets=[det('sports ball'),det('person')],room='kitchen') is None

def test_said_today_resets_at_midnight(env):
    e,m,clk=env
    clk.t=time.mktime((2026,10,15,23,59,0,0,0,-1))
    assert tick(e,dets=[det('cup'),det('person')],room='den').kind=='ask_thing'
    clk.t=time.mktime((2026,10,16,0,6,0,0,0,-1))
    assert tick(e,dets=[det('cup'),det('person')],room='den').kind=='ask_thing'

def test_callback_for_a_named_thing_back_after_hours(env):
    e,m,clk=env
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball",at=T0-6*3600)
    t=tick(e,dets=[det('sports ball'),det('person')],room='kitchen',
           prev={'thing:sports ball@kitchen':T0-6*3600})
    assert t.kind=='callback' and t.facts['about']=='thing' and t.facts['label']=="Storm's ball"

def test_callback_for_a_note_about_a_greeted_person(env):
    e,m,clk=env
    m.add_person_note('Howard','were fixing the arm',at=T0-86400)
    assert tick(e,faces=[me()],room='den').kind=='greet_known'
    clk.t+=config.ENGAGE_GAP_S+1
    t=tick(e,faces=[me()],room='den')
    assert t.kind=='callback' and t.facts['about']=='note' and 'arm' in t.facts['note']

def test_change_new_here(env):
    e,m,clk=env
    m.name_thing('backpack','hall',None,'the blue backpack',at=T0-86400)
    t=tick(e,dets=[det('backpack'),det('person')],room='kitchen',prev={'thing:backpack@kitchen':None})
    assert t.kind=='change' and t.facts['about']=='new' and t.facts['room']=='kitchen'

def test_change_missing_needs_time_in_the_room(env):
    e,m,clk=env
    m.name_thing('sports ball','kitchen','Storm',"Storm's ball",at=T0-8*3600)
    assert tick(e,dets=[det('person')],room='kitchen') is None           # just arrived
    clk.t+=config.ENGAGE_LOOK_ROOM_S+1
    t=tick(e,dets=[det('person')],room='kitchen')
    assert t.kind=='change' and t.facts['about']=='missing' and t.facts['label']=="Storm's ball"

def test_ask_person_after_greeting(env):
    e,m,clk=env
    tick(e,faces=[me()],room='den')
    clk.t+=config.ENGAGE_ASK_PERSON_AFTER_S-1; assert tick(e,faces=[me()],room='den') is None
    clk.t+=config.ENGAGE_GAP_S
    t=tick(e,faces=[me()],room='den')
    assert t.kind=='ask_person' and t.question and t.facts['name']=='Howard'

def test_greeting_ignores_the_gap(env):
    e,m,clk=env
    assert tick(e,dets=[det('cup'),det('person')],room='den').kind=='ask_thing'
    clk.t+=5; assert tick(e,faces=[me()]).kind=='greet_known'

def test_gated_tick_does_not_swallow_a_new_visit(env):
    e,m,clk=env
    assert tick(e,faces=[me()]).kind=='greet_known'
    clk.t+=2*3600; assert tick(e,state='AVOID',faces=[me()]) is None
    clk.t+=5; assert tick(e,faces=[me()]).kind=='greet_known'

def test_greeting_starts_the_gap(env):
    e,m,clk=env
    assert tick(e,faces=[me()],room='den').kind=='greet_known'
    clk.t+=5; assert tick(e,dets=[det('cup'),det('person')],room='den') is None
    clk.t+=config.ENGAGE_GAP_S; assert tick(e,dets=[det('cup'),det('person')],room='den').kind=='ask_thing'

def test_stranger_run_survives_a_no_scan_tick(env):
    e,m,clk=env
    assert tick(e,faces=[stranger()],room='den') is None
    assert tick(e,faces=[stranger()],room='den') is None
    assert tick(e,faces=None,room='den') is None
    assert tick(e,faces=[stranger()],room='den').kind=='greet_stranger'
