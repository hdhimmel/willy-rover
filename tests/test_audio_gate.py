import os,sys,types,struct
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config

# 2026-10-11 CPU: the wake-word model runs only while there is sound; quiet blocks wait in a
# pre-roll that is scored first at onset, so the start of the wake word is never lost.

class Clock:
    def __init__(self): self.t=0.0
    def __call__(self): return self.t

def _g(clock): 
    import audio_gate
    return audio_gate.WakeGate(preroll_blocks=3,hang_s=1.0,margin=2.0,floor=0.002,clock=clock)

def test_quiet_blocks_are_not_scored():
    c=Clock(); g=_g(c)
    for i in range(10):
        out,reset=g.feed(f'q{i}',0.001,0.001); c.t+=0.08
        assert out==[] and not reset
    assert g.skipped==10

def test_onset_replays_the_preroll_after_a_reset():
    c=Clock(); g=_g(c)
    for i in range(5): g.feed(f'q{i}',0.001,0.001); c.t+=0.08
    out,reset=g.feed('loud',0.05,0.001)
    assert reset and out==['q2','q3','q4','loud']      # last 3 quiet blocks, then the onset block

def test_hang_keeps_scoring_after_the_sound_stops_then_closes():
    c=Clock(); g=_g(c)
    g.feed('loud',0.05,0.001); c.t+=0.5
    out,reset=g.feed('tail',0.001,0.001)
    assert out==['tail'] and not reset                  # inside the hang
    c.t+=1.0
    assert g.feed('quiet',0.001,0.001)==([],False)      # hang over

def test_threshold_follows_the_noise_floor_and_vad_overrides():
    c=Clock(); g=_g(c)
    assert not g.sound(0.015,0.01)                      # under 2x a noisy floor
    assert g.sound(0.025,0.01)
    assert g.sound(0.0001,0.01,vad=1) and not g.sound(0.5,0.01,vad=0)

def test_pick_input_prefers_a_respeaker_at_16k():
    import audio_gate
    devs=[{'name':'USB PnP Sound Device','max_input_channels':1},
          {'name':'ReSpeaker 4 Mic Array (UAC1.0)','max_input_channels':6}]
    assert audio_gate.pick_input(devs)==('ReSpeaker 4 Mic Array (UAC1.0)',16000,'array')
    assert audio_gate.pick_input(devs[:1])==(config.AUDIO_INPUT_DEVICE,int(config.AUDIO_INPUT_RATE),'mic')

def test_respeaker_vad_read_and_failure():
    import audio_gate
    calls=[]
    def ctrl(rt,req,val,idx,ln,to): calls.append((rt,req,val,idx,ln)); return struct.pack('<ii',1,0)
    v=audio_gate.ReSpeakerVAD(dev=types.SimpleNamespace(ctrl_transfer=ctrl))
    assert v.read()==1 and calls[0]==(0xC0,0,0x80|32|0x40,19,8)
    def boom(*a): raise OSError('unplugged')
    v2=audio_gate.ReSpeakerVAD(dev=types.SimpleNamespace(ctrl_transfer=boom))
    assert v2.read() is None and not v2.present        # falls back to the energy gate
