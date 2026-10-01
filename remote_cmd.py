import hmac,json,os,threading,time,queue,config,logsetup
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
log=logsetup.setup('remote_cmd')

# Remote commands from Home Assistant (owner request 2026-10-01): "Hey Google, Willie status" ->
# Google Home routine -> HA script (exposed to Google as a scene) -> POST here -> Willie answers
# aloud AND returns the reply text, which HA reads back on the Nest that heard the request.
#
# This REVERSES the FR-1300 direction recorded in smart_home.py (Willie -> Google only). Owner
# decision, 2026-10-01. Google gave up free-text third-party Actions in 2023, so this is a FIXED
# list of intents, never free text.
#
# Same gating as voice, by construction: everything except stop is put on voice.pending_commands
# exactly as a spoken command would be, so brain.py's Directive 1-5 checks and the self-test
# refusal apply unchanged. stop goes to voice.stop_requested, the same immediate path a spoken
# "stop" takes -- it must never wait in a queue behind anything.
#
# Auth: a shared token in REMOTE_CMD_TOKEN_PATH, sent as "Authorization: Bearer <token>". No
# token file -> the server does not start. It is never opened unauthenticated.

INTENTS=frozenset({'status','battery','stop','come_here'})

class RemoteCommandServer:
    def __init__(self,voice):
        self.voice=voice; self._server=None; self._thread=None; self._token=None
        path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.REMOTE_CMD_TOKEN_PATH)
        if not config.ENABLE_REMOTE_CMD: return
        try:
            with open(path) as f: self._token=f.read().strip() or None
        except OSError:
            self._token=None
        if not self._token:
            log.warning(f'Remote commands disabled: no token at {config.REMOTE_CMD_TOKEN_PATH}')

    @property
    def available(self): return self._token is not None

    def handle(self,auth_header,body):
        """Returns (http_status, response_dict). Pure apart from the voice handle -- tested directly."""
        expected=f'Bearer {self._token}'
        if not self._token or not hmac.compare_digest((auth_header or '').encode(),expected.encode()):
            return 401,{'error':'unauthorized'}
        try:
            intent=json.loads(body or b'{}').get('intent')
        except (ValueError,AttributeError):
            return 400,{'error':'body must be JSON {"intent": ...}'}
        if intent not in INTENTS:
            return 400,{'error':f'unknown intent {intent!r}','intents':sorted(INTENTS)}
        log.info(f'Remote command: {intent}')
        if intent=='stop':
            self.voice.stop_requested.set()
            self.voice.speak('Stopping.')
            return 200,{'reply':'Willie is stopping.'}
        replies=queue.Queue()
        self.voice.pending_commands.put({'source':'remote','intent':intent,'args':{},'text':intent,
                                         'ts':time.time(),'on_reply':replies.put})
        try:
            return 200,{'reply':replies.get(timeout=config.REMOTE_CMD_REPLY_TIMEOUT_S)}
        except queue.Empty:
            # Queued but not answered in time: the rover is mid-task, and a task intent waits for
            # IDLE (and expires after VOICE_COMMAND_MAX_AGE_S). Say so rather than claim success.
            return 200,{'reply':"Willie got the message but is busy and didn't answer."}

    def start(self):
        if not self.available: return
        owner=self
        class _H(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path!='/command':
                    self._send(404,{'error':'not found'}); return
                n=min(int(self.headers.get('Content-Length') or 0),4096)
                status,resp=owner.handle(self.headers.get('Authorization'),self.rfile.read(n))
                self._send(status,resp)
            def _send(self,status,resp):
                data=json.dumps(resp).encode()
                self.send_response(status); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data))); self.end_headers()
                self.wfile.write(data)
            def log_message(self,fmt,*args): pass  # handle() logs what matters
        try:
            self._server=ThreadingHTTPServer(('0.0.0.0',config.REMOTE_CMD_PORT),_H)
        except OSError as e:
            log.error(f'Remote command server failed to bind port {config.REMOTE_CMD_PORT}: {e}')
            return
        self._server.daemon_threads=True
        self._thread=threading.Thread(target=self._server.serve_forever,daemon=True); self._thread.start()
        log.info(f'Remote commands listening on port {config.REMOTE_CMD_PORT}')

    def stop(self):
        if self._server is not None: self._server.shutdown(); self._server.server_close()
