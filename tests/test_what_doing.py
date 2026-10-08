import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')

# Owner 2026-10-07: "what are you doing?" / "what are you looking at?" get a BRIEF answer.

def _b(state,**kw):
    from brain import RoverBrain
    b=types.SimpleNamespace(_state=state,_motion_enabled=True,_manual_action='',
        rotation=types.SimpleNamespace(_dir=1),
        come_to_me=types.SimpleNamespace(state='LEG_NAVIGATE',room='kitchen'),
        pursuit=types.SimpleNamespace(_mode='come_here'),
        navigator=types.SimpleNamespace(_target_room='hall',state='SEEKING'),
        mapping=types.SimpleNamespace(active=False))
    for k,v in kw.items(): setattr(b,k,v)
    b._activity_phrase=types.MethodType(RoverBrain._activity_phrase,b)
    return b

def test_every_state_gets_one_short_sentence():
    for st in ('IDLE','ROAM','SLOW','AVOID','ROTATE','COME_TO_ME','PURSUE','NAVIGATE','MANUAL',
               'WAVE','STUCK','STALL_FAULT','SENSOR_FAULT','TILT_FAULT','SAFE_MODE','SHUTDOWN','INIT','WEIRD'):
        p=_b(st)._activity_phrase()
        assert p and len(p)<=80 and p.count('.')<=2, (st,p)

def test_answers_say_what_and_where():
    assert _b('IDLE')._activity_phrase()=="Nothing much, just waiting."
    assert _b('ROTATE',rotation=types.SimpleNamespace(_dir=-1))._activity_phrase()=="I'm turning right."
    assert 'kitchen' in _b('COME_TO_ME')._activity_phrase()
    b=_b('COME_TO_ME'); b.come_to_me.state='LEG_FIND'
    assert b._activity_phrase()=="I'm looking for you in the kitchen."
    assert _b('MANUAL',_manual_action='reverse')._activity_phrase()=="I'm backing up, like you asked."
    assert 'reset' in _b('STALL_FAULT')._activity_phrase()
    assert 'self-test' in _b('IDLE',_motion_enabled=False)._activity_phrase()
    assert _b('ROAM',mapping=types.SimpleNamespace(active=True))._activity_phrase().endswith('and mapping as I go.')

def test_what_doing_is_answered_even_while_moving():
    import brain
    assert 'what_doing' in brain._SPEECH_ONLY_INTENTS
