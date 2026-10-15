import os,sys,threading,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import voice

# 2026-10-15: one stalled capture ("no audio from the capture callback for 2 s") stopped the voice
# pipeline at 11:26 and Willie was deaf until restarted. A failed stream must be reopened.


def test_a_failed_mic_stream_is_reopened(monkeypatch):
    monkeypatch.setattr(config,'VOICE_REOPEN_MAX_S',0.01)
    p=object.__new__(voice.VoicePipeline)
    p._running=True
    calls=[]
    def capture():
        calls.append(time.time())
        if len(calls)>=3: p._running=False   # third open "works" until stop()
    p._capture=capture
    t=threading.Thread(target=p._loop,daemon=True); t.start(); t.join(timeout=5)
    assert not t.is_alive()
    assert len(calls)==3


def test_stop_ends_the_loop_without_reopening(monkeypatch):
    p=object.__new__(voice.VoicePipeline)
    p._running=True
    calls=[]
    def capture():
        calls.append(1); p._running=False
    p._capture=capture
    p._loop()
    assert calls==[1]


def test_the_listening_circle_is_on_for_the_whole_capture_and_off_after():
    import types
    p=object.__new__(voice.VoicePipeline)
    seen=[]
    p.display=types.SimpleNamespace(update_state=lambda **k: None,set_listening=seen.append)
    def capture(stream,frame_len,t_wake,on_text,*rest): seen.append('capturing')
    p._capture_utterance=capture
    p._handle_wake(None,1280,0.0)
    assert seen==[True,'capturing',False]


def test_the_listening_circle_goes_off_even_if_capture_fails():
    import types
    p=object.__new__(voice.VoicePipeline)
    seen=[]
    p.display=types.SimpleNamespace(update_state=lambda **k: None,set_listening=seen.append)
    def capture(*a): raise RuntimeError('mic')
    p._capture_utterance=capture
    try: p._handle_wake(None,1280,0.0)
    except RuntimeError: pass
    assert seen[-1] is False
