import json,os,urllib.request,urllib.error,config,logsetup
log=logsetup.setup('cloud_ai')

# FR-1400 Cloud AI Assistance. FALLBACK ONLY — the onboard voice.py pipeline (Llama 3.2 3B via
# llama.cpp) is the primary path; this is called only when voice.py decides a request is below
# LOCAL_LLM_CONFIDENCE_FLOOR, and only with active connectivity.
#
# BACKEND: the FRD assumed Gemini under Willie's own Google account, but that account's Gemini
# API key hit a persistent zero free-tier quota (billing was linked and confirmed active on the
# Google side; the project still reported `limit: 0` on every retry — a Google-side provisioning
# gap, not something fixable from this codebase). Parked 2026-08-06 per owner instruction, swapped
# to Anthropic's API instead, reusing the ANTHROPIC_API_KEY already configured and working for
# claude_client.py's STUCK-state driving decisions. Same swap-the-backend-not-the-callers pattern
# smart_home.py uses for its own FRD-assumption mismatch — ask()'s signature is what voice.py
# actually depends on, not which provider answers it.
#
# FR-1400-004 (never block FR-000 Directives 1-5): ask() below is a plain blocking HTTP call
# with a short timeout by design — callers MUST invoke it off brain.py's main tick thread (e.g.
# from voice.py's own worker thread), never from RoverBrain._tick(). It does not touch motors,
# display state, or the FSM directly.

class CloudAIClient:
    def __init__(self):
        self._enabled=config.ENABLE_CLOUD_AI
        self._key=os.environ.get('ANTHROPIC_API_KEY','')
        if self._enabled and not self._key:
            log.warning('ANTHROPIC_API_KEY not set — cloud AI fallback stays disabled.')
            self._enabled=False

    @property
    def available(self): return self._enabled and bool(self._key)

    def ask(self,prompt,system=None):
        # FR-1400-002/003: only ever called with connectivity assumed present by the caller;
        # any failure here (offline, quota, timeout) degrades to (None, reason) — the caller
        # (voice.py) is responsible for FR-1400-003's onboard-only fallback-with-notice.
        if not self.available: return None,'cloud AI not configured/enabled'
        payload={'model':config.CLAUDE_MODEL,'max_tokens':config.CLAUDE_MAX_TOKENS,
                 'thinking':{'type':'disabled'},'messages':[{'role':'user','content':prompt}]}
        if system: payload['system']=system
        req=urllib.request.Request('https://api.anthropic.com/v1/messages',data=json.dumps(payload).encode(),
            headers={'x-api-key':self._key,'anthropic-version':'2023-06-01','content-type':'application/json'},
            method='POST')
        try:
            with urllib.request.urlopen(req,timeout=config.CLOUD_AI_TIMEOUT_S) as r:
                resp=json.loads(r.read())
                text=resp['content'][0]['text'].strip()
                return text,None
        except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,KeyError,IndexError) as e:
            log.info(f'Cloud AI fallback failed (expected if offline/quota): {e}')
            return None,str(e)
