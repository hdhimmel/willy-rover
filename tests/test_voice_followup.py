import os,sys,queue,threading,time,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import config,voice

# 2026-10-15 (owner): in a conversation, after his reply he listens again without "Hey Willie".

def _p():
    p=object.__new__(voice.VoicePipeline)
    p._speak_queue=queue.Queue(); p._speaking=threading.Event(); p.stop_requested=threading.Event()
    p._prompt=None; p._noise_rms=0.002; p.display=None
    p.handled=[]
    p._handle_wake=lambda stream,fl,t,on_text=None,preroll=None,quiet_empty=False: p.handled.append((len(preroll or []),quiet_empty))
    p._drop_backlog=lambda: None
    return p

QUIET=np.zeros(1280,dtype=np.int16)
LOUD=(np.ones(1280)*3000).astype(np.int16)

def test_armed_after_an_answer_not_after_stop_or_a_question():
    p=_p(); p._last_heard='what time is it'; p._arm_followup()
    assert p._followup=={'until':None}
    p=_p(); p._last_heard='stop'; p._arm_followup(); assert getattr(p,'_followup',None) is None
    p=_p(); p._last_heard='hello'; p._prompt={'cb':None}; p._arm_followup(); assert getattr(p,'_followup',None) is None
    p=_p(); p._last_heard=None; p._arm_followup(); assert getattr(p,'_followup',None) is None

def test_off_when_zero(monkeypatch):
    monkeypatch.setattr(config,'VOICE_FOLLOWUP_S',0)
    p=_p(); p._last_heard='hello'; p._arm_followup(); assert getattr(p,'_followup',None) is None

def test_speech_in_the_window_is_handled_with_preroll_and_quietly():
    p=_p(); p._followup={'until':None}
    for _ in range(3): assert p._followup_step(None,1280,QUIET) is False
    assert p._followup_step(None,1280,LOUD) is False          # one loud block is not enough
    assert p._followup_step(None,1280,LOUD) is True
    assert p.handled==[(5,True)] and p._followup is None

def test_window_closes_after_its_time(monkeypatch):
    p=_p(); p._followup={'until':None}
    p._followup_step(None,1280,QUIET)
    p._followup['until']=time.time()-0.01
    assert p._followup_step(None,1280,LOUD) is False and p._followup is None and not p.handled

def test_waits_while_the_reply_is_queued_and_yields_to_a_question():
    p=_p(); p._followup={'until':None}; p._speak_queue.put('reply')
    assert p._followup_step(None,1280,LOUD) is False and p._followup['until'] is None
    p._speak_queue.get(); p._prompt={'cb':None}
    assert p._followup_step(None,1280,LOUD) is False and p._followup is None

def test_busy_while_the_window_is_open():
    p=_p(); p._in_utterance=False; p._followup={'until':None}
    assert p.busy
    p._followup=None; assert not p.busy
