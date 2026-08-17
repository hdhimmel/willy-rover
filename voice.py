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
_FAST_PATH_PATTERNS=[
    (re.compile(r'stop|halt|freeze',re.I),'stop','Stopping.'),
    (re.compile(r'(go |move |drive )?forward',re.I),'forward','Going forward.'),
    (re.compile(r'(go |move |drive )?(reverse|backward|back up)',re.I),'reverse','Backing up.'),
    (re.compile(r'turn left',re.I),'turn_left','Turning left.'),
    (re.compile(r'turn right',re.I),'turn_right','Turning right.'),
    (re.compile(r"how'?s your battery|battery status|battery level|how much charge( left)?",re.I),
     'battery','Checking.'),
    (re.compile(r'status report|how are you|are you (ok|okay)|status',re.I),'status','Checking.'),
    (re.compile(r'where are you|what room (is this|are you in)',re.I),'where_are_you','Checking.'),
    (re.compile(r'stow the arm|put your arm away|stow your arm',re.I),'arm_stow','Stowing the arm.'),
    (re.compile(r'arm home|reset your arm|home your arm',re.I),'arm_home','Homing the arm.'),
    (re.compile(r'start mapping|begin mapping|map this room|start the map',re.I),'map','Starting the map.'),
    (re.compile(r'stop mapping|end mapping|finish mapping|stop the map',re.I),'stop_map','Stopping the map.'),
    (re.compile(r'shut down|power off|go to sleep',re.I),'shutdown',''),
    (re.compile(r'run diagnostics|self test|run a self test|run self test',re.I),'diagnostics',''),
]

_TIME_PATTERN=re.compile(r"what'?s the time|what is the time|what time is it|current time|do you (know|have) (what )?the time( it is)?",re.I)

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
            self._whisper=WhisperModel(config.WHISPER_MODEL_SIZE,device='cpu',compute_type='int8',
                                        local_files_only=True)
            self._local_ai=LocalAIProvider()  # §14 -- was a bare Llama(...) instance here
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
                time.sleep(0.6)  # let speaker-to-mic echo decay before wake scoring resumes
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
                    scores=self._wakeword.predict(frame.flatten())
                    if max(scores.values(),default=0.0)>=config.WAKEWORD_THRESHOLD:
                        self._handle_wake(stream,frame_len,time.time())
        except Exception as e:
            log.error(f'Voice input stream failed, pipeline stopping: {e}')
            self._running=False

    def _handle_wake(self,stream,frame_len,t_wake):
        # FR-1500-001 satisfied (wake word seen) — now capture an utterance and process it.
        # Kept simple: fixed-length capture window rather than VAD-based endpointing.
        if self.display: self.display.update_state(state='listening',status='Listening...')
        audio=[]
        for _ in range(int(4.0*16000/frame_len)):  # ~4s window
            f,_=stream.read(frame_len); audio.append(f.flatten())
        pcm=np.concatenate(audio).astype(np.float32)/32768.0
        if self.display: self.display.update_state(state='processing',status='Thinking...')
        self._process_utterance(pcm,t_wake)

    def _process_utterance(self,pcm,t_wake):
        # FR-1500-002: onboard STT, no cloud dependency.
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
