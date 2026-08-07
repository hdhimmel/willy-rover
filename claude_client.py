import json,urllib.request,urllib.error,os,config
SYSTEM="""You are the brain of WildWilly, a 6-wheel autonomous rover.
Respond ONLY with JSON: {"action":"forward"|"reverse"|"turn_left"|"turn_right"|"stop"|"wait","duration":<float>,"speed":<0.0-1.0>,"reason":"<60 chars"}
Safety: never forward if front<15cm. Stop if tilt>22deg."""
class ClaudeClient:
    def __init__(self): self._key=os.environ.get('ANTHROPIC_API_KEY',''); self._history=[]
    def decide(self,situation):
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
        except Exception as e: return {'action':'stop','duration':2.0,'reason':f'API err:{type(e).__name__}'}
