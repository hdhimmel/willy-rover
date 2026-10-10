import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config

# FR-1800-005 (2026-10-08): privacy ON by voice ("privacy mode", "stop listening", "turn off your
# microphone/camera"); OFF by the screen's two-tap RESUME or an owner email -- not by voice,
# because with the microphone off he cannot hear.

def test_phrases():
    import voice
    fp=lambda t: (voice.VoicePipeline._fast_path(None,t) or {}).get('intent')
    for t in ("Willie, privacy mode","stop listening","turn off your microphone and camera","go private"):
        assert fp(t)=='privacy_on', t
    for t in ("privacy off","resume listening","turn back on your camera"):
        assert fp(t)=='privacy_off', t
    assert fp("don't stop listening") is None

def test_the_flag_turns_both_off_and_back_on(tmp_path,monkeypatch):
    import privacy
    monkeypatch.setattr(privacy,'_flag_path',lambda: str(tmp_path/'privacy.flag'))
    assert privacy.mic_enabled() and privacy.camera_enabled()
    privacy.disable_mic_camera('voice command')
    assert not privacy.mic_enabled() and not privacy.camera_enabled()
    privacy.enable_mic_camera()
    assert privacy.mic_enabled() and privacy.camera_enabled()

def test_screen_resume_needs_two_taps(monkeypatch):
    os.environ['SDL_VIDEODRIVER']='dummy'
    import display
    d=object.__new__(display.WillyFace)
    import threading,pygame
    d._lock=threading.Lock(); d._t=10.0; d._privacy_on=True; d._privacy_armed_until=0.0
    d._privacy_event=threading.Event(); d._privacy_button_rect=pygame.Rect(0,0,100,100)
    d._handle_privacy_tap(50,50); assert not d.privacy_resume_tapped()        # first tap arms
    d._handle_privacy_tap(50,50); assert d.privacy_resume_tapped()            # second tap fires
    d._handle_privacy_tap(50,50); d._handle_privacy_tap(500,500)              # tap elsewhere cancels
    d._handle_privacy_tap(50,50); assert not d.privacy_resume_tapped()
    d._privacy_on=False; d._handle_privacy_tap(50,50); d._handle_privacy_tap(50,50)
    assert not d.privacy_resume_tapped()                                      # inert when privacy is off

def test_privacy_on_is_answered_even_while_moving_and_by_email():
    import brain
    assert 'privacy_on' in brain._SPEECH_ONLY_INTENTS
    assert {'privacy_on','privacy_off'} <= brain._EMAIL_QUEUEABLE


def test_cloud_send_says_a_thinking_phrase_and_still_shows_the_notice():
    # 2026-10-10 (owner): no "checking with a cloud service" out loud; the display keeps the
    # FR-1800-003 notice.
    import privacy
    said=[]; shown=[]
    voice=types.SimpleNamespace(speak=lambda t,**k: said.append(t))
    display=types.SimpleNamespace(update_state=lambda **k: shown.append(k.get('status','')))
    privacy.note_cloud_send(display,voice,'your question')
    assert said and said[0] in config.CLOUD_THINKING_PHRASES and 'cloud' not in said[0].lower()
    assert shown and 'cloud AI' in shown[0]
