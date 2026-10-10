import json,os,re,queue,subprocess,sys,tempfile,threading,time,numpy as np
import config,logsetup,privacy
from ai_provider import LocalAIProvider
log=logsetup.setup('voice')

_INTENT_SCHEMA={'intent':str,'args':dict,'reply':str}  # §14/§15 -- required keys _interpret_local()
                                                         # validates against; 'confidence' is asked
                                                         # for in the prompt but not required here,
                                                         # since older/smaller local models may not
                                                         # reliably emit it -- missing just means
                                                         # ai_provider.py's _clamp01() default (0.3).

# FR-1500 Voice Interaction. The wake-word/STT/LLM pipeline runs entirely on background
# threads. brain.py DOES call speak()/speak_safety() directly from RoverBrain._tick() (e.g. to
# announce an email or a finished retrieval task) — speak() only ever enqueues onto
# _speak_queue and returns immediately; the actual piper+aplay subprocess call (which can block
# for seconds) happens on _speaker_loop's own thread, never on the tick thread. Motion-triggering
# commands are only ever placed on pending_commands; brain.py is the sole consumer, and only
# drains it at Directive 6, after Directives 1-5 have already gated the tick (FR-1500-007). If
# ENABLE_VOICE is False (default — model files are not provisioned on this unit yet, see
# config.py), start() is a no-op, speak() just logs, and the whole pipeline stays inert.
#
# FR-1500-010 / defense in depth: any text that looks safety-related is forced to neutral tone
# even if the caller asked for a personality tone — mirrors the layered-allowlist pattern used
# in email_client.py's FR-2000 boundaries rather than trusting a single call site to always pass
# tone='neutral' correctly.
_WAKE_FRAME=1280      # openwakeword's 80ms block, always at 16kHz


def downsample_to_16k(samples,factor):
    """One captured block at 16000*factor Hz -> the same 80ms at 16kHz, int16.

    Mic swap 2026-09-09. The capture-only USB mic that replaced the Waveshare puck's microphone
    cannot do 16kHz at all -- its hardware offers 48000 and 44100 only -- and PortAudio exposes
    the raw `hw:` devices with no plug/default/PipeWire route, so ALSA will not resample for us.

    scipy's decimate, not `samples[::factor]`. Plain striding folds everything above the new
    8kHz Nyquist back down into the speech band as phantom tones, which would degrade wake
    scoring in a way that looks like a flaky mic rather than a bug. zero_phase keeps the filter
    from shifting the block in time, which matters because the endpointer measures per-frame RMS.
    """
    if factor==1: return samples          # 16kHz-native mic: cost nothing
    from scipy.signal import decimate
    return decimate(samples,factor,ftype='fir',zero_phase=True).astype(np.int16)


class PiperEngine:
    """Text -> WAV file, with the voice model loaded ONCE (2026-10-07, "faster responses").

    Every reply used to run the `piper` console script as a fresh process, which loads the
    .onnx voice from disk before synthesising a word: live timing put the tts bucket at
    2.6-5.1 s for one-line replies. Here the model is loaded on first use through Piper's Python
    API and kept. Two API generations exist (piper-tts 1.3+: synthesize_wav + SynthesisConfig;
    1.2: synthesize(text, wav, length_scale=)) -- both are tried. If neither imports or loads,
    `fallback` (the old subprocess path) is used, so speech can never be lost to this.

    Short fixed replies are also CACHED as finished WAV bytes, keyed on (text, length_scale):
    "Turning left.", "Checking.", ... need no synthesis at all after their first use."""
    def __init__(self,model_path,fallback,cache_max=None,max_cached_chars=None):
        self.model_path=model_path; self.fallback=fallback
        self.cache_max=cache_max if cache_max is not None else config.TTS_CACHE_MAX
        self.max_cached_chars=max_cached_chars if max_cached_chars is not None else config.TTS_CACHE_MAX_CHARS
        self._voice=None; self._api=None; self._load_failed=False; self._cache={}
        self.last_path=''   # 'cache' | 'inproc' | 'subprocess' -- logged beside the timing
    def _load(self):
        if self._voice is not None or self._load_failed: return
        try:
            from piper import PiperVoice
            self._voice=PiperVoice.load(self.model_path)
            try:
                from piper import SynthesisConfig    # piper-tts 1.3+
                self._api=('new',SynthesisConfig)
            except ImportError:
                self._api=('old',None)
            log.info(f'Piper voice loaded in-process ({self._api[0]} API)')
        except Exception as e:
            self._load_failed=True
            log.warning(f'Piper in-process unavailable ({type(e).__name__}: {e}); using the piper subprocess')
    def _synth_inproc(self,text,wav_path,scale):
        import wave
        with wave.open(wav_path,'wb') as w:
            kind,Cfg=self._api
            if kind=='new':
                self._voice.synthesize_wav(text,w,syn_config=Cfg(length_scale=scale))
            else:
                self._voice.synthesize(text,w,length_scale=scale)
    def synthesize(self,text,wav_path,scale=1.0):
        key=(text,round(scale,3))
        if key in self._cache:
            with open(wav_path,'wb') as f: f.write(self._cache[key])
            self.last_path='cache'; return
        self._load()
        done=False
        if self._voice is not None:
            try:
                self._synth_inproc(text,wav_path,scale); self.last_path='inproc'; done=True
            except Exception as e:
                log.warning(f'Piper in-process synthesis failed ({type(e).__name__}: {e}); subprocess this time')
        if not done:
            self.fallback(text,wav_path,scale); self.last_path='subprocess'
        if len(text)<=self.max_cached_chars:
            try:
                with open(wav_path,'rb') as f: data=f.read()
                if len(self._cache)>=self.cache_max: self._cache.pop(next(iter(self._cache)))
                self._cache[key]=data
            except OSError: pass


# Intents whose answer comes from brain.py reading sensors/state -- never from the model's text.
# 2026-10-10: a plain general question with no command in it skips the on-board model (which
# only maps COMMANDS, and spent 5.3 s on "why is the grass green?" before being rejected) and
# goes straight to the fast cloud chat.
_GENERAL_QUESTION=re.compile(r"^(?:why|how (?:does|do|did|is|are|many|much|far|long|big)|what(?:'s| is| are| was| were| does| do)|"
                             r"who|when (?:is|was|did|does)|tell me (?:about|a joke)|explain|can you tell me)\b",re.I)
_COMMAND_WORDS=re.compile(r"\b(?:you|your|yourself|willie|go|drive|move|turn|come|fetch|bring|get|stop|back|forward|"
                          r"reverse|map|steer|explore|roam|room|kitchen|battery|see|looking|doing|arm|wave|follow|"
                          r"shut|privacy|light|lights|log|logs)\b",re.I)

def general_question(text):
    t=re.sub(r'^(?:(?:hey|ok|okay)[\s,]+)?willie[\s,]+','',text.strip(),flags=re.I)
    return bool(_GENERAL_QUESTION.match(t)) and not _COMMAND_WORDS.search(t)

_SENSOR_ANSWERED=frozenset({'status','battery','where_are_you','what_do_you_see','what_doing','diagnostics','check_logs'})
# 2026-10-10, live: "Why is the grass green?" went to the Hailo model, which said where_are_you
# (0.8, three times), and Willie answered "I'm not sure which room I'm in". A sensor-answered
# intent from the MODEL must be backed by a word that belongs to it; otherwise it is not
# understood and falls through to the cloud model. The fast path is not affected.
_SENSOR_INTENT_WORDS={
    'where_are_you':('where','room','location','lost'),
    'battery':('battery','charge','charged','power','juice','volt','percent'),
    'what_do_you_see':('see','look','looking','camera','front of you','watching'),
    'what_doing':('doing','up to','going on','busy'),
    'status':('status','how are you','okay','ok','report','state','alright'),
    'diagnostics':('diagnos','self test','test yourself','check yourself'),
    'check_logs':('log','error','problem'),
}
_NEUTRAL_ACKS=frozenset({'','Checking.','Looking.'})

def speech_envelope(wav_path,step_s):
    """FR-1600-009: loudness per `step_s` of a 16-bit WAV, scaled 0..1 for the talking mouth.
    RMS per window, normalised to the 95th percentile so a loud word does not make every other
    word look shut; anything under MOUTH_TALK_GATE is 0 (mouth closed in the gaps). [] on any
    problem -- the mouth is decoration and must never stop him speaking."""
    import wave
    try:
        with wave.open(wav_path,'rb') as w:
            if w.getsampwidth()!=2: return []
            rate=w.getframerate(); ch=w.getnchannels()
            pcm=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)
        if ch>1: pcm=pcm.reshape(-1,ch).mean(axis=1)
        n=max(1,int(rate*step_s)); k=len(pcm)//n
        if k==0: return []
        rms=np.sqrt((pcm[:k*n].reshape(k,n)**2).mean(axis=1))
        ref=float(np.percentile(rms,95)) or 1.0
        env=np.clip(rms/ref,0.0,1.0)
        env[env<config.MOUTH_TALK_GATE]=0.0
        return [round(float(x),3) for x in env]
    except Exception:
        return []

_SAFETY_PATTERN=re.compile(
    r'\b(e-?stop|estop|emergency|fault|shutdown|shutting down|battery critical|low battery|'
    r'safe mode|stall|tilt|obstacle detected|confirm.*(move|drive|forward|reverse))\b',re.I)

# Voice latency handoff 2026-08-15, Fix 1: deterministic matcher for the small set of fixed-
# phrasing commands, tried before the ~15-20s local LLM intent call. Whole-utterance match only
# (not substring) -- a false match that starts motion is far worse than a miss that costs the
# LLM's usual latency (doc's explicit conservatism requirement), so these are deliberately
# narrow rather than broad. go_to/retrieve/smart_home take free-form args and stay LLM-only, per
# the doc. Reply text is empty for shutdown/diagnostics because brain.py's own handler for those
# speaks its own (required) message immediately on dispatch -- an extra ack here would either be
# redundant or, for shutdown, actively confusing right before the confirmation prompt.
# Real speech carries filler the original patterns rejected: "Willie, stop", "can you stow the
# arm", "what's the battery at please". Because _fast_path() uses fullmatch (deliberately -- see
# above), every one of those missed and fell through to the local LLM. That was an acceptable
# trade when this was written against an assumed 15-20s LLM; the LLM was measured live on this
# rover 2026-08-21 at 74.2s for a single intent (total round trip 84.9s), so a miss is now roughly
# 15x worse than assumed and widening coverage matters far more than it did.
_ADDRESS=r'(?:(?:hey |ok |okay )?willie(?:[,]? )|please |can you |could you |would you |'\
          r'i want you to |go ahead and |lets |let\'s )*'
_BARE_ADDRESS=re.compile(r'\s*(?:(?:hey|hi|ok|okay)[\s,]+)?willie[\s,.!?]*',re.I)
# FR-1500-008/009 (2026-10-02): tone is carried through to synthesis as Piper's length scale
# (speaking rate) -- the one prosody control a single Piper voice has. FR-1500-010's neutral
# override for safety text still runs first, in speak().
_TONE_LENGTH_SCALE={'neutral':1.0,'funny':0.92,'silly':0.85,'bashful':1.18}
# FR-1500-009 / FR-1600-006 triggers: a compliment or a personal question.
_BASHFUL_TRIGGER=re.compile(r"\b(good (boy|job|robot)|well done|(you'?re|you are) (so )?(cute|smart|clever|"
                            r"great|awesome|amazing|adorable|sweet)|i love you|how old are you|"
                            r"do you have (a )?(girlfriend|boyfriend|feelings)|are you (alive|happy|shy))\b",re.I)
# FR-1000-001 / FR-1200-006 labelling, matched before the LLM (2026-10-02).
_NAME_ROOM=re.compile(r"(?:this is|this room is|we(?:'re| are) in|you(?:'re| are) in) the ([a-z][a-z ]{1,30})",re.I)
# FR-1000-006 "I'm in the kitchen, come to me" / "come to me in the kitchen". "I'm in the
# kitchen" alone is not a room label (_NAME_ROOM is "we're in" / "this is"), so the two do not
# collide; matched first anyway so the order says so.
_COME_TO_ME=re.compile(r"(?:i'?m|i am) in the ([a-z][a-z ]{1,30}?)[,.]? (?:(?:please|can you|could you) )?"
                       r"come (?:to me|and find me|find me)|come (?:to me|and find me|find me) in the ([a-z][a-z ]{1,30})",re.I)
# Rotation mode (rotate.py, 2026-10-07): "turn around" = 180 left; "turn left/right 90 degrees".
# A bare "turn left" stays the short manual nudge -- only an explicit angle or "around" rotates.
_TURN_AROUND=re.compile(r"(?:turn|spin) (?:yourself )?around",re.I)
_TURN_DEGREES=re.compile(r"(?:turn|rotate|spin) (left|right) (\d{1,3}) degrees",re.I)
# FR-600-004 steering override (2026-10-08): wheels only, parked. "steer" never drives, so it
# cannot be confused with the "turn left" nudge.
_STEER=re.compile(r"steer (?:your wheels |the wheels )?(left|right)(?: (\d{1,2})(?: degrees)?)?",re.I)
_STEER_STRAIGHT=re.compile(r"(?:(?:wheels|steering) straight|straighten (?:your |the )?(?:wheels|steering)|"
                           r"cent(?:er|re) (?:your |the )?(?:wheels|steering))",re.I)
# FR-1800-005 privacy (2026-10-08). Turning it ON by voice only: once on he cannot hear, so the
# way back is the screen (two-tap RESUME) or an owner email "privacy off".
_PRIVACY_ON=re.compile(r"(?:privacy mode(?: on)?|turn on privacy(?: mode)?|go private|stop listening(?: to (?:me|us))?|"
                       r"turn off your (?:microphone|mic|camera|cameras)(?: and (?:your )?(?:microphone|mic|camera|cameras))?)",re.I)
_PRIVACY_OFF=re.compile(r"(?:privacy (?:mode )?off|turn off privacy(?: mode)?|resume listening|"
                        r"turn (?:on|back on) your (?:microphone|mic|camera|cameras)(?: and (?:your )?(?:microphone|mic|camera|cameras))?)",re.I)
_MARK_STAIRS=re.compile(r"(?:there are |these are )?(?:the )?(?:stairs|steps)(?: are)? (?:here|ahead|in front of you)",re.I)
# FR-1900-001/002 demonstrations.
_DEMO_START=re.compile(r"(?:watch me|follow me)?[\s,]*(?:and )?learn (?:the |this )?(?:way|route|path) (?:to )?(?:the )?([a-z][a-z ]{1,30})",re.I)
_DEMO_STOP=re.compile(r"(?:that's it|that is it|stop learning|done learning|finished|we're here|we are here)",re.I)
_DEMO_REPLAY=re.compile(r"(?:do|take|repeat|replay|show me) (?:the )?(?:way|route|path) (?:to )?(?:the )?([a-z][a-z ]{1,30})",re.I)
# FR-2100: "this is Carolyn" (a NAME -- "this is the kitchen" is a room, matched first).
_ENROL=re.compile(r"this is ([A-Z][a-z]+)",re.I)
_FORGET_EVERYONE=re.compile(r"forget everyone|forget all (?:the )?faces",re.I)
_NAME_REPLY=re.compile(r"(?:(?:hi|hello|hey)[\s,]+)?(?:i'?m|i am|it'?s|it is|my name is|this is)?\s*([A-Za-z]+)[.!]?",re.I)
_FORGET=re.compile(r"(?:please )?forget (?:about |that )?(.+)",re.I)
_ROUTINES=re.compile(r"what do i usually (?:ask|do|ask for)|what are my routines",re.I)
_RECALL=re.compile(r"what do you (?:remember|know)(?: about (.+))?",re.I)
# FR-1400-001 (2026-10-02): intents the rest of the system can act on. Escalation no longer
# rests on the model's self-reported confidence alone -- G-6 measured that number as carrying
# no information. An answer that fails to parse, or names an intent outside this set, is a
# deterministic "the local model did not understand" signal.
_ACTIONABLE_INTENTS=frozenset({'forward','reverse','turn_left','turn_right','go_to','retrieve',
    'confirm_receipt','map','stop_map','shutdown','status','battery','arm_stow','arm_home','wave',
    'come_here','come_to_me','rotate','steer','roam','follow','diagnostics','check_logs','where_are_you','what_do_you_see','what_doing','name_room','mark_stairs',
    'privacy_on','privacy_off','demo_start','demo_stop','demo_replay','enrol','forget_everyone','stop','smart_home','chat','time','date'})
_TRAILER=r'(?: please| now| for me| ok| okay| buddy)?'

def _fp(core):
    # fullmatch still: the whole utterance must be address + command + trailer and nothing else,
    # so "don't stop" and "we should stop soon" still fall through rather than firing motion.
    return re.compile(_ADDRESS+r'(?:'+core+r')'+_TRAILER,re.I)

# TIER 1 -- consequence-free if mis-fired (he speaks, nothing moves). Widened aggressively:
# the worst case is an unwanted spoken answer, versus 84.9s of silence for a miss.
# TIER 2 -- motion/destructive. Cores deliberately left as narrow as they were; only the address
# and trailer wrappers are new, so "Willie, turn left" works while "don't turn left" does not.
# 'stop' sits in tier 2 by topic but is fail-safe in the same direction as a false positive
# (stopping when not asked is harmless), so its core is widened too.
# Arm presets, composed as verb x subject rather than enumerated. "center arm" used to fall
# through to the ~30s LLM because the old pattern listed only 'arm home|reset your arm|home
# (the|your) arm' -- the same enumeration trap that let the time/date patterns regress three
# times. Both word orders are accepted because people say it both ways, and composing means a
# phrasing nobody predicted still lands.
# NOTE brain.py runs arm_home AND arm_stow as the same stepped move to ARM_POSE_REST (since
# 2026-10-02). The intents are distinct; the behaviour is not.
_ARM=r"(?:the |your |that )?arm"   # 'that' 2026-10-08: "put that arm away" reached the model
_ARM_HOME_V=r"(?:centre|center|home|reset)"
_ARM_STOW_V=r"(?:stow|park)"

# --- Emergency stop, deterministic. P0, 2026-09-14 review. -----------------------------------
# "whoa whoa please stop right now" was classified by the Hailo model as `where_are_you` at
# confidence 0.8 in 2 of 3 repeats (experiments/results/2026-09-14-failure-classification.md).
# It reached the model at all only because the tier-2 `stop` core above is wrapped in _ADDRESS /
# _TRAILER, whose vocabulary does not cover interjections ("whoa") or intensifiers ("right now").
# A safety-critical command was one model misfire away from being read as a question about which
# room the rover is in.
#
# STRUCTURE IS STILL FULLMATCH, deliberately. The review asked that the negation protection
# survive, and switching to a keyword search would break it: tests/test_voice_fast_path.py
# requires "we should stop soon" NOT to fire, because discussing stopping is not commanding it.
# What widens is the VOCABULARY around a narrow imperative core -- interjections and politeness
# in front, intensifiers behind. That is fail-closed: an unanticipated phrasing falls through to
# the LLM exactly as before, and no negation can be admitted because "don't" is not a prefix this
# accepts.
#
# Both groups are a single * over a flat alternation rather than nested quantifiers, which would
# be a backtracking hazard on long non-matching speech.
_STOP_PREFIX=(r"(?:(?:hey|ok|okay|oh|no|now|just|please|whoa|woah|willie|wait|"
              r"can you|could you|would you|i need you to|i want you to|you need to|"
              r"go ahead and)[,!]?\s+)*")
# "emergency stop" and "full stop" precede bare "stop": alternation is first-match, so the longer
# forms must come first or they would match as prefix-plus-"stop" and leave a trailing word.
_STOP_CORE=(r"(?:emergency stop|full stop|stop right there|stop moving|stop|halt|freeze|brake|"
            r"cease|stand still|hold (?:it|on|up)|whoa|woah)")
_STOP_TRAILER=(r"(?:[\s,]+(?:right now|right there|right here|now|immediately|moving|please|"
               r"for me|willie|ok|okay|buddy|there))*[\s!.?]*")
_EMERGENCY_STOP=re.compile(_STOP_PREFIX+_STOP_CORE+_STOP_TRAILER,re.I)

# Defence in depth. The fullmatch structure above cannot admit a negation today, because none of
# these words are in _STOP_PREFIX. This guard is for whoever widens that vocabulary next: it makes
# the requirement explicit rather than emergent, so a well-meaning addition of "do not" to the
# prefix list cannot silently turn "don't stop" into a stop.
_STOP_NEGATED=re.compile(r"\b(?:do\s*n[o']?t|do not|does\s*n[o']?t|did\s*n[o']?t|never|without|"
                         r"avoid|rather than|instead of|no need to|should\s*n[o']?t|"
                         r"could\s*n[o']?t|ca\s*n[o']?t|cannot|wo\s*n[o']?t|will not)"
                         r"\b",re.I)


def is_emergency_stop(text):
    """True when `text` is an imperative stop command.

    Fail-safe direction is asymmetric and chosen deliberately: a false positive stops a rover
    nobody asked to stop, which is annoying and harmless; a false negative fails to stop a moving
    rover when a person asked it to. Where a judgement call exists this errs toward stopping.

    The result goes straight to stop_requested -- never to the LLM, never to pending_commands.
    """
    norm=text.strip().rstrip('.!? ')
    if _STOP_NEGATED.search(norm): return False
    return bool(_EMERGENCY_STOP.fullmatch(norm))


_FAST_PATH_PATTERNS=[
    # --- tier 2: motion / destructive, narrow cores ---
    (_fp(r'stop|halt|freeze|hold (it|on|up)|stop moving|stand still|whoa'),'stop','Stopping.'),
    # FR-300-003 operator reset (owner decision 2026-09-17: voice OR screen tap). Tier 2 -- it
    # re-enables motion -- so the core stays narrow. A false positive is cheap in a way the
    # other tier-2 intents are not: brain.py only consumes 'reset' from a latched fault state
    # whose triggering condition has ALREADY cleared, so it can never override a live fault.
    (_fp(r'reset|clear (the )?fault|fault clear|all clear'),'reset','Reset. Motion re-enabled.'),
    (_fp(r'(?:go |move |drive )?forward'),'forward','Going forward.'),
    (_fp(r'(?:go |move |drive )?(?:reverse|backward|back up)'),'reverse','Backing up.'),
    # 2026-10-10 (owner): roam by voice, no screen tap. Saying it IS the permission.
    (_fp(r'(?:you can |go ahead and )?(?:go )?(?:explore|roam|wander)(?: around)?|go (?:for a )?(?:wander|walk|explore)|'
         r'start (?:exploring|roaming)'),'roam',''),
    (_fp(r'turn left'),'turn_left','Turning left.'),
    (_fp(r'turn right'),'turn_right','Turning right.'),
    (_fp(r'shut down|power off|go to sleep|power yourself (?:off|down)|shut yourself (?:off|down)|'
         r'turn yourself off'),'shutdown',''),   # still asks to confirm before anything happens
    # --- tier 1: speech-only, widened ---
    (_fp(r"(?:how'?s|hows|how is|what'?s|whats|what is|check) (?:your |the )?battery(?: (?:level|status|at|doing))?|"
         r"battery (?:status|level|check)|how much (?:charge|battery|power|juice)(?: (?:left|is left|do you have))?|"
         r"do you have (?:much |enough |any )?(?:charge|battery|power|juice)(?: left)?|"
         r"are you charged"),'battery','Checking.'),
    (_fp(r'status(?: report)?|how are you(?: doing| feeling)?|are you (?:doing )?(?:ok|okay|alright|good|well)|'
         r"what'?s your status|report"),'status','Checking.'),
    (_fp(r'where are you|what room (?:is this|are you in)|which room (?:is this|are you in)|'
         r"where(?:'?s| is) this|do you know where you are"),'where_are_you','Checking.'),
    (_fp(r'what (?:do|can) you see|what'r"'"r's (?:in front of you|out there|there)|'
         r'look around|describe what you see|tell me what you see|'
         r'what are you looking at|what(?:'r"'"r're| are) you staring at'),'what_do_you_see','Looking.'),
    # 2026-10-07 (owner): "what are you doing?" gets a brief answer about his current activity.
    (_fp(r'what(?:'r"'"r're| are) you doing|whatcha doing|what are you up to|what(?:'r"'"r's| is) going on'),
         'what_doing',''),
    (_fp(r'wave(?: hello| hi| at me| at (?:them|him|her|everyone|everybody))?|'
         r'say (?:hi|hello)(?: to (?:them|him|her|everyone|everybody))?|give (?:me |them )?a wave'),'wave',''),
    (_fp(_ARM_STOW_V+r' '+_ARM+r'|put '+_ARM+r' away|'+_ARM+r' away'),'arm_stow','Stowing the arm.'),
    (_fp(_ARM_HOME_V+r' '+_ARM+r'|'+_ARM+r' '+_ARM_HOME_V),'arm_home','Homing the arm.'),
    (_fp(r'(?:start|begin) (?:mapping|the map)|map this room|start mapping this room'),
     'map','Starting the map.'),
    (_fp(r'(?:stop|end|finish) (?:mapping|the map)'),'stop_map','Stopping the map.'),
    # 2026-10-10 (owner): a spoken summary of his own log.
    (_fp(r'(?:check|scan|read|look at) (?:your |the )?logs?(?: for (?:errors|problems))?|'
         r'any (?:errors|problems)(?: today| lately)?|what (?:errors|problems) (?:have you had|did you have)(?: today)?'),
     'check_logs',''),
    (_fp(r'run (?:a )?diagnostics?|(?:run )?(?:a )?self test|diagnostics|check yourself'),
     'diagnostics',''),
]

_ACK_TONE_S=0.18      # wake-chirp duration. NOT skipped from capture -- see _handle_wake()

# Composed rather than enumerated. Both patterns below are built as an optional interrogative
# prefix followed by a subject noun phrase, because enumerating surface forms has now failed
# three times in a row -- each time fixed by appending one more alternative, each time leaving
# every OTHER unlisted combination as a silent ~30s fall-through to the local LLM:
#   2026-08-21  a clipped first word turned "what time is it" into "time is it" -> 84.9s
#   2026-08-23  "what's today's day" missed -- no alternative put "today's" before "day"
#   2026-08-25  "What is the current time?" missed -- `(?:the )?current time` was a bare
#               alternative, so nothing allowed "what is" in front of it. Live log 08:19:15:
#               30s in the LLM, directly after "What is today's date?" answered in 8.7s, which
#               is why it presented as "the second command never works".
# Coverage is deliberately generous. These are tier 1: a false positive means Willie tells you
# the time when you did not ask, against 30s of apparent deafness for a miss. Neither 'time' nor
# 'date' is in _interpret_local()'s prompt, so anything missing here reaches an LLM with no clock
# that will cheerfully invent an answer. Regression-pinned in tests/test_voice_fast_path.py.
_ASK=r"(?:what'?s|whats|what is|tell me|do you know|do you have|have|got)"

_TIME_PATTERN=re.compile(
    _ADDRESS+r"(?:"
    r"(?:"+_ASK+r" )?(?:the )?(?:current )?time(?: is it)?|"
    r"(?:what )?time is it|"
    r"do you (?:know|have) (?:what )?the time(?: it is)?|"
    r"time check|what hour is it"
    r")"+_TRAILER,re.I)

_DATE_PATTERN=re.compile(
    _ADDRESS+r"(?:"
    r"(?:"+_ASK+r" )?(?:the |today'?s )?(?:current )?(?:date|day)(?: today)?|"
    r"(?:what|which) (?:date|day) is it(?: today)?|"
    r"(?:what'?s|whats) (?:it |the day )?today|what day is today|"
    r"(?:tell me|do you know) (?:the|what) date(?: it is)?|"
    r"date check"
    r")"+_TRAILER,re.I)

class VoicePipeline:
    def __init__(self,memory=None,cloud_ai=None,display=None,smart_home=None):
        self._enabled=config.ENABLE_VOICE
        self.memory=memory; self.cloud_ai=cloud_ai; self.display=display; self.smart_home=smart_home
        self._tts=None   # PiperEngine, created on the speaker thread at first use
        self.pending_commands=queue.Queue()
        self._speak_queue=queue.Queue()
        # 'stop' bypasses pending_commands entirely — every other queued intent only gets drained
        # by brain.py from IDLE (Directive 6), so a spoken "stop" during an in-progress RETRIEVE/
        # NAVIGATE/PURSUE task would otherwise never be picked up at all. brain.py's tick thread
        # polls this Event at the very top of _tick(), before any Directive gating, and is the
        # only thing that ever clears it or touches SafetyController — this stays a plain signal,
        # not a second writer into motor control.
        self.stop_requested=threading.Event()
        self._running=False; self._thread=None; self._speaker_thread=None
        self._wakeword=None; self._whisper=None; self._local_ai=None
        self._noise_rms=None  # ambient floor, maintained by _update_noise() on the wake loop
        # Wake-loop heartbeat (2026-10-01). Voice went silently deaf for weeks: the thread was
        # alive and reading, nothing was logged, and the only symptom was "no chirp". One line a
        # minute -- frames scored vs muted, best wake score, loudest frame, overflows -- says
        # which half is broken without stopping the service to test the mic by hand.
        self._hb=dict(t=time.time(),scored=0,muted=0,best=0.0,peak=0.0,overflows=0)
        # No echo cancellation on this mic+speaker puck — TTS playback leaks straight back into
        # capture, gets transcribed as a new "command", and self-triggers another AI round-trip
        # forever (found 2026-08-15: "One moment, checking..." looping on its own echo, deaf to
        # real wake words the whole time since predict() and utterance handling share this one
        # thread). Gate wake-word scoring while speaking, plus a decay grace period after.
        self._speaking=threading.Event()
        # Set by _process_utterance just before the one speak() call each utterance-processing
        # pass makes (every branch returns right after its single speak(), so at most one
        # utterance's timing is ever in flight); speak() snapshots+clears it into the queued
        # item so _speaker_loop can log the full wake->stt->intent->tts breakdown on its own
        # thread once synthesis finishes. None for speak() calls with no wake-word origin
        # (brain.py's direct calls, "How can I help?"/_maybe_learn early-return branches).
        self._utterance_timing=None
        if self._enabled: self._load_models()

    def _load_models(self):
        missing=[p for p in (config.WAKEWORD_MODEL_PATH,config.PIPER_VOICE_PATH,config.LOCAL_LLM_MODEL_PATH)
                 if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),p))]
        if missing:
            log.warning(f'Voice model file(s) missing, staying disabled: {missing}')
            self._enabled=False; return
        try:
            import openwakeword; from openwakeword.model import Model as OwwModel
            from faster_whisper import WhisperModel
            # openwakeword 0.4.0's Model.__init__ takes wakeword_model_paths, not
            # wakeword_models — the old kwarg silently fell through to **kwargs and crashed
            # deeper inside AudioFeatures.__init__, caught here and disabling voice entirely.
            self._wakeword=OwwModel(wakeword_model_paths=[config.WAKEWORD_MODEL_PATH])
            # local_files_only: WHISPER_MODEL_SIZE is a hub name, not a path like the other three
            # models above -- without this, construction hits huggingface.co to check the cached
            # revision every time, violating FR-1500-002's "no cloud dependency for basic STT"
            # and adding a startup network dependency. Cache already exists at
            # ~/.cache/huggingface/hub/models--Systran--faster-whisper-small.en (found 2026-08-09).
            # cpu_threads: unset used to mean "take all 4 cores", whose current spike was browning
            # out the 5V rail mid-utterance and hard-killing the rover (2026-08-21). See config.
            # 2026-08-23: Hailo NPU STT scaffolded alongside the LLM/vision backends, same
            # fail-safe pattern -- HailoWhisper always raises today (no HEF exists yet, see
            # hailo_stt.py), so this falls straight through to the CPU faster_whisper path below.
            if config.ENABLE_HAILO_STT:
                try:
                    from hailo_stt import HailoWhisper
                    self._whisper=HailoWhisper()
                except Exception as e:
                    log.warning(f'Hailo STT unavailable, falling back to CPU: {e}')
                    self._whisper=None
            else:
                self._whisper=None
            if self._whisper is None:
                self._whisper=WhisperModel(config.WHISPER_MODEL_SIZE,device='cpu',compute_type='int8',
                                            local_files_only=True,cpu_threads=config.WHISPER_CPU_THREADS)
            # §14 -- was a bare Llama(...) instance here. 2026-08-23: Hailo NPU backend added
            # alongside it, same fail-safe pattern as the Hailo vision backend (config.py).
            if config.ENABLE_HAILO_LLM:
                try:
                    from hailo_llm import HailoIntentModel
                    self._local_ai=HailoIntentModel()
                    if not self._local_ai.available: raise RuntimeError('Hailo LLM load reported unavailable')
                except Exception as e:
                    log.warning(f'Hailo LLM unavailable, falling back to CPU: {e}')
                    self._local_ai=None
            else:
                self._local_ai=None
            if self._local_ai is None:
                self._local_ai=LocalAIProvider()
            if not self._local_ai.available: raise RuntimeError('local LLM failed to load')
        except Exception as e:
            log.error(f'Voice model load failed, staying disabled: {e}')
            self._enabled=False

    @property
    def available(self): return self._enabled

    def start(self):
        if not self._enabled: return
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()
        self._speaker_thread=threading.Thread(target=self._speaker_loop,daemon=True); self._speaker_thread.start()
        log.info('Voice pipeline started.')

    def stop(self):
        self._running=False
        if self._thread is not None: self._thread.join(timeout=3.0)
        if self._speaker_thread is not None: self._speaker_thread.join(timeout=3.0)

    def _speaker_loop(self):
        # Sole consumer of _speak_queue — keeps every speak()/speak_safety() call (including
        # brain.py's, from the main tick thread) non-blocking regardless of caller.
        # Load the voice now, while nothing is waiting to be said, so the FIRST reply is as quick
        # as the rest (PiperEngine, 2026-10-07).
        try:
            if self._tts is None:
                model=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.PIPER_VOICE_PATH)
                self._tts=PiperEngine(model,self._piper_subprocess)
            self._tts._load()
        except Exception: log.warning('Piper warm-up failed; loading on first reply',exc_info=True)
        while self._running:
            try: text,timing,tone=self._speak_queue.get(timeout=0.5)
            except queue.Empty: continue
            self._speaking.set()
            try: self._synthesize_and_play(text,timing,tone)
            finally:
                self._play_done()  # owner-requested: signals Willie has finished and is listening
                # 2026-08-23: was hardcoded 0.6s. Live symptom: 2-3 spurious wake-word triggers
                # firing ~8s after a real reply, each producing an empty transcript ("How can I
                # help?" spoken each time). Raising this to 2.0s and separately raising
                # WAKEWORD_THRESHOLD 0.5->0.65 (a live-suspected dehumidifier as the noise
                # source) neither one stopped it -- ruling out both "echo hasn't decayed yet"
                # and "threshold too permissive for ambient noise". The real cause: predict()
                # is never called while _speaking is set (the `continue` in _loop() skips it
                # entirely), so openwakeword's Model keeps whatever internal smoothing-window
                # state it had from just before muting -- including the elevated state from the
                # genuine wake event that started this reply. Model.reset() (confirmed present
                # on this installed version) clears that, so scoring resumes cold instead of
                # picking up mid-decay from a stale, already-elevated internal buffer.
                time.sleep(config.VOICE_ECHO_DECAY_S)
                # Reset BEFORE clearing _speaking, not after: _loop() resumes scoring the
                # instant _speaking clears, so clearing first leaves a window where predict()
                # runs against the stale buffer this reset exists to clear -- or runs
                # concurrently with reset() mutating openwakeword's internals, which makes no
                # thread-safety promise. Narrow (80ms frame cadence) but free to close.
                if self._wakeword is not None:
                    try: self._wakeword.reset()
                    except Exception as e: log.warning(f'Wake model reset failed: {e}')
                self._speaking.clear()

    def _read_frame(self,stream):
        # THE rate boundary. Everything downstream of this -- wake scoring, the noise floor, the
        # endpointer's fps math, Whisper -- assumes 16kHz/1280, and this is what keeps that true
        # no matter what the mic's native rate is. Both capture paths go through it.
        # 2026-10-02: blocks come from the PortAudio CALLBACK via a queue (see _loop), not from a
        # blocking read. The blocking read dropped ~55 blocks a minute (~20% of the audio) when
        # scoring or anything else on this thread ran late, and a wake word missing chunks is a
        # wake word that fails at distance. The queue holds AUDIO_QUEUE_BLOCKS (~4 s) of slack.
        try: raw=self._audio_q.get(timeout=2.0)
        except queue.Empty: raise RuntimeError('no audio from the capture callback for 2 s')
        return downsample_to_16k(raw,self._rate_factor)

    def _loop(self):
        import sounddevice as sd
        frame_len=_WAKE_FRAME  # what the REST of the pipeline sees: openwakeword's 80ms @16kHz
        # The mic may not support 16kHz (2026-09-09: the current one supports only 48000/44100),
        # so capture natively and convert in _read_frame(). Validated in config.validate().
        self._rate_factor=int(config.AUDIO_INPUT_RATE)//16000
        self._blocksize=frame_len*self._rate_factor
        try:
            self._audio_q=queue.Queue(maxsize=config.AUDIO_QUEUE_BLOCKS)
            # blocksize=0: let PortAudio deliver the driver's natural period and re-cut it into
            # _blocksize frames here. Measured on the rover 2026-10-02: a forced 3840-sample
            # block lost ~20% of the samples (19 overflows / 15 s); blocksize=0 lost none.
            pend=[np.zeros(0,dtype=np.int16)]
            def _cb(indata,frames,t,status):
                if status.input_overflow: self._hb['overflows']+=1
                buf=np.concatenate((pend[0],indata[:,0]))
                n=self._blocksize
                while len(buf)>=n:
                    try: self._audio_q.put_nowait(buf[:n].copy())
                    except queue.Full: self._hb['overflows']+=1   # consumer 4 s behind: drop
                    buf=buf[n:]
                pend[0]=buf
            with sd.InputStream(samplerate=int(config.AUDIO_INPUT_RATE),channels=1,dtype='int16',
                                 device=config.AUDIO_INPUT_DEVICE,blocksize=0,
                                 latency='high',callback=_cb) as stream:
                # Logged once, by resolved name: picking the wrong mic is otherwise invisible and
                # presents as "the wake word just doesn't work" -- see the 2026-08-21 hunt.
                try:
                    import sounddevice as _sd
                    log.info('Voice capture on %r @ %dHz (decimating %dx to 16k)',
                             _sd.query_devices(config.AUDIO_INPUT_DEVICE,'input')['name'],
                             int(config.AUDIO_INPUT_RATE),self._rate_factor)
                except Exception: pass
                while self._running:
                    if not privacy.mic_enabled():
                        time.sleep(1.0); continue  # FR-1800-005, re-checked continuously
                    flat=self._read_frame(stream)
                    self._heartbeat()
                    if self._speaking.is_set():
                        self._hb['muted']+=1
                        p=getattr(self,'_prompt',None)
                        if p: p['seen_speaking']=True
                        continue  # still drain the buffer, just don't score our own echo
                    p=getattr(self,'_prompt',None)
                    if p:
                        # FR-2100-003 prompted listen: once the question has played (or 3 s if
                        # it never started), capture one utterance with no wake word.
                        if time.time()>p['deadline']:
                            self._prompt=None; p['cb'](None); continue
                        if p['seen_speaking'] or time.time()-p['t0']>3.0:
                            self._prompt=None
                            self._handle_wake(stream,frame_len,time.time(),on_text=p['cb'])
                            continue
                    self._update_noise(flat)
                    scores=self._wakeword.predict(flat)
                    hb=self._hb; hb['scored']+=1
                    hb['best']=max(hb['best'],max(scores.values(),default=0.0))
                    hb['peak']=max(hb['peak'],float(np.sqrt(np.mean((flat.astype(np.float32)/32768.0)**2))))
                    if max(scores.values(),default=0.0)>=config.WAKEWORD_THRESHOLD:
                        self._handle_wake(stream,frame_len,time.time())
                        self._drop_backlog()
        except Exception as e:
            log.error(f'Voice input stream failed, pipeline stopping: {e}')
            self._running=False

    def _drop_backlog(self):
        """After an utterance is handled: discard audio queued while he was transcribing and
        thinking, and reset the wake model's smoothing. That backlog is stale -- scored late, it
        can open a new listen just as his reply starts (2026-10-08, he heard himself)."""
        q=getattr(self,'_audio_q',None)
        n=0
        while q is not None:
            try: q.get_nowait(); n+=1
            except queue.Empty: break
        try: self._wakeword.reset()
        except Exception: pass
        if n: log.debug(f'dropped {n} stale audio blocks after the utterance')

    def _heartbeat(self):
        hb=self._hb; now=time.time()
        if now-hb['t']<60.0: return
        log.info('wake loop: %d scored, %d muted, best score %.3f (threshold %.2f), peak rms %.4f, '
                 'noise %.4f, %d overflows',hb['scored'],hb['muted'],hb['best'],
                 config.WAKEWORD_THRESHOLD,hb['peak'],self._noise_rms or 0.0,hb['overflows'])
        self._hb=dict(t=now,scored=0,muted=0,best=0.0,peak=0.0,overflows=0)

    def _update_noise(self,samples):
        # Ambient floor for endpointing, tracked continuously on the wake-scoring loop rather
        # than sampled at capture start: by then the speaker is usually already talking, which
        # would set the threshold above their own voice and silently disable endpointing (found
        # in simulation 2026-08-21 before this ever ran on hardware). Asymmetric EMA -- rises
        # slowly, falls fast -- so it tracks the room's floor, not speech peaks.
        rms=float(np.sqrt(np.mean((samples.astype(np.float32)/32768.0)**2)))
        if self._noise_rms is None: self._noise_rms=rms
        else: self._noise_rms+=(0.02 if rms>self._noise_rms else 0.25)*(rms-self._noise_rms)

    def _ensure_ack_wav(self):
        # Generated rather than provisioned: models/ is gitignored, and a 4KB tone doesn't belong
        # in git anyway. Written once, then reused.
        path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.VOICE_ACK_PATH)
        if not os.path.exists(path):
            import wave
            sr=16000; dur=_ACK_TONE_S
            t=np.linspace(0,dur,int(sr*dur),endpoint=False)
            env=np.minimum(1.0,np.minimum(t,dur-t)*40.0)  # fade both ends, else it clicks
            tone=0.22*env*np.sin(2*np.pi*880*t)
            os.makedirs(os.path.dirname(path),exist_ok=True)
            with wave.open(path,'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes((tone*32767).astype(np.int16).tobytes())
        return path

    def _play_ack(self):
        # FR-1500 perceived latency. Popen, not run: this must never delay the capture it
        # precedes. Failure here is cosmetic only, so it's logged at info and swallowed.
        if not config.VOICE_ACK_ENABLED: return
        try:
            subprocess.Popen(['pw-play',self._ensure_ack_wav()],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except Exception as e:
            log.info(f'Wake ack skipped: {e}')

    def _ensure_done_wav(self):
        # Two short 660Hz pulses, not one -- audibly distinct from the single 880Hz wake chirp
        # so the two can never be confused by ear. Generated once, then reused, same as
        # _ensure_ack_wav().
        path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.VOICE_DONE_PATH)
        if not os.path.exists(path):
            import wave
            sr=16000; pulse=0.12; gap=0.08
            t=np.linspace(0,pulse,int(sr*pulse),endpoint=False)
            env=np.minimum(1.0,np.minimum(t,pulse-t)*40.0)  # fade both ends, else it clicks
            one=0.22*env*np.sin(2*np.pi*660*t)
            silence=np.zeros(int(sr*gap))
            tone=np.concatenate([one,silence,one])
            os.makedirs(os.path.dirname(path),exist_ok=True)
            with wave.open(path,'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes((tone*32767).astype(np.int16).tobytes())
        return path

    def _play_done(self):
        # Blocking (subprocess.run, not Popen) -- _speaker_loop must wait for this to finish
        # before it clears _speaking/resets the wake model, so this chirp's own sound is muted
        # the same way the wake chirp's is, not left to self-trigger the bug just fixed above.
        if not config.VOICE_DONE_CHIRP_ENABLED: return
        try:
            subprocess.run(['pw-play',self._ensure_done_wav()],capture_output=True,timeout=5)
        except Exception as e:
            log.info(f'Done chirp skipped: {e}')

    def _handle_wake(self,stream,frame_len,t_wake,on_text=None):
        # FR-1500-001 satisfied (wake word seen) — now capture an utterance and process it.
        # Endpointed capture (2026-08-21, was a fixed 4s window): ends once the speaker stops,
        # so a short command no longer pays a long command's latency. Falls back to the old
        # behaviour exactly -- a full VOICE_CAPTURE_MAX_S window -- whenever endpointing can't
        # decide (nothing above threshold, or a room noisy enough that nothing reads as silence).
        if self.display: self.display.update_state(state='listening',status='Listening...')
        self._play_ack()
        fps=16000.0/frame_len
        # NOTE: capture starts immediately. An earlier version discarded _ACK_SKIP_S of frames
        # here so the chirp wouldn't be recorded (no echo cancellation on this puck) -- that was
        # wrong and shipped a real regression: people start speaking the instant the wake word
        # fires, so those frames hold the first word. Live 2026-08-21 it turned "what time is it"
        # into "Time is it.", which then missed _fast_path()'s fullmatch and fell through to the
        # local LLM: 84.9s total (intent=74.2s) instead of a sub-second regex hit. The chirp is a
        # short 880Hz tone, not speech -- Whisper's vad_filter drops it, and a pure tone cannot
        # transcribe into words, so letting it into the buffer is much safer than losing audio.
        max_frames=int(config.VOICE_CAPTURE_MAX_S*fps)
        min_frames=int(config.VOICE_CAPTURE_MIN_S*fps)
        end_frames=max(1,int(config.VOICE_ENDPOINT_SILENCE_S*fps))
        thresh=max(config.VOICE_VAD_FLOOR,(self._noise_rms or 0.0)*config.VOICE_VAD_NOISE_MULT)
        # The chirp is audible to our own mic (no echo cancellation). It must NOT be allowed to
        # latch `heard`, or the speaker's natural pause right after it reads as end-of-utterance
        # and capture cuts at min_frames while they are still talking -- live 2026-08-21 that
        # truncated every command to 0.9s and Whisper returned nothing at all ("How can I help?").
        # Its audio is still kept; only the endpoint decision ignores this window.
        deaf_frames=int((_ACK_TONE_S+0.14)*fps) if config.VOICE_ACK_ENABLED else 0
        # Two consecutive loud frames to latch, so a click or a single transient can't arm the
        # endpointer either.
        audio=[]; heard=False; silent=0; loud=0
        for i in range(max_frames):
            s=self._read_frame(stream); audio.append(s)
            if self._speaking.is_set():
                # 2026-10-08, live: a capture opened from the audio backlog just as his reply
                # began, recorded the reply, and he answered himself ("Heard: I'm just starting
                # up."). Anything captured while he is speaking is his own voice: drop it.
                log.info('capture abandoned: I started speaking')
                if self.display: self.display.update_state(state='idle',status='')
                if on_text is not None: on_text(None)
                return
            rms=float(np.sqrt(np.mean((s.astype(np.float32)/32768.0)**2)))
            if i<deaf_frames: continue
            if rms>=thresh:
                loud+=1; silent=0
                if loud>=2: heard=True
            else:
                loud=0
                if heard: silent+=1
            if heard and silent>=end_frames and i>=min_frames: break
        pcm=np.concatenate(audio).astype(np.float32)/32768.0
        log.info('capture: %.1fs of %.1fs max (endpointed=%s)',
                  len(audio)/fps,config.VOICE_CAPTURE_MAX_S,heard and silent>=end_frames)
        if self.display: self.display.update_state(state='processing',status='Thinking...')
        if on_text is not None:   # prompted listen: hand back the words, interpret nothing
            try:
                with self._display_quiet():
                    segs,_=self._whisper.transcribe(pcm,language='en',beam_size=1,vad_filter=True)
                    text=' '.join(s.text for s in segs).strip()
            except Exception:
                log.warning('Prompted transcription failed',exc_info=True); text=''
            on_text(text or None); return
        self._process_utterance(pcm,t_wake)

    def _display_quiet(self):
        """Context: the face draws at DISPLAY_FPS_QUIET while speech is transcribed (2026-10-08)."""
        import contextlib
        disp=self.display
        @contextlib.contextmanager
        def cm():
            try:
                if disp is not None and hasattr(disp,'set_quiet'): disp.set_quiet(True)
            except Exception: pass
            try: yield
            finally:
                try:
                    if disp is not None and hasattr(disp,'set_quiet'): disp.set_quiet(False)
                except Exception: pass
        return cm()

    def _process_utterance(self,pcm,t_wake):
        # FR-1500-002: onboard STT, no cloud dependency. Also satisfies FR-1800-001 (raw
        # audio never transmitted off-device): cloud_ai.ask_sync() below is only ever given
        # already-transcribed text, never the PCM buffer, so no cloud fallback path exists that
        # would need to send raw audio in the first place.
        with self._display_quiet():
            # segments is a lazy generator -- decoding happens in the join, so it stays inside
            segments,_=self._whisper.transcribe(pcm,language='en',beam_size=1,vad_filter=True)
            text=' '.join(s.text for s in segments).strip()
        t_stt=time.time()
        if not text:
            self.speak("How can I help?"); return
        log.info(f'Heard: "{text}"')
        self._reply_tone=config.VOICE_TONE_DEFAULT
        if _BASHFUL_TRIGGER.search(text):
            self._reply_tone='bashful'
            if self.display:
                try: self.display.set_expression('bashful')
                except Exception: pass
        if _BARE_ADDRESS.fullmatch(text):
            # Only the wake phrase was transcribed. 2026-10-01 the LLM turned a bare "Hey,
            # Willie" into a 'retrieve' intent; there is no command here to interpret.
            self.speak("How can I help?"); return
        if self.display: self.display.note_heard()

        # FR-1900-006: explicit teaching commands short-circuit interpretation, handled locally.
        if self.memory and self._maybe_learn(text): return

        # FR-1900-007: a stored "when I say X, do Y" instruction is APPLIED -- the trigger phrase
        # is replaced by its action text, which then goes through the normal fast path / LLM and
        # all of brain.py's gating, exactly as if the action had been spoken. One substitution
        # only, so an instruction can never chain into a loop.
        if self.memory:
            spoken=re.sub(r'^(?:(?:hey|ok|okay)[\s,]+)?willie[\s,]+','',text.strip().rstrip('.!? '),flags=re.I).lower()
            for ins in self.memory.all_instructions():
                if spoken==ins['trigger_phrase'].strip().rstrip('.!? ').lower():
                    log.info(f'Instruction applied: "{ins["trigger_phrase"]}" -> "{ins["action_text"]}"')
                    text=ins['action_text']; break
        fast=self._fast_path(text)
        if fast is not None:
            t_intent=time.time()
            self._utterance_timing=(t_wake,t_stt,t_intent)
            log.info(f'Fast-path matched: "{text}" -> {fast["intent"]}')
            self._act_on_intent(fast,text); return

        if general_question(text) and self.cloud_ai and self.cloud_ai.available:
            t_intent=time.time(); self._utterance_timing=(t_wake,t_stt,t_intent)
            log.info(f'General question, straight to cloud chat: "{text}"')
            import privacy as _p; _p.note_cloud_send(self.display,self,'your question')
            chat=getattr(self.cloud_ai,'chat',None)
            result=chat(text) if chat else self.cloud_ai.ask_sync(text)
            if result.parse_success:
                self.speak(result.payload,tone=getattr(self,'_reply_tone',config.VOICE_TONE_DEFAULT)); return
            self.speak("I couldn't look that up right now."); return
        intent,confidence=self._interpret_local(text)
        t_intent=time.time()
        # Voice latency handoff 2026-08-15 Step 0: timing captured through here regardless of
        # which branch below fires — cloud fallback and the low-confidence reply both still went
        # through STT+local-intent-parse, so their cost belongs in the same measurement.
        self._utterance_timing=(t_wake,t_stt,t_intent)
        if confidence<config.LOCAL_LLM_CONFIDENCE_FLOOR:
            if self.cloud_ai and self.cloud_ai.available:
                import privacy as _p; _p.note_cloud_send(self.display,self,'your request')
                result=self.cloud_ai.ask_sync(text)  # §14: schema=None -> free text, result.payload is the reply
                if result.parse_success:
                    self.speak(result.payload,tone=getattr(self,'_reply_tone',config.VOICE_TONE_DEFAULT)); return
            # FR-1500-005: never guess and act.
            self.speak("I'm not confident I understood that — could you rephrase it?"); return
        self._act_on_intent(intent,text)

    def set_current_person(self,name):
        """FR-2100-004: brain reports each recognised face; it is 'who I am talking to' for
        FACE_SPEAKER_WINDOW_S. Last face seen, not a voice match -- design §5.1's known weakness."""
        self._person=(name,time.time())
    def current_person(self):
        p=getattr(self,'_person',None)
        return p[0] if p and time.time()-p[1]<config.FACE_SPEAKER_WINDOW_S else None

    def ask(self,question,timeout_s=None):
        """Speak a question, then -- with no wake word -- beep and listen for the answer once
        (2026-10-10, owner: "when he asks a question automatically beep and turn on the mic").
        The answer is queued like any spoken command, so the brain's existing yes/no handling
        (roam permission, shutdown confirmation) receives it unchanged. No answer = nothing
        queued; the ask then lapses on its own timeout as before."""
        self.speak(question)
        def queue_answer(text):
            if text: self.pending_commands.put({'intent':None,'text':text,'source':'voice','ts':time.time()})
        self.prompt_listen(queue_answer,timeout_s if timeout_s is not None else config.VOICE_ASK_LISTEN_S)

    def prompt_listen(self,on_text,timeout_s):
        """FR-2100-003: listen once WITHOUT the wake word, after the question being spoken has
        finished, and call on_text(transcript or None). A narrow entry point -- the wake gate
        itself is untouched (design §5)."""
        if not self._enabled or self._whisper is None: on_text(None); return
        self._prompt={'cb':on_text,'deadline':time.time()+timeout_s+6.0,'seen_speaking':False,
                      't0':time.time()}

    def interpret_text(self,text):
        """FR-2000-012: the voice interpreter for text that did not come from the microphone
        (an authenticated owner email). Same steps as a spoken utterance -- bare-address check,
        stored instruction, fast path, local model with the FR-1400-001 gate -- but it speaks
        nothing and queues nothing; the caller does. Returns an intent dict or None."""
        text=(text or '').strip()
        if not text or _BARE_ADDRESS.fullmatch(text): return None
        if self.memory:
            spoken=text.rstrip('.!? ').lower()
            for ins in self.memory.all_instructions():
                if spoken==ins['trigger_phrase'].strip().rstrip('.!? ').lower():
                    text=ins['action_text']; break
        fast=self._fast_path(text)
        if fast is not None: return fast
        if not self._enabled or self._local_ai is None: return None
        intent,confidence=self._interpret_local(text)
        return intent if confidence>=config.LOCAL_LLM_CONFIDENCE_FLOOR else None

    def _maybe_learn(self,text):
        norm=text.strip().rstrip('.!? ')
        if _FORGET_EVERYONE.fullmatch(norm): return False   # FR-2100: brain's intent, not a fact
        # FR-1900-008: correction and deletion by voice. Both delete paths existed; nothing
        # spoken reached them.
        m=_FORGET.fullmatch(norm)
        if m:
            what=re.sub(r'^(?:the|a|an|my)\s+','',m.group(1).strip().lower())
            if len(what)<3 or what in ('it','that','this','them','everything','all'):
                # "forget it" must never become "delete everything containing 'it'".
                self.speak('Tell me what to forget, for example: forget the blue cup.'); return True
            hit=re.compile(r'\b'+re.escape(what)+r'\b',re.I).search
            facts=[k for k,v in self.memory.all_facts().items() if hit(k) or hit(str(v))]
            instr=[i for i in self.memory.all_instructions()
                   if hit(i['trigger_phrase']) or hit(i['action_text'])]
            for k in facts: self.memory.delete_fact(k)
            for i in instr: self.memory.delete_instruction(i['id'])
            n=len(facts)+len(instr)
            self.speak(f"Okay, I've forgotten {n} thing{'s' if n!=1 else ''} about {what}." if n
                       else f"I don't have anything stored about {what}.")
            return True
        if _ROUTINES.fullmatch(norm):
            tops=self.memory.top_routines()
            self.speak(('You usually ask for '+'; '.join(f"{t['pattern']} ({t['count']} times)" for t in tops)+'.')
                       if tops else "I haven't noticed any routines yet.")
            return True
        m=_RECALL.fullmatch(norm)
        if m:
            what=(m.group(1) or '').strip().lower()
            facts=[v for k,v in self.memory.all_facts().items() if not what or what in k.lower() or what in str(v).lower()]
            instr=[f"when you say {i['trigger_phrase']}, I {i['action_text']}" for i in self.memory.all_instructions()
                   if not what or what in i['trigger_phrase'].lower() or what in i['action_text'].lower()]
            items=(facts+instr)[:4]
            self.speak(('I remember: '+'; '.join(str(x) for x in items)+'.') if items
                       else "I don't have anything stored about that.")
            return True
        m=re.match(r"remember that (.+)",text,re.I)
        if m:
            # FR-2100-004: scoped to whoever he last recognised (within FACE_SPEAKER_WINDOW_S).
            who=self.current_person()
            key=(f'[{who}] ' if who else '')+m.group(1)[:60]
            self.memory.add_fact(key,m.group(1))
            self.speak(f"Got it, I'll remember that{', ' + who if who else ''}."); return True
        m=re.match(r"when i say (.+?), do (.+)",text,re.I)
        if m: self.memory.add_instruction(m.group(1).strip(),m.group(2).strip())
        if m: self.speak(f"Understood — when you say '{m.group(1)}', I'll {m.group(2)}."); return True
        return False

    def _fast_path(self,text):
        # See _FAST_PATH_PATTERNS' module-level comment for the conservatism rationale.
        # fullmatch, not search -- a command embedded in a longer sentence falls through to the
        # LLM rather than risk matching on a fragment (e.g. "don't stop" must never hit 'stop').
        norm=text.strip().rstrip('.!? ')
        norm=re.sub(r'^(?:(?:hey|ok|okay)[\s,]+)?willie[\s,]+','',norm,flags=re.I)
        if _PRIVACY_ON.fullmatch(norm): return {'intent':'privacy_on','args':{},'reply':''}
        if _PRIVACY_OFF.fullmatch(norm): return {'intent':'privacy_off','args':{},'reply':''}
        m=_STEER.fullmatch(norm)
        if m:
            deg=float(m.group(2)) if m.group(2) else config.STEER_OVERRIDE_DEFAULT_DEG
            return {'intent':'steer','args':{'degrees':deg if m.group(1).lower()=='right' else -deg},'reply':''}
        if _STEER_STRAIGHT.fullmatch(norm): return {'intent':'steer','args':{'degrees':0},'reply':''}
        if _TURN_AROUND.fullmatch(norm): return {'intent':'rotate','args':{'degrees':180},'reply':''}
        m=_TURN_DEGREES.fullmatch(norm)
        if m:
            deg=min(360,int(m.group(2)))
            return {'intent':'rotate','args':{'degrees':deg if m.group(1).lower()=='left' else -deg},'reply':''}
        m=_COME_TO_ME.fullmatch(norm)
        if m: return {'intent':'come_to_me','args':{'room':(m.group(1) or m.group(2)).strip().lower()},'reply':''}
        m=_NAME_ROOM.fullmatch(norm)
        if m: return {'intent':'name_room','args':{'room':m.group(1).strip().lower()},'reply':''}
        if _MARK_STAIRS.fullmatch(norm): return {'intent':'mark_stairs','args':{},'reply':''}
        m=_ENROL.fullmatch(norm)
        if m and m.group(1).lower() not in ('the','a','an','it','me','my','that','him','her'):
            return {'intent':'enrol','args':{'name':m.group(1).capitalize()},'reply':''}
        if _FORGET_EVERYONE.fullmatch(norm): return {'intent':'forget_everyone','args':{},'reply':''}
        m=_DEMO_START.fullmatch(norm)
        if m: return {'intent':'demo_start','args':{'name':m.group(1).strip().lower()},'reply':''}
        if _DEMO_STOP.fullmatch(norm): return {'intent':'demo_stop','args':{},'reply':''}
        m=_DEMO_REPLAY.fullmatch(norm)
        if m: return {'intent':'demo_replay','args':{'name':m.group(1).strip().lower()},'reply':''}
        if _TIME_PATTERN.fullmatch(norm):
            return {'intent':'time','args':{},'reply':f"It's {time.strftime('%I:%M %p').lstrip('0')}."}
        if _DATE_PATTERN.fullmatch(norm):
            # tm_mday rather than %-d: that flag is glibc-only, and %d would speak "August oh two".
            d=time.localtime()
            return {'intent':'date','args':{},
                    'reply':f"It's {time.strftime('%A, %B ',d)}{d.tm_mday}."}
        for pattern,name,reply in _FAST_PATH_PATTERNS:
            if pattern.fullmatch(norm):
                return {'intent':name,'args':{},'reply':reply}
        # Last, so a task-directed stop ("stop mapping") is claimed by its own pattern above
        # rather than swallowed as an emergency stop. Everything reaching here is either an
        # emergency stop phrased conversationally, or not a fast-path command at all.
        if is_emergency_stop(norm):
            return {'intent':'stop','args':{},'reply':'Stopping.'}
        return None

    def _interpret_local(self,text):
        # FR-1500-003/§15: parse_success and intent_confidence are independent AIResult signals
        # now, not one masquerading as the other — see ai_provider.py's module docstring. The
        # model is asked to self-report its own confidence rather than confidence being inferred
        # from whether the JSON happened to parse.
        ctx=self.memory.get_context_for(text,person=self.current_person()) if self.memory else {}
        prompt=(f'You are Willie, a home-assistant rover. Known facts: {json.dumps(ctx)}\n'
                f'User said: "{text}"\n'
                f'If the user is asking you to fetch/bring/collect an object -- phrasings like '
                f'"retrieve", "get", "pick up", "grab", or "bring me" the object -- use '
                f'intent "retrieve" with args like {{"object":"newspaper"}}, regardless of which '
                f'of those words they used.\n'
                f'Other recognized intents and example phrasings, always use exactly these names:\n'
                f'"shutdown" -- "shut down", "power off", "go to sleep"\n'
                f'"status" -- "how are you?", "status report", "are you okay?"\n'
                f'"battery" -- "how\'s your battery?", "how much charge left?"\n'
                f'"arm_stow" -- "stow the arm", "put your arm away"\n'
                f'"arm_home" -- "arm home", "reset your arm"\n'
                f'"come_here" -- "come here", "come over here"\n'
                f'"come_to_me" -- "I\'m in the kitchen, come to me" -- args {{"room":"kitchen"}}\n'
                f'"follow" -- "follow me", "keep following me"\n'
                f'"diagnostics" -- "run diagnostics", "self test"\n'
                f'"where_are_you" -- "where are you?", "what room is this?"\n'
                f'"what_do_you_see" -- "what do you see?", "what\'s in front of you?"\n'
                f'"wave" -- "wave hello", "say hi", "give a wave"\n'
                f'"stop" -- "stop", "halt", "freeze"\n'
                f'Reply with one JSON object and nothing else. It must ALWAYS contain all four keys '
                f'\"intent\", \"args\", \"reply\" and \"confidence\" -- never leave one out.\n'
                f'Give args an object name ONLY for \"retrieve\" and a room ONLY for \"come_to_me\"; for every other intent '
                f'args must be exactly {{}}. Never output angle brackets or placeholder text.\n'
                f'Example: {{\"intent\":\"retrieve\",\"args\":{{\"object\":\"newspaper\"}},'
                f'\"reply\":\"On my way to get the newspaper.\",\"confidence\":0.9}}\n'
                f'Example: {{\"intent\":\"battery\",\"args\":{{}},'
                f'\"reply\":\"I am at 80 percent.\",\"confidence\":0.9}}')
        result=self._local_ai.ask_sync(prompt,schema=_INTENT_SCHEMA)
        if not result.parse_success:
            log.info(f'Local interpretation low-confidence/failed: {result.reason}')
            return result.payload,0.0
        name=(result.payload or {}).get('intent','')
        if name not in _ACTIONABLE_INTENTS:
            log.info(f'Local interpretation named an unknown intent {name!r} -- treating as not understood')
            return result.payload,0.0
        words=_SENSOR_INTENT_WORDS.get(name)
        if words and not any(w in text.lower() for w in words):
            log.info(f'Local model said {name!r} for "{text}" with none of its words -- not understood')
            return result.payload,0.0
        log.info(f'Local model intent: {name!r} ({result.intent_confidence})')
        return result.payload,result.intent_confidence

    def _act_on_intent(self,intent,original_text):
        reply=intent.get('reply','') if intent else ''
        name=(intent or {}).get('intent',''); args=(intent or {}).get('args',{})
        # 2026-10-08, live: "How is your battery?" missed the fixed phrases, went to the Hailo
        # model, and Willie said the model's own reply -- "I am at 80%" -- then brain's real
        # answer, "I can't read my battery right now". The model cannot know sensor facts. For
        # intents brain.py answers from his sensors, drop any reply that is not one of the fast
        # path's fixed acknowledgements; brain speaks the real answer.
        if name in _SENSOR_ANSWERED and reply not in _NEUTRAL_ACKS: reply=''
        if name=='stop':
            # Immediate, not queued — see stop_requested's docstring in __init__. brain.py's tick
            # thread picks this up and does the actual emergency_stop()/task-abort work; nothing
            # here touches SafetyController directly.
            self.stop_requested.set()
            if reply: self.speak(reply,tone=getattr(self,'_reply_tone',config.VOICE_TONE_DEFAULT))
            return
        # confirm_receipt doesn't move/reply anything itself, but still has to cross to the tick
        # thread via this same queue — retrieval_task.py's AWAIT_CONFIRM state (and brain.py's
        # new shutdown confirmation, see _drain_voice_commands) are the consumers. status/battery/
        # where_are_you/what_do_you_see/diagnostics/arm_stow/arm_home/wave/come_here/follow/
        # shutdown all need state voice.py doesn't have (battery volts, FSM state, pose, camera,
        # arm) — brain.py is what answers/executes them, same "queued, brain.py is the sole
        # consumer" rule as every motion intent.
        motion_intents={'forward','reverse','turn_left','turn_right','go_to','retrieve',
                         'confirm_receipt','map','stop_map','shutdown','status','battery',
                         'arm_stow','arm_home','wave','come_here','come_to_me','rotate','steer','roam','follow','diagnostics','check_logs',
                         'where_are_you','what_do_you_see','what_doing','privacy_on','privacy_off','name_room','mark_stairs',
                         'demo_start','demo_stop','demo_replay','enrol','forget_everyone'}
        if name in motion_intents:
            # FR-1500-007: queued only — brain.py applies full Directive 1-5 gating before this
            # is ever executed.
            self.pending_commands.put({'source':'voice','intent':name,'args':args,
                                        'text':original_text,'ts':time.time()})
        elif name=='smart_home' and self.smart_home is not None:
            # Non-motion — FR-1300 doesn't need brain.py's motion gating, handled directly here.
            ok,msg=self.smart_home.send_command(args.get('entity_id',''),args.get('command','on'),
                                                 **{k:v for k,v in args.items() if k not in('entity_id','command')})
            if not reply: reply=msg
        if reply: self.speak(reply,tone=getattr(self,'_reply_tone',config.VOICE_TONE_DEFAULT))

    def speak(self,text,tone='neutral'):
        # FR-1500-004 + FR-1500-010: force neutral tone for anything safety-shaped, regardless
        # of what the caller asked for. Non-blocking — safe to call from brain.py's tick thread
        # (see module docstring); actual synthesis happens on _speaker_loop's own thread.
        if _SAFETY_PATTERN.search(text): tone='neutral'
        if self.display: self.display.update_state(state='speak',status=text)
        if not self._enabled:
            log.info(f'(voice disabled) would say: {text}'); return
        timing=self._utterance_timing; self._utterance_timing=None
        self._speak_queue.put((text,timing,tone))

    def speak_safety(self,text):
        # FR-1500-010: the only entry point brain.py's safety paths should use — always neutral,
        # never routed through personality logic at all. Also non-blocking, same as speak().
        if not self._enabled:
            log.info(f'(voice disabled) would say: {text}'); return
        self._speak_queue.put((text,None,'neutral'))

    @staticmethod
    def _piper_subprocess(text,wav_path,scale):
        """The original path: one `piper` process per reply. Kept as PiperEngine's fallback."""
        model=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.PIPER_VOICE_PATH)
        # `piper` is a venv-installed console script (venv/bin/piper) -- willy-rover.service sets
        # no PATH, so resolve it next to the running interpreter rather than trusting PATH.
        piper_bin=os.path.join(os.path.dirname(sys.executable),'piper')
        cmd=[piper_bin,'--model',model,'--output_file',wav_path]
        try:
            subprocess.run(cmd+(['--length_scale',str(scale)] if scale!=1.0 else []),
                           input=text.encode(),capture_output=True,timeout=10,check=True)
        except subprocess.CalledProcessError:
            if scale==1.0: raise
            # A Piper build that rejects the flag must cost the tone, never the speech.
            log.warning('piper rejected --length_scale; speaking in the neutral tone')
            subprocess.run(cmd,input=text.encode(),capture_output=True,timeout=10,check=True)

    def _synthesize_and_play(self,text,timing=None,tone='neutral'):
        # Only ever called from _speaker_loop's own thread — never call this directly.
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav',delete=False) as f: wav_path=f.name
            model=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.PIPER_VOICE_PATH)
            # `piper` is a venv-installed console script (venv/bin/piper) — willy-rover.service
            # sets no PATH, and systemd's default minimal PATH doesn't include venv/bin, so a
            # bare 'piper' lookup fails FileNotFoundError under the actual live service (caught
            # below, so it fails silent — no speech, no crash, no obvious clue why). Resolve it
            # next to the interpreter actually running this process instead of trusting PATH.
            scale=_TONE_LENGTH_SCALE.get(tone,1.0)
            if self._tts is None:
                self._tts=PiperEngine(model,self._piper_subprocess)
            self._tts.synthesize(text,wav_path,scale)
            if timing is not None:
                # Voice latency handoff 2026-08-15 Step 0: logged right after synthesis, before
                # aplay/pw-play, so this bucket reflects piper compute cost rather than the
                # reply's spoken-audio duration (which scales with reply length, not latency).
                t_wake,t_stt,t_intent=timing; t_tts=time.time()
                log.info('voice timing: stt=%.1fs intent=%.1fs tts=%.1fs (%s) total=%.1fs',
                          t_stt-t_wake,t_intent-t_stt,t_tts-t_intent,self._tts.last_path,t_tts-t_wake)
            # aplay opens ALSA directly, which conflicts with pipewire holding the USB
            # card exclusively under this user session (confirmed 2026-08-15: bare aplay
            # fails with "Device or resource busy", caught here as a silent no-op).
            # pw-play goes through pipewire instead and reaches the same default sink.
            env=speech_envelope(wav_path,config.MOUTH_TALK_STEP_S) if config.ENABLE_TALKING_MOUTH else None
            if env and self.display is not None:
                try: self.display.set_talking(env,config.MOUTH_TALK_STEP_S)   # FR-1600-009
                except Exception: log.warning('talking mouth unavailable',exc_info=True)
            subprocess.run(['pw-play',wav_path],capture_output=True,timeout=15)
        except Exception as e:
            log.warning(f'TTS playback failed: {e}')
        finally:
            if self.display is not None:
                try: self.display.stop_talking()
                except Exception: pass
            try: os.remove(wav_path)
            except OSError: pass
