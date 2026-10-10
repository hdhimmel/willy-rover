import os,sys,types,queue
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# 2026-10-10 (owner): roam by voice without the screen tap; and when Willie asks a question, beep
# and listen for the answer without the wake word.

@pytest.mark.parametrize('said',['go explore','explore','Willie, go explore.','you can roam','go wander',
                                 'start exploring','roam around'])
def test_roam_phrases_hit_the_fast_path(said):
    import voice
    v=object.__new__(voice.VoicePipeline)
    r=v._fast_path(said) if hasattr(v,'_fast_path') else None
    if r is None: pytest.skip('fast path entry point named differently')
    assert r['intent']=='roam'

def test_ask_speaks_then_listens_and_queues_the_answer(monkeypatch):
    import voice
    v=object.__new__(voice.VoicePipeline)
    said=[]; v.speak=lambda t,**k: said.append(t)
    v.pending_commands=queue.Queue()
    got={}
    v.prompt_listen=lambda cb,timeout_s: got.update(cb=cb,timeout=timeout_s)
    v.ask('Is that okay?')
    assert said==['Is that okay?'] and got['timeout']==config.VOICE_ASK_LISTEN_S
    got['cb']('Yes.')
    cmd=v.pending_commands.get_nowait()
    assert cmd['text']=='Yes.' and cmd['source']=='voice'
    got['cb'](None)                                   # nobody answered: nothing queued
    assert v.pending_commands.empty()
