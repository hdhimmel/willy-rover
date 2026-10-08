import os,sys,secrets,subprocess,threading,time,config,logsetup
from logsetup import log_event
log=logsetup.setup('hailo_server')

# FR-1400-006, the real fix (2026-10-08). The on-board model froze the WHOLE rover process while
# it read a prompt -- 2.2 s with streaming generate(), 7.7 s before -- because HailoRT's genai
# holds Python's GIL for that step. Every sensor reader, the tick loop and the motor ramp thread
# stopped with it; brain.py braked before every call so nothing drove blind.
#
# The model has to leave the rover process. It cannot simply get a process of its own: vision
# and the model must share ONE VDevice (a second VDevice -> HAILO_OUT_OF_PHYSICAL_DEVICES), and
# the Hailo-10H runtime (h10-hailort 5.1.1) has no multi-process service (ruled out 10-08). So
# ONE child process owns the chip for both: it loads YOLO and the LLM on its VDevice and answers
# over two connections, one per job, each served by its own thread. The camera stays in the
# rover process (picamera2), which sends the 640x640 'lores' frame across (~1.2 MB, a few ms).
#
# What the freeze costs now: the prompt read still holds the GIL -- of the CHILD. Detection
# pauses up to ~2.2 s while a prompt is read. Detection is never a stop sensor (the stop is
# sonar + ToF), so that is accepted. The rover's tick, sensors and motors keep running.
#
# Failure: a request that times out or hits a dead pipe kills the child and marks the client
# down; the next call restarts it, at most every HAILO_SERVER_RESTART_S. Callers see what they
# already handle: no detections, or a failed AIResult.


# ------------------------------------------------------------------ server (child process)

def _load_backends():
    """Runs in the child. One VDevice, YOLO and the LLM on it. Either may be absent; a runtime
    that will not import leaves both absent and the child still answers (with errors)."""
    try: from picamera2.devices import Hailo
    except ImportError as e:
        log.error(f'Hailo server: runtime not importable: {e}')
        return None,None,{'yolo':False,'llm':False,'input_shape':None}
    info={'yolo':False,'llm':False,'input_shape':None}
    yolo=llm=None
    root=os.path.dirname(os.path.abspath(__file__))
    if config.ENABLE_HAILO_VISION and os.path.exists(config.HAILO_YOLO_MODEL_PATH):
        try:
            yolo=Hailo(config.HAILO_YOLO_MODEL_PATH)
            info['yolo']=True; info['input_shape']=tuple(int(v) for v in yolo.get_input_shape())
        except Exception as e:
            log.error(f'Hailo server: YOLO load failed: {e}')
    llm_path=os.path.join(root,config.HAILO_LLM_MODEL_PATH)
    if config.ENABLE_HAILO_LLM and os.path.exists(llm_path):
        try:
            from hailo_platform.genai import LLM
            if Hailo.TARGET is None:
                from hailo_platform import VDevice,HailoSchedulingAlgorithm
                p=VDevice.create_params(); p.scheduling_algorithm=HailoSchedulingAlgorithm.ROUND_ROBIN
                Hailo.TARGET=VDevice(p)
            llm=LLM(Hailo.TARGET,llm_path); info['llm']=True
        except Exception as e:
            log.error(f'Hailo server: LLM load failed: {e}')
    return yolo,llm,info


def _generate(llm,req):
    toks=[]
    try:
        with llm.generate(req['prompt'],temperature=req['temperature'],top_p=req['top_p'],
                          max_generated_tokens=req['max_tokens']) as gen:
            for tok in gen: toks.append(tok)
    finally:
        # Single-turn: the model keeps context across calls unless cleared (hailo_llm.py).
        try: llm.clear_context()
        except Exception as e: log.warning(f'Hailo server: clear_context failed: {e}')
    return ''.join(toks)


def serve(conn,handler):
    """Answer (op,payload) requests on one connection until it closes. Every reply is
    ('ok',result) or ('err',text): a failing request never ends the loop."""
    while True:
        try: op,payload=conn.recv()
        except (EOFError,OSError): return
        if op=='quit': return
        try: conn.send(('ok',handler(op,payload)))
        except (EOFError,OSError,BrokenPipeError): return
        except Exception as e:
            try: conn.send(('err',f'{type(e).__name__}: {e}'))
            except (EOFError,OSError): return


def _child_main():
    from multiprocessing.connection import Client
    import logging
    # The rover process owns the rotating log file; two processes rotating one file corrupts it.
    # The child logs to stderr, which systemd puts in the journal next to the service's lines.
    root=logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h,logging.FileHandler): root.removeHandler(h)
    address=os.environ['WILLY_HAILO_ADDR']; key=bytes.fromhex(os.environ['WILLY_HAILO_KEY'])
    yolo,llm,info=_load_backends()
    log.info(f'Hailo server up (pid {os.getpid()}): yolo={info["yolo"]} llm={info["llm"]}')
    det=Client(address,authkey=key); det.send(('detect',info))
    gen=Client(address,authkey=key); gen.send(('llm',info))
    def on_detect(op,frame):
        if op!='detect' or yolo is None: raise RuntimeError(f'unsupported: {op}')
        return yolo.run(frame)
    def on_llm(op,req):
        if op!='generate' or llm is None: raise RuntimeError(f'unsupported: {op}')
        return _generate(llm,req)
    t=threading.Thread(target=serve,args=(det,on_detect),daemon=True); t.start()
    serve(gen,on_llm)
    # The rover process went away or asked us to quit: release the chip.
    for m in (yolo,):
        try:
            if m is not None: m.close()
        except Exception: pass


# ------------------------------------------------------------------ client (rover process)

class ServerDown(Exception):
    pass


class HailoServerClient:
    """The rover side. One per process (get_client()); vision and every HailoIntentModel share it.
    Each channel has its own lock, so a 5 s generation never queues a detection behind it."""
    def __init__(self,launcher=None):
        self._launch=launcher or self._launch_child
        self._proc=None; self._det=None; self._llm=None; self.info={}
        self._det_lock=threading.Lock(); self._llm_lock=threading.Lock(); self._state_lock=threading.Lock()
        self._next_try=0.0

    # ---- lifecycle
    def _launch_child(self):
        """Start the child and wait for both connections. Returns (proc,det_conn,llm_conn,info)."""
        from multiprocessing.connection import Listener
        key=secrets.token_bytes(32)
        address=os.path.join(os.environ.get('XDG_RUNTIME_DIR') or '/tmp',f'willy-hailo-{os.getpid()}.sock')
        try: os.unlink(address)
        except OSError: pass
        lst=Listener(address,family='AF_UNIX',authkey=key)
        env=dict(os.environ,WILLY_HAILO_ADDR=address,WILLY_HAILO_KEY=key.hex())
        proc=subprocess.Popen([sys.executable,os.path.abspath(__file__)],env=env,
                              cwd=os.path.dirname(os.path.abspath(__file__)))
        conns={}; err=[]
        def accept():
            try:
                for _ in range(2):
                    c=lst.accept(); role,info=c.recv(); conns[role]=(c,info)
            except Exception as e: err.append(e)
        t=threading.Thread(target=accept,daemon=True); t.start()
        t.join(config.HAILO_SERVER_START_TIMEOUT_S)
        try: lst.close()
        except Exception: pass
        if t.is_alive() or err or set(conns)!={'detect','llm'}:
            proc.kill()
            raise ServerDown(f'Hailo server did not start ({err[0] if err else "timeout"})')
        return proc,conns['detect'][0],conns['llm'][0],conns['llm'][1]

    def start(self):
        """Start (or restart) the child. True when it is up. Rate-limited after a failure."""
        with self._state_lock:
            if self._det is not None: return True
            now=time.monotonic()
            if now<self._next_try: return False
            self._next_try=now+config.HAILO_SERVER_RESTART_S
            try:
                self._proc,self._det,self._llm,self.info=self._launch()
            except Exception as e:
                log_event(log,'HAILO_SERVER',severity='warning',subsystem='hailo',status='start_failed',reason=str(e))
                return False
            log_event(log,'HAILO_SERVER',subsystem='hailo',status='up',
                      yolo=self.info.get('yolo'),llm=self.info.get('llm'))
            return True

    def _down(self,why):
        """Kill the child and drop both channels. A reply that arrives late would answer the NEXT
        request, so after any timeout nothing on these connections can be trusted."""
        with self._state_lock:
            for c in (self._det,self._llm):
                try:
                    if c is not None: c.close()
                except Exception: pass
            if self._proc is not None:
                try: self._proc.kill()
                except Exception: pass
            self._proc=self._det=self._llm=None
        log_event(log,'HAILO_SERVER',severity='warning',subsystem='hailo',status='down',reason=why)

    def close(self):
        with self._state_lock:
            for c in (self._det,self._llm):
                try:
                    if c is not None: c.send(('quit',None)); c.close()
                except Exception: pass
            if self._proc is not None:
                try: self._proc.wait(timeout=5)
                except Exception:
                    try: self._proc.kill()
                    except Exception: pass
            self._proc=self._det=self._llm=None

    # ---- requests
    def _request(self,which,lock,op,payload,timeout):
        if not self.start(): raise ServerDown('Hailo server not running')
        with lock:
            conn=self._det if which=='detect' else self._llm
            if conn is None: raise ServerDown('Hailo server not running')
            try:
                conn.send((op,payload))
                if not conn.poll(timeout):
                    self._down(f'{op} timed out after {timeout:.0f} s'); raise ServerDown(f'{op} timed out')
                status,result=conn.recv()
            except (EOFError,OSError,BrokenPipeError) as e:
                self._down(f'{op}: {type(e).__name__}'); raise ServerDown(str(e)) from e
        if status!='ok': raise RuntimeError(result)
        return result

    def detect(self,frame):
        return self._request('detect',self._det_lock,'detect',frame,config.HAILO_SERVER_DETECT_TIMEOUT_S)

    def generate(self,prompt,temperature,top_p,max_tokens):
        req={'prompt':prompt,'temperature':temperature,'top_p':top_p,'max_tokens':max_tokens}
        return self._request('llm',self._llm_lock,'generate',req,config.HAILO_SERVER_GENERATE_TIMEOUT_S)


class RemoteYolo:
    """Stands in for picamera2's Hailo object in vision.py: run() and get_input_shape()."""
    def __init__(self,client): self._c=client
    def get_input_shape(self): return self._c.info['input_shape']
    def run(self,frame): return self._c.detect(frame)
    def close(self): pass   # the client owns the child; brain.stop() -> close_client()


_client=None; _client_failed=False; _client_lock=threading.Lock()

def get_client():
    """The shared client, or None: server off, simulated, or it failed to start this run. A
    failed FIRST start is remembered, so vision and both intent models fall back to the old
    in-process path once, rather than each waiting out HAILO_SERVER_START_TIMEOUT_S. (Restarts
    after the server was up are the client's job, see start().)"""
    global _client,_client_failed
    if not config.ENABLE_HAILO_SERVER or config.SIMULATE_HARDWARE: return None
    with _client_lock:
        if _client is None and not _client_failed:
            c=HailoServerClient()
            if c.start(): _client=c
            else:
                _client_failed=True
                log.warning('Hailo server failed to start: using the in-process Hailo path this run')
        return _client

def close_client():
    global _client
    with _client_lock:
        if _client is not None: _client.close(); _client=None


if __name__=='__main__':
    _child_main()
