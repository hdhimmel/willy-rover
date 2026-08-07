import json,urllib.request,urllib.error,os,threading,queue,config,logsetup
log=logsetup.setup('claude_client')
SYSTEM="""You are the brain of WildWilly, a 6-wheel autonomous rover.
Respond ONLY with JSON: {"action":"forward"|"reverse"|"turn_left"|"turn_right"|"stop"|"wait","duration":<float>,"speed":<0.0-1.0>,"reason":"<60 chars"}
Safety: never forward if front<15cm. Stop if tilt>22deg."""

class ClaudeClient:
    # §2 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: no HTTP call may run on brain.py's
    # tick thread. The actual API call (_call, below) only ever runs on the background _worker
    # thread; request_decision()/poll_decision() are the non-blocking interface brain.py's
    # _stuck() polls instead of blocking on.
    def __init__(self):
        self._key=os.environ.get('ANTHROPIC_API_KEY',''); self._history=[]
        self._in_q=queue.Queue(maxsize=1); self._out_q=queue.Queue(maxsize=1)
        self._busy=False  # only ever touched from the caller's thread (brain.py's tick thread)
        threading.Thread(target=self._worker,daemon=True).start()

    def _worker(self):
        while True:
            situation=self._in_q.get()
            action=self._call(situation)
            try: self._out_q.get_nowait()  # drop a stale unread result, if any
            except queue.Empty: pass
            self._out_q.put(action)

    def request_decision(self,situation):
        """Non-blocking. Submits a decision request if the worker isn't already busy with one.
        Returns True if submitted, False if a request is already in flight (caller should keep
        polling poll_decision() rather than submit a second overlapping request)."""
        if self._busy: return False
        self._busy=True; self._in_q.put(situation); return True

    def poll_decision(self):
        """Non-blocking. Returns the decided action dict once the worker finishes, else None."""
        try: action=self._out_q.get_nowait()
        except queue.Empty: return None
        self._busy=False; return action

    def reset(self):
        """Call when a STUCK episode is abandoned (e.g. a tilt/battery/sensor fault pre-empts it)
        before its result was ever polled — otherwise _busy stays True forever and every future
        request_decision() silently refuses to submit. Doesn't cancel an in-flight HTTP call (not
        cheaply cancellable via urllib), just drops its result and frees the client to accept a
        new request; harmless since the call no longer runs on any safety-relevant thread."""
        try: self._out_q.get_nowait()
        except queue.Empty: pass
        self._busy=False

    def _call(self,situation):
        if not self._key: return {'action':'stop','duration':1.0,'reason':'No API key'}
        msg=(f"State:{situation.get('state')} front:{situation.get('front_cm',999):.0f}cm "
             f"left:{situation.get('left_cm',999):.0f}cm right:{situation.get('right_cm',999):.0f}cm "
             f"tilt:{situation.get('tilt_deg',0):.1f}deg stuck:{situation.get('stuck_count',0)} "
             f"bat:{situation.get('battery_pct',0)}% last:{situation.get('last_action','none')}\nWhat should I do?")
        self._history.append({'role':'user','content':msg})
        if len(self._history)>12: self._history=self._history[-12:]
        payload=json.dumps({'model':config.CLAUDE_MODEL,'max_tokens':config.CLAUDE_MAX_TOKENS,
            'thinking':{'type':'disabled'},'system':SYSTEM,'messages':self._history}).encode()
        req=urllib.request.Request('https://api.anthropic.com/v1/messages',data=payload,
            headers={'x-api-key':self._key,'anthropic-version':'2023-06-01','content-type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=8) as r:
                txt=json.loads(r.read())['content'][0]['text'].strip()
                if txt.startswith('```'): txt=txt.split('```')[1]; txt=txt[4:] if txt.startswith('json') else txt
                action=json.loads(txt); self._history.append({'role':'assistant','content':txt}); return action
        except Exception as e:
            log.warning(f'Claude API call failed: {type(e).__name__}: {e}')
            return {'action':'stop','duration':2.0,'reason':f'API err:{type(e).__name__}'}
