import json,os,time,urllib.request,urllib.error,config,logsetup
log=logsetup.setup('smart_home')

# FR-1300 Smart Home Integration (Google Home).
#
# DIRECTION CONFIRMED WITH OWNER 2026-08-18: Willie sends commands OUT to existing Google Home
# devices, not the reverse (Willie controlled BY Google Assistant, e.g. "Hey Google, ask Willy to
# come here") — that would be a different, unbuilt capability (an Actions-on-Google integration),
# not this class. The assumption the FRD flagged since 2026-08-01 is resolved; this is the
# correct, intended direction, not a guess anymore.
#
# BACKEND SUBSTITUTION: Google does not expose a public API for a third-party script to send
# on/off/dim/scene commands directly to another account's Google Home devices — that surface
# (Home Graph) is for building your OWN Actions-on-Google smart-home integration, not for
# controlling existing ones. The realistic, commonly-used local bridge for this is Home
# Assistant's REST API, with its own Google Home integration handling the actual device link —
# so that's what this client talks to. If a Home Assistant instance isn't what's actually
# running on the network, this needs a different backend; the discover/send_command interface
# below is written so swapping the backend doesn't change callers (brain.py, voice.py).
#
# FR-1300-005: auth is via config.GOOGLE_HOME_CREDS_PATH, a JSON file (gitignored, not this
# module's concern to create) shaped {"base_url": "http://homeassistant.local:8123",
# "token": "<long-lived access token>"} — created under Willie's own dedicated Google account
# per config.WILLIE_GOOGLE_ACCOUNT, not the owner's personal account.

class SmartHomeClient:
    def __init__(self):
        self._enabled=config.ENABLE_SMART_HOME
        self._base_url=None; self._token=None
        self._last_error=''
        if self._enabled: self._load_creds()

    def _load_creds(self):
        path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.GOOGLE_HOME_CREDS_PATH)
        try:
            with open(path) as f: creds=json.load(f)
            self._base_url=creds['base_url'].rstrip('/'); self._token=creds['token']
        except (OSError,KeyError,json.JSONDecodeError) as e:
            # FR-1300-004: missing/bad credentials must not raise into the caller — smart home
            # is Directive 6 (lowest priority), core mobility/safety must never notice this failed.
            log.warning(f'Smart home credentials unavailable ({e}) — smart home stays disabled.')
            self._enabled=False; self._last_error=str(e)

    @property
    def available(self): return self._enabled and self._base_url is not None

    def _request(self,method,path,body=None):
        if not self.available: return None,'smart home not configured/enabled'
        url=f'{self._base_url}{path}'
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(url,data=data,method=method,
            headers={'Authorization':f'Bearer {self._token}','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=config.SMART_HOME_DISCOVERY_TIMEOUT_S) as r:
                return json.loads(r.read() or b'{}'),None
        except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,ConnectionError) as e:
            # FR-1300-004: loss of network/HA access is an ordinary, expected failure mode here,
            # not an exception the rest of the system should see.
            self._last_error=str(e)
            log.info(f'Smart home request failed (expected if offline): {e}')
            return None,str(e)

    def discover_devices(self):
        # FR-1300-001. Returns [] (not an error) if unavailable — callers should treat an empty
        # list as "nothing to control right now", same as any other empty discovery result.
        states,err=self._request('GET','/api/states')
        if states is None: return []
        domains=('light','switch','scene')
        return [{'entity_id':s['entity_id'],'name':s.get('attributes',{}).get('friendly_name',s['entity_id']),
                 'state':s.get('state')} for s in states if s['entity_id'].split('.')[0] in domains]

    def send_command(self,entity_id,command,**kwargs):
        # FR-1300-002/003: command in {'on','off','dim','scene'}; returns (ok,message) — never
        # raises, always something safe to read back to the user via voice/display.
        domain=entity_id.split('.')[0]
        service={'on':'turn_on','off':'turn_off','dim':'turn_on','scene':'turn_on'}.get(command)
        if service is None: return False,f'Unknown smart home command: {command}'
        body={'entity_id':entity_id}
        if command=='dim' and 'brightness_pct' in kwargs: body['brightness_pct']=kwargs['brightness_pct']
        svc_domain='scene' if domain=='scene' else domain
        result,err=self._request('POST',f'/api/services/{svc_domain}/{service}',body)
        if err: return False,f'Could not reach {entity_id}: {err}'
        log.info(f'Smart home: {command} -> {entity_id}')
        return True,f'{entity_id} {command} sent'
