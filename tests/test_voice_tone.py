import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FR-1500-008/009/010, FR-1600-006 (2026-10-02): tone reaches synthesis; safety text is
# forced neutral; compliments and personal questions trigger the bashful tone.

_REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT='''
import queue,types
import voice
from voice import VoicePipeline,_BASHFUL_TRIGGER,_TONE_LENGTH_SCALE
v=VoicePipeline.__new__(VoicePipeline)
v._enabled=True; v.display=None; v._utterance_timing=None; v._speak_queue=queue.Queue()
v.speak("Hello there",tone="silly")
assert v._speak_queue.get_nowait()==("Hello there",None,"silly")
v.speak("Obstacle detected ahead",tone="silly")
assert v._speak_queue.get_nowait()[2]=="neutral"      # FR-1500-010
v.speak_safety("Stopping")
assert v._speak_queue.get_nowait()==("Stopping",None,"neutral")
assert _TONE_LENGTH_SCALE["neutral"]==1.0 and _TONE_LENGTH_SCALE["bashful"]>1.0
for t in ("good boy","you're so cute","How old are you?","well done Willie"):
    assert _BASHFUL_TRIGGER.search(t), t
for t in ("go to the kitchen","what time is it","stop"):
    assert not _BASHFUL_TRIGGER.search(t), t
print("TONE_OK")
'''

def test_tone_reaches_synthesis_and_bashful_triggers():
    env=dict(os.environ,WILLY_SIMULATE='1',PYTHONPATH=_REPO_ROOT)
    r=subprocess.run([sys.executable,'-c',_SCRIPT],capture_output=True,text=True,cwd=_REPO_ROOT,env=env,timeout=120)
    assert 'TONE_OK' in r.stdout, r.stdout+r.stderr
