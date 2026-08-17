import json,os,math,threading,queue,urllib.request,urllib.error,config,logsetup
from abc import ABC,abstractmethod
from logsetup import log_event
log=logsetup.setup('ai_provider')

# §14/§15 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: one AIProvider abstraction over
# what used to be three separate, un-unified AI call sites -- claude_client.py::ClaudeClient
# (motion-decision JSON, brain.py's STUCK state), cloud_ai.py::CloudAIClient (free-text fallback,
# voice.py), and a bare llama_cpp.Llama instance inlined directly in voice.py::_interpret_local().
# The first two independently POSTed to the same Anthropic endpoint with duplicated transport
# code. "The rest of Willy should not care which model is used" (§14): callers pass a
# prompt/system/schema, get back a structured AIResult regardless of which provider answered.
#
# §15's named anti-pattern -- "do not use 'valid JSON' as AI confidence" -- is what AIResult
# fixes: parse_success (did the response structurally validate against the expected schema) and
# intent_confidence (a value the prompt itself asks the model to self-report) are two independent
# signals, not one standing in for the other the way voice.py's old hardcoded 0.8/0.0 did.
# action_confidence is a THIRD, separately *computed* signal, only meaningful for motion-decision
# queries: is the specific action/duration/speed structurally sane. None of this is the actual
# safety gate -- safety.py::SafetyController.approve_motion() is unchanged and remains the sole
# authority over what the rover is allowed to do; safety_validation here reflects only whether
# *this AI response* was structurally plausible enough to act on, not a real physical-safety check.

_MOTION_ACTIONS={'forward','reverse','turn_left','turn_right','stop','wait'}
_ANTHROPIC_URL='https://api.anthropic.com/v1/messages'

class AIResult:
    __slots__=('parse_success','intent_confidence','action_confidence','safety_validation','payload','reason')
    def __init__(self,parse_success,intent_confidence,action_confidence,safety_validation,payload,reason=''):
        self.parse_success=parse_success; self.intent_confidence=intent_confidence
        self.action_confidence=action_confidence; self.safety_validation=safety_validation
        self.payload=payload; self.reason=reason
    def __repr__(self):
        return (f'AIResult(parse_success={self.parse_success},intent_confidence={self.intent_confidence},'
                f'action_confidence={self.action_confidence},safety_validation={self.safety_validation},'
                f'reason={self.reason!r})')

def _validate_schema(parsed,schema):
    """Pure function: does parsed (a dict) have every key in schema with a matching type? schema
    values are a type or a tuple of types, matching isinstance()'s second-argument shape."""
    if not isinstance(parsed,dict): return False
    return all(key in parsed and isinstance(parsed[key],types) for key,types in schema.items())

def _clamp01(x,default=0.3):
    # Deliberately low default (not 0.5) so a model that doesn't self-report a confidence field at
    # all reads as uncertain rather than silently "average" -- matches §15's spirit that absence
    # of a real signal should not be treated as a good one.
    try: return max(0.0,min(1.0,float(x)))
    except(TypeError,ValueError): return default

def _action_confidence(payload):
    """Structural plausibility only -- NOT the safety gate, see module docstring. 1.0 if the
    action name is recognized and duration/speed (when present) are non-negative and within a
    generous multiple of the real clamp (safety.py enforces the actual, tighter limit regardless
    of this result)."""
    if payload.get('action') not in _MOTION_ACTIONS: return 0.0
    dur=payload.get('duration'); spd=payload.get('speed')
    if dur is not None and not(isinstance(dur,(int,float)) and 0<=dur<=config.MAX_COMMAND_DURATION_S*4):
        return 0.0
    if spd is not None and not(isinstance(spd,(int,float)) and 0<=spd<=1.0):
        return 0.0
    return 1.0

def _parse_response(txt,schema):
    """Pure function: raw model output text + an optional schema -> AIResult. schema=None means
    treat the response as free text (cloud_ai.py's old behavior) -- no JSON parsing attempted,
    parse_success trivially True since there's nothing to fail to parse."""
    if schema is None:
        return AIResult(True,1.0,None,True,txt,'')
    try:
        if txt.startswith('```'):
            txt=txt.split('```')[1]
            if txt.startswith('json'): txt=txt[4:]
        parsed=json.loads(txt[txt.index('{'):txt.rindex('}')+1])
    except Exception as e:
        return AIResult(False,0.0,None,False,None,f'parse failed: {e}')
    if not _validate_schema(parsed,schema):
        return AIResult(False,0.0,None,False,parsed,'schema validation failed')
    intent_confidence=_clamp01(parsed.get('confidence'))
    action_conf=_action_confidence(parsed) if 'action' in schema else None
    safety_validation=(action_conf is None) or (action_conf>=1.0)
    return AIResult(True,intent_confidence,action_conf,safety_validation,parsed,'')

def build_world_state(world_model,goal=None,battery=None,**extra):
    """§14's required world-state schema, assembled from real world_model.py (§9) data instead of
    raw sensor values. **extra merges in caller-specific fields (e.g. brain.py's STUCK state adds
    stuck_count/last_action/front_cm/etc, which aren't part of §14's general schema but are
    specific to that one decision point)."""
    pose=world_model.get_robot_pose()
    room=world_model.get_room(pose.x,pose.y)
    nearby_obstacles=world_model.get_nearby_obstacles(pose.x,pose.y,config.AI_NEARBY_RADIUS_M)
    nearby_objects=[o for o in world_model.get_objects()
                     if math.hypot(o.x-pose.x,o.y-pose.y)<=config.AI_NEARBY_RADIUS_M]
    state={'robot':{'room':room.name if room else None,
                     'pose':{'x':round(pose.x,2),'y':round(pose.y,2),'heading':round(pose.heading,3)},
                     'battery':battery},
           'goal':goal,
           'nearby_objects':[{'cls':o.cls,'x':round(o.x,2),'y':round(o.y,2)} for o in nearby_objects],
           'nearby_obstacles':[{'x':round(ob.x,2),'y':round(ob.y,2)} for ob in nearby_obstacles],
           'available_routes':[r.name for r in world_model.all_routes()]}
    state.update(extra)
    return state

class AIProvider(ABC):
    # Owns the non-blocking worker-thread plumbing (moved from the old claude_client.py,
    # unchanged in shape -- request_async/poll_async/reset_async are exactly
    # request_decision/poll_decision/reset renamed) plus a synchronous ask_sync() path for
    # callers already off the tick thread (voice.py, matching cloud_ai.py's old documented
    # contract: "callers MUST invoke it off brain.py's main tick thread").
    def __init__(self):
        self._in_q=queue.Queue(maxsize=1); self._out_q=queue.Queue(maxsize=1)
        self._busy=False  # only ever touched from the caller's own thread
        threading.Thread(target=self._worker,daemon=True).start()

    @property
    @abstractmethod
    def available(self): ...

    @abstractmethod
    def _call(self,prompt,system=None,schema=None,history=None):
        """Blocking. Subclass-implemented. Returns an AIResult. Runs on the worker thread when
        reached via request_async/poll_async, or directly on the caller's thread via ask_sync."""

    def _worker(self):
        while True:
            prompt,system,schema,history=self._in_q.get()
            result=self._call(prompt,system,schema,history)
            try: self._out_q.get_nowait()  # drop a stale unread result, if any
            except queue.Empty: pass
            self._out_q.put(result)

    def request_async(self,prompt,system=None,schema=None,history=None):
        """Non-blocking. Submits a request if the worker isn't already busy with one. Returns
        True if submitted, False if a request is already in flight (caller should keep polling
        poll_async() rather than submit a second overlapping request)."""
        if self._busy: return False
        self._busy=True; self._in_q.put((prompt,system,schema,history)); return True

    def poll_async(self):
        """Non-blocking. Returns the AIResult once the worker finishes, else None."""
        try: result=self._out_q.get_nowait()
        except queue.Empty: return None
        self._busy=False; return result

    def reset_async(self):
        """Call when an in-flight request is abandoned (e.g. a tilt/battery/sensor fault
        pre-empts brain.py's STUCK state) before its result was ever polled -- otherwise _busy
        stays True forever and every future request_async() silently refuses to submit. Doesn't
        cancel an in-flight HTTP call (not cheaply cancellable via urllib), just drops its result
        and frees the provider to accept a new request."""
        try: self._out_q.get_nowait()
        except queue.Empty: pass
        self._busy=False

    def ask_sync(self,prompt,system=None,schema=None,history=None):
        """Blocking, on the caller's own thread -- no queue involved. Only for callers already
        off the tick thread (voice.py)."""
        return self._call(prompt,system,schema,history)

class CloudAIProvider(AIProvider):
    # Unifies claude_client.py + cloud_ai.py's independent, duplicated Anthropic clients into one.
    # Conversation history (for the STUCK motion-decision use case) is deliberately NOT owned
    # here -- it's threaded through by the caller on each call instead. A single CloudAIProvider
    # instance serves both brain.py's stateful STUCK use and voice.py's stateless free-text
    # fallback use; an internally-owned history buffer would leak unrelated voice Q&A turns into
    # the motion-decision conversation (or vice versa) since both go through the same instance.
    def __init__(self):
        self._enabled=config.ENABLE_CLOUD_AI
        self._key=os.environ.get('ANTHROPIC_API_KEY','')
        if self._enabled and not self._key:
            log.warning('ANTHROPIC_API_KEY not set — cloud AI stays disabled.')
            self._enabled=False
        super().__init__()

    @property
    def available(self): return self._enabled and bool(self._key)

    def _post_anthropic(self,system,messages):
        payload={'model':config.CLAUDE_MODEL,'max_tokens':config.CLAUDE_MAX_TOKENS,
                  'thinking':{'type':'disabled'},'messages':messages}
        if system: payload['system']=system
        req=urllib.request.Request(_ANTHROPIC_URL,data=json.dumps(payload).encode(),
            headers={'x-api-key':self._key,'anthropic-version':'2023-06-01','content-type':'application/json'},
            method='POST')
        with urllib.request.urlopen(req,timeout=config.CLOUD_AI_TIMEOUT_S) as r:
            return json.loads(r.read())['content'][0]['text'].strip()

    def _call(self,prompt,system=None,schema=None,history=None):
        if not self.available:
            log_event(log,'AI_UNAVAILABLE',severity='info',subsystem='ai_provider',provider='cloud')
            return AIResult(False,0.0,None,False,None,'cloud AI not configured/enabled')
        log_event(log,'AI_REQUEST',severity='info',subsystem='ai_provider',provider='cloud')
        messages=(history or [])+[{'role':'user','content':prompt}]
        try:
            txt=self._post_anthropic(system,messages)
        except Exception as e:
            if isinstance(e,TimeoutError):  # §21: urllib raises socket.timeout, a TimeoutError subclass/alias
                log_event(log,'AI_TIMEOUT',severity='warning',subsystem='ai_provider',
                          provider='cloud',timeout_s=config.CLOUD_AI_TIMEOUT_S)
            else:
                log.info(f'Cloud AI call failed (expected if offline/quota): {type(e).__name__}: {e}')
            return AIResult(False,0.0,None,False,None,f'{type(e).__name__}: {e}')
        result=_parse_response(txt,schema)
        if not result.parse_success:
            log_event(log,'AI_REJECTED',severity='warning',subsystem='ai_provider',
                      provider='cloud',reason=result.reason)
        else:
            log_event(log,'AI_RESULT',severity='info',subsystem='ai_provider',provider='cloud',
                      intent_confidence=result.intent_confidence,action_confidence=result.action_confidence)
        return result

class LocalAIProvider(AIProvider):
    # Wraps llama_cpp.Llama, moved out of voice.py's __init__/_load_models() so it goes through
    # the same AIResult/schema/confidence machinery CloudAIProvider does.
    def __init__(self):
        self._enabled=False; self._llm=None
        model_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.LOCAL_LLM_MODEL_PATH)
        if os.path.exists(model_path):
            try:
                from llama_cpp import Llama
                self._llm=Llama(model_path=model_path,n_ctx=2048,n_threads=4,verbose=False)
                self._enabled=True
            except Exception as e:
                log.error(f'Local LLM load failed, staying disabled: {e}')
        super().__init__()

    @property
    def available(self): return self._enabled

    def _call(self,prompt,system=None,schema=None,history=None):
        # history unused -- local interpretation is single-turn, same as the code this replaces.
        if not self.available:
            log_event(log,'AI_UNAVAILABLE',severity='info',subsystem='ai_provider',provider='local')
            return AIResult(False,0.0,None,False,None,'local LLM not loaded')
        log_event(log,'AI_REQUEST',severity='info',subsystem='ai_provider',provider='local')
        # Raw completion (bare self._llm(...)) on an instruct-tuned model was unreliable: no
        # chat template meant it sometimes echoed the instruction text back verbatim instead of
        # filling it in, or hit the '\n\n' stop sequence almost immediately and returned nothing
        # at all -- confirmed 2026-08-15 as the actual cause of the near-100% local parse-failure
        # rate (every request paying full local-inference latency for nothing, always falling
        # back to cloud). create_chat_completion applies the model's real system/user template.
        messages=([{'role':'system','content':system}] if system else [])+[{'role':'user','content':prompt}]
        try:
            out=self._llm.create_chat_completion(messages=messages,max_tokens=200)
            txt=out['choices'][0]['message']['content'].strip()
        except Exception as e:
            log.info(f'Local LLM call failed: {type(e).__name__}: {e}')
            return AIResult(False,0.0,None,False,None,f'{type(e).__name__}: {e}')
        result=_parse_response(txt,schema)
        if not result.parse_success:
            log_event(log,'AI_REJECTED',severity='warning',subsystem='ai_provider',
                      provider='local',reason=result.reason)
        else:
            log_event(log,'AI_RESULT',severity='info',subsystem='ai_provider',provider='local',
                      intent_confidence=result.intent_confidence,action_confidence=result.action_confidence)
        return result
