import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest

# 2026-10-10 (owner: "the internet retrieval needs to be faster"): plain questions skip the
# on-board model and go straight to the fast cloud chat; commands never do.

@pytest.mark.parametrize('t',['Why is the grass green?','Hey Willie, why is the sky blue?','What is the capital of France?',
                              "What's a black hole?",'How does a rainbow form?','Who wrote Hamlet?','Tell me a joke'])
def test_general_questions(t):
    import voice
    assert voice.general_question(t)

@pytest.mark.parametrize('t',['What do you see?','Why did you stop?','What are you doing?','How is your battery?',
                              'Who is in the kitchen?','What room are you in?','go to the kitchen','turn left',
                              'what is in front of you'])
def test_commands_and_self_questions_are_not(t):
    import voice
    assert not voice.general_question(t)

def test_chat_uses_the_fast_model_and_falls_back(monkeypatch):
    import ai_provider,config,json,io
    p=object.__new__(ai_provider.CloudAIProvider); p._enabled=True; p._key='k'
    sent=[]
    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self,*a): pass
    def ok(req,timeout=None):
        sent.append(json.loads(req.data)); return _R(json.dumps({'content':[{'type':'text','text':'Chlorophyll.'}]}).encode())
    monkeypatch.setattr(ai_provider.urllib.request,'urlopen',ok)
    r=p.chat('Why is the grass green?')
    assert r.parse_success and r.payload=='Chlorophyll.'
    assert sent[0]['model']==config.CLAUDE_CHAT_MODEL and 'output_config' not in sent[0]
    def boom(req,timeout=None): raise TimeoutError('slow')
    monkeypatch.setattr(ai_provider.urllib.request,'urlopen',boom)
    called=[]; monkeypatch.setattr(p,'_call',lambda q,**k: called.append(q) or ai_provider.AIResult(True,1.0,None,True,'x'))
    assert p.chat('q').payload=='x' and called==['q']
