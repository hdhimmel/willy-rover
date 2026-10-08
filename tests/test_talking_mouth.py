import os,sys,wave,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import numpy as np
import config

# FR-1600-009 (owner 2026-10-07): "when Willie speaks have his mouth open and close like he is
# talking". The mouth follows the loudness of the audio being played: open on syllables, shut in
# the gaps, closed (normal face) when he is not speaking.

def _wav(samples,rate=22050):
    f=tempfile.NamedTemporaryFile(suffix='.wav',delete=False); f.close()
    with wave.open(f.name,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(np.asarray(samples,dtype=np.int16).tobytes())
    return f.name

def test_envelope_is_shut_in_silence_and_open_on_sound():
    from voice import speech_envelope
    rate=22050; t=np.arange(int(rate*0.3))/rate
    word=(8000*np.sin(2*np.pi*220*t)).astype(np.int16)
    gap=np.zeros(int(rate*0.3),dtype=np.int16)
    path=_wav(np.concatenate([gap,word,gap,word]),rate)
    try:
        env=speech_envelope(path,config.MOUTH_TALK_STEP_S)
    finally:
        os.remove(path)
    n=len(env); q=n//4
    assert n>0
    assert all(v==0.0 for v in env[1:q-1])                    # first gap: closed
    assert max(env[q+1:2*q-1])>0.8                             # first word: open
    assert all(v==0.0 for v in env[2*q+1:3*q-1])              # second gap: closed

def test_a_bad_file_gives_no_envelope_rather_than_an_error():
    from voice import speech_envelope
    assert speech_envelope('/no/such/file.wav',0.05)==[]

def test_mouth_follows_the_envelope_and_closes_after_it():
    from display import mouth_openness
    env=[0.0,0.5,1.0]
    assert mouth_openness(env,0.05,0.00)==0.0
    assert mouth_openness(env,0.05,0.06)==0.5
    assert mouth_openness(env,0.05,0.11)==1.0
    assert mouth_openness(env,0.05,0.16) is None               # finished speaking: normal face
    assert mouth_openness(None,0.05,0.0) is None               # not talking

def test_display_goes_quiet_only_while_transcribing():
    import types
    from voice import VoicePipeline
    calls=[]
    v=object.__new__(VoicePipeline); v.display=types.SimpleNamespace(set_quiet=calls.append)
    with v._display_quiet(): calls.append('transcribe')
    assert calls==[True,'transcribe',False]
    try:
        with v._display_quiet(): raise RuntimeError('whisper')
    except RuntimeError: pass
    assert calls[-1] is False                       # restored even when transcription fails
