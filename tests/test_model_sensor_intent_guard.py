import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest

# 2026-10-10, live: the Hailo model mapped "Why is the grass green?" to where_are_you (0.8) and
# Willie answered with his room. A model-picked sensor intent needs one of its own words.

def _v(intent):
    import voice
    from ai_provider import AIResult
    v=object.__new__(voice.VoicePipeline)
    v._local_ai=types.SimpleNamespace(ask_sync=lambda p,schema=None: AIResult(True,0.8,None,True,{'intent':intent,'args':{},'reply':''},''))
    v.memory=None
    return v

@pytest.mark.parametrize('text,intent',[('Why is the grass green?','where_are_you'),
                                        ('Tell me a joke','battery'),('What is two plus two','what_do_you_see')])
def test_unbacked_sensor_intent_is_not_understood(text,intent):
    payload,conf=_v(intent)._interpret_local(text)
    assert conf==0.0

@pytest.mark.parametrize('text,intent',[('which room are you in','where_are_you'),
                                        ('is your battery okay','battery'),('what are you looking at over there','what_do_you_see')])
def test_backed_sensor_intent_passes(text,intent):
    payload,conf=_v(intent)._interpret_local(text)
    assert conf==0.8
