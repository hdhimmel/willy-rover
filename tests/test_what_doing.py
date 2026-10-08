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

def test_how_is_your_battery_is_a_fixed_phrase():
    import voice
    r=voice.VoicePipeline._fast_path(None,"How is your battery?")
    assert r and r['intent']=='battery'

def test_the_model_never_answers_a_sensor_question_itself():
    """2026-10-08: the model's own reply "I am at 80%" was spoken before the real "I can't read
    my battery right now". Its reply text is dropped for sensor-answered intents."""
    import queue, voice
    v=object.__new__(voice.VoicePipeline)
    said=[]; v.speak=lambda text,tone='neutral': said.append(text)
    v.pending_commands=queue.Queue(); v.smart_home=None; v._reply_tone='neutral'
    v.stop_requested=type('E',(),{'set':lambda self:None})()
    v._act_on_intent({'intent':'battery','args':{},'reply':'I am at 80%'},'how is your battery')
    assert said==[] and v.pending_commands.get_nowait()['intent']=='battery'
    v._act_on_intent({'intent':'battery','args':{},'reply':'Checking.'},'hows your battery')
    assert said==['Checking.']

def test_phrasings_the_model_got_wrong_are_fixed_phrases_now():
    """2026-10-08 Hailo qualification: these reached the model and came back wrong or unparseable
    ("say hi to them" once became come_here -- motion). Now deterministic."""
    import voice
    fp=lambda t: (voice.VoicePipeline._fast_path(None,t) or {}).get('intent')
    assert fp("would you power yourself off now")=='shutdown'      # still asks to confirm
    assert fp("do you have much juice left")=='battery'
    assert fp("put that arm away for me")=='arm_stow'
    assert fp("go ahead and say hi to them")=='wave'
    assert fp("are you doing okay buddy")=='status'
    for t in ("don't power yourself off","say hi to grandma tomorrow","put that arm away later maybe"):
        assert fp(t) is None, t                                       # near-misses still go to the model

def test_failing_self_test_beats_starting_up():
    """Live 2026-10-08 on Pi-only power: state stays INIT, and he said "I'm just starting up"."""
    assert 'self-test' in _b('INIT',_motion_enabled=False)._activity_phrase()
    assert _b('INIT')._activity_phrase()=="I'm just starting up."

def test_backlog_is_dropped_and_wake_model_reset():
    import queue,types,voice
    v=object.__new__(voice.VoicePipeline)
    v._audio_q=queue.Queue()
    for _ in range(5): v._audio_q.put(b'x')
    resets=[]; v._wakeword=types.SimpleNamespace(reset=lambda: resets.append(1))
    v._drop_backlog()
    assert v._audio_q.empty() and resets==[1]
