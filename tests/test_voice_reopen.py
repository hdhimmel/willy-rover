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
