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
_FAST_PATH_PATTERNS=[
    # --- tier 2: motion / destructive, narrow cores ---
    (_fp(r'stop|halt|freeze|hold (it|on|up)|stop moving|stand still|whoa'),'stop','Stopping.'),
    (_fp(r'(?:go |move |drive )?forward'),'forward','Going forward.'),
    (_fp(r'(?:go |move |drive )?(?:reverse|backward|back up)'),'reverse','Backing up.'),
    (_fp(r'turn left'),'turn_left','Turning left.'),
    (_fp(r'turn right'),'turn_right','Turning right.'),
    (_fp(r'shut down|power off|go to sleep'),'shutdown',''),
    # --- tier 1: speech-only, widened ---
    (_fp(r"(?:how'?s|hows|what'?s|whats|check) (?:your |the )?battery(?: (?:level|status|at|doing))?|"
         r"battery (?:status|level|check)|how much (?:charge|battery|power)(?: (?:left|is left|do you have))?|"
         r"are you charged"),'battery','Checking.'),
    (_fp(r'status(?: report)?|how are you(?: doing| feeling)?|are you (?:ok|okay|alright|good)|'
         r"what'?s your status|report"),'status','Checking.'),
    (_fp(r'where are you|what room (?:is this|are you in)|which room (?:is this|are you in)|'
         r"where(?:'?s| is) this|do you know where you are"),'where_are_you','Checking.'),
    (_fp(r'what (?:do|can) you see|what'r"'"r's (?:in front of you|out there|there)|'
         r'look around|describe what you see|tell me what you see'),'what_do_you_see','Looking.'),
    (_fp(r'wave(?: hello| hi| at me)?|say (?:hi|hello)|give (?:me )?a wave'),'wave',''),
    (_fp(r'stow (?:the|your) arm|put your arm away|arm away'),'arm_stow','Stowing the arm.'),
    (_fp(r'arm home|reset your arm|home (?:the|your) arm'),'arm_home','Homing the arm.'),
    (_fp(r'(?:start|begin) (?:mapping|the map)|map this room|start mapping this room'),
     'map','Starting the map.'),
    (_fp(r'(?:stop|end|finish) (?:mapping|the map)'),'stop_map','Stopping the map.'),
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
        while self._running:
            try: text,timing=self._speak_queue.get(timeout=0.5)
            except queue.Empty: continue
            self._speaking.set()
            try: self._synthesize_and_play(text,timing)
            finally:
                self._play_done()  # owner-requested: signals Willy has finished and is listening
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

    def _loop(self):
        import sounddevice as sd
        frame_len=1280  # openwakeword expects 80ms @16kHz frames
        try:
            with sd.InputStream(samplerate=16000,channels=1,dtype='int16',
                                 device=config.AUDIO_INPUT_DEVICE,blocksize=frame_len) as stream:
                while self._running:
                    if not privacy.mic_enabled():
                        time.sleep(1.0); continue  # FR-1800-005, re-checked continuously
                    frame,_=stream.read(frame_len)
                    if self._speaking.is_set():
                        continue  # still drain the buffer, just don't score our own echo
                    flat=frame.flatten()
                    self._update_noise(flat)
                    scores=self._wakeword.predict(flat)
                    if max(scores.values(),default=0.0)>=config.WAKEWORD_THRESHOLD:
                        self._handle_wake(stream,frame_len,time.time())
        except Exception as e:
            log.error(f'Voice input stream failed, pipeline stopping: {e}')
            self._running=False

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

    def _handle_wake(self,stream,frame_len,t_wake):
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
            f,_=stream.read(frame_len); s=f.flatten(); audio.append(s)
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
        self._process_utterance(pcm,t_wake)

    def _process_utterance(self,pcm,t_wake):
        # FR-1500-002: onboard STT, no cloud dependency. Also satisfies FR-1800-001 (raw
        # audio never transmitted off-device): cloud_ai.ask_sync() below is only ever given
        # already-transcribed text, never the PCM buffer, so no cloud fallback path exists that
        # would need to send raw audio in the first place.
        segments,_=self._whisper.transcribe(pcm,language='en',beam_size=1,vad_filter=True)
        text=' '.join(s.text for s in segments).strip()
        t_stt=time.time()
        if not text:
            self.speak("How can I help?"); return
        log.info(f'Heard: "{text}"')
        if self.display: self.display.note_heard()

        # FR-1900-006: explicit teaching commands short-circuit interpretation, handled locally.
        if self.memory and self._maybe_learn(text): return

        fast=self._fast_path(text)
        if fast is not None:
            t_intent=time.time()
            self._utterance_timing=(t_wake,t_stt,t_intent)
            log.info(f'Fast-path matched: "{text}" -> {fast["intent"]}')
            self._act_on_intent(fast,text); return

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
                    self.speak(result.payload,tone=config.VOICE_TONE_DEFAULT); return
            # FR-1500-005: never guess and act.
            self.speak("I'm not confident I understood that — could you rephrase it?"); return
        self._act_on_intent(intent,text)

    def _maybe_learn(self,text):
        m=re.match(r"remember that (.+)",text,re.I)
        if m: self.memory.add_fact(m.group(1)[:60],m.group(1)); self.speak(f"Got it, I'll remember that."); return True
        m=re.match(r"when i say (.+?), do (.+)",text,re.I)
        if m: self.memory.add_instruction(m.group(1).strip(),m.group(2).strip())
        if m: self.speak(f"Understood — when you say '{m.group(1)}', I'll {m.group(2)}."); return True
        return False

    def _fast_path(self,text):
        # See _FAST_PATH_PATTERNS' module-level comment for the conservatism rationale.
        # fullmatch, not search -- a command embedded in a longer sentence falls through to the
        # LLM rather than risk matching on a fragment (e.g. "don't stop" must never hit 'stop').
        norm=text.strip().rstrip('.!? ')
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
        return None

    def _interpret_local(self,text):
        # FR-1500-003/§15: parse_success and intent_confidence are independent AIResult signals
        # now, not one masquerading as the other — see ai_provider.py's module docstring. The
        # model is asked to self-report its own confidence rather than confidence being inferred
        # from whether the JSON happened to parse.
        ctx=self.memory.get_context_for(text) if self.memory else {}
        prompt=(f'You are Willie, a home-assistant rover. Known facts: {json.dumps(ctx)}\n'
                f'User said: "{text}"\n'
                f'If the user is asking you to fetch/bring/collect an object -- phrasings like '
                f'"retrieve", "get", "pick up", "grab", or "bring me" the object -- use '
                f'intent "retrieve" with args {{"object":"<the object>"}}, regardless of which '
                f'of those words they used.\n'
                f'Other recognized intents and example phrasings, always use exactly these names:\n'
                f'"shutdown" -- "shut down", "power off", "go to sleep"\n'
                f'"status" -- "how are you?", "status report", "are you okay?"\n'
                f'"battery" -- "how\'s your battery?", "how much charge left?"\n'
                f'"arm_stow" -- "stow the arm", "put your arm away"\n'
                f'"arm_home" -- "arm home", "reset your arm"\n'
                f'"come_here" -- "come here", "come over here"\n'
                f'"follow" -- "follow me", "keep following me"\n'
                f'"diagnostics" -- "run diagnostics", "self test"\n'
                f'"where_are_you" -- "where are you?", "what room is this?"\n'
                f'"what_do_you_see" -- "what do you see?", "what\'s in front of you?"\n'
                f'"wave" -- "wave hello", "say hi", "give a wave"\n'
                f'"stop" -- "stop", "halt", "freeze"\n'
                f'Respond ONLY with JSON: '
                f'{{"intent":"<short action name>","args":{{}},"reply":"<what to say back, <200 chars>",'
                f'"confidence":<0.0-1.0, how sure you are of this interpretation>}}')
        result=self._local_ai.ask_sync(prompt,schema=_INTENT_SCHEMA)
        if not result.parse_success:
            log.info(f'Local interpretation low-confidence/failed: {result.reason}')
        return result.payload,result.intent_confidence

    def _act_on_intent(self,intent,original_text):
        reply=intent.get('reply','') if intent else ''
        name=(intent or {}).get('intent',''); args=(intent or {}).get('args',{})
        if name=='stop':
            # Immediate, not queued — see stop_requested's docstring in __init__. brain.py's tick
            # thread picks this up and does the actual emergency_stop()/task-abort work; nothing
            # here touches SafetyController directly.
            self.stop_requested.set()
            if reply: self.speak(reply,tone=config.VOICE_TONE_DEFAULT)
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
                         'arm_stow','arm_home','wave','come_here','follow','diagnostics',
                         'where_are_you','what_do_you_see'}
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
        if reply: self.speak(reply,tone=config.VOICE_TONE_DEFAULT)

    def speak(self,text,tone='neutral'):
        # FR-1500-004 + FR-1500-010: force neutral tone for anything safety-shaped, regardless
        # of what the caller asked for. Non-blocking — safe to call from brain.py's tick thread
        # (see module docstring); actual synthesis happens on _speaker_loop's own thread.
        if _SAFETY_PATTERN.search(text): tone='neutral'
        if self.display: self.display.update_state(state='speak',status=text)
        if not self._enabled:
            log.info(f'(voice disabled) would say: {text}'); return
        timing=self._utterance_timing; self._utterance_timing=None
        self._speak_queue.put((text,timing))

    def speak_safety(self,text):
        # FR-1500-010: the only entry point brain.py's safety paths should use — always neutral,
        # never routed through personality logic at all. Also non-blocking, same as speak().
        if not self._enabled:
            log.info(f'(voice disabled) would say: {text}'); return
        self._speak_queue.put((text,None))

    def _synthesize_and_play(self,text,timing=None):
        # Only ever called from _speaker_loop's own thread — never call this directly.
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav',delete=False) as f: wav_path=f.name
            model=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.PIPER_VOICE_PATH)
            # `piper` is a venv-installed console script (venv/bin/piper) — willy-rover.service
            # sets no PATH, and systemd's default minimal PATH doesn't include venv/bin, so a
            # bare 'piper' lookup fails FileNotFoundError under the actual live service (caught
            # below, so it fails silent — no speech, no crash, no obvious clue why). Resolve it
            # next to the interpreter actually running this process instead of trusting PATH.
            piper_bin=os.path.join(os.path.dirname(sys.executable),'piper')
            subprocess.run([piper_bin,'--model',model,'--output_file',wav_path],
                            input=text.encode(),capture_output=True,timeout=10,check=True)
            if timing is not None:
                # Voice latency handoff 2026-08-15 Step 0: logged right after synthesis, before
                # aplay/pw-play, so this bucket reflects piper compute cost rather than the
                # reply's spoken-audio duration (which scales with reply length, not latency).
                t_wake,t_stt,t_intent=timing; t_tts=time.time()
                log.info('voice timing: stt=%.1fs intent=%.1fs tts=%.1fs total=%.1fs',
                          t_stt-t_wake,t_intent-t_stt,t_tts-t_intent,t_tts-t_wake)
            # aplay opens ALSA directly, which conflicts with pipewire holding the USB
            # card exclusively under this user session (confirmed 2026-08-15: bare aplay
            # fails with "Device or resource busy", caught here as a silent no-op).
            # pw-play goes through pipewire instead and reaches the same default sink.
            subprocess.run(['pw-play',wav_path],capture_output=True,timeout=15)
        except Exception as e:
            log.warning(f'TTS playback failed: {e}')
        finally:
            try: os.remove(wav_path)
            except OSError: pass
