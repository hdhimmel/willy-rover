import os,threading,time,queue,config,logsetup
import numpy as np
log=logsetup.setup('recognition')

# FR-2100 person recognition -- the EMBEDDING SOURCE (built 2026-10-02). identity.py is the store
# and matcher and stays camera-free; this module is the only place frames and models live
# (design §4). Faces only: the pet half waits on the design's §10 spike.
#
# Models: OpenCV's YuNet (detection) + SFace (128-d embedding), CPU, from the OpenCV model zoo,
# in models/ (gitignored). Missing models or no camera -> unavailable, and everything that uses
# this simply does nothing (FR-2100 degrades independently of the rest of the rover).
#
# Runs on its OWN thread with a single-slot result queue (design §5): a slow embedding never
# touches the tick thread, and under load he recognises less often rather than building a
# backlog. FRAMES ARE NEVER STORED (FR-2100-005, FR-1800-002): a frame lives for one embed call.
# Embeddings of people who are not enrolled are matched and discarded; only enrol() persists.

class FaceRecognizer:
    def __init__(self,frame_source):
        """frame_source() -> BGR uint8 frame or None (vision.ObjectDetector.capture_frame)."""
        self._frame_source=frame_source
        self._det=None; self._rec=None
        self._results=queue.Queue(maxsize=1)
        self._scan=threading.Event(); self._running=False; self._thread=None
        self._lock=threading.Lock()
        self.available=False
        if not config.ENABLE_FACE_RECOGNITION: return
        root=os.path.dirname(os.path.abspath(__file__))
        det=os.path.join(root,config.FACE_DET_MODEL_PATH); rec=os.path.join(root,config.FACE_REC_MODEL_PATH)
        if not (os.path.exists(det) and os.path.exists(rec)):
            log.warning(f'Face models missing ({config.FACE_DET_MODEL_PATH}, {config.FACE_REC_MODEL_PATH}) '
                        '-- recognition disabled'); return
        try:
            import cv2
            self._cv2=cv2
            self._det=cv2.FaceDetectorYN.create(det,'',(320,320),config.FACE_DET_SCORE,0.3,5000)
            self._rec=cv2.FaceRecognizerSF.create(rec,'')
            self.available=True
        except Exception:
            log.warning('Face models failed to load -- recognition disabled',exc_info=True)

    # --- pure-ish embedding step, used by the worker, enrolment and the bootstrap script ---
    def embed(self,frame):
        """[(box, unit-vector)] for every face in one BGR frame. The frame is not kept."""
        if not self.available or frame is None: return []
        with self._lock:
            h,w=frame.shape[:2]
            self._det.setInputSize((w,h))
            _,faces=self._det.detect(frame)
            out=[]
            for f in (faces if faces is not None else []):
                crop=self._rec.alignCrop(frame,f)
                v=np.asarray(self._rec.feature(crop),dtype=np.float32).ravel()
                n=float(np.linalg.norm(v))
                if n>0: out.append((tuple(int(x) for x in f[:4]),v/n))
            return out

    # --- background scanning (IDLE only; brain turns it on and off) ---
    def start(self):
        if not self.available: return
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True,name='face-scan'); self._thread.start()
    def stop(self):
        self._running=False; self._scan.set()
        if self._thread is not None: self._thread.join(timeout=2.0)
    def set_scanning(self,on):
        (self._scan.set if on else self._scan.clear)()
    def _loop(self):
        while self._running:
            if not self._scan.wait(1.0): continue
            if not self._running: break
            try:
                faces=self.embed(self._frame_source())
            except Exception:
                log.warning('Face scan failed',exc_info=True); faces=[]
            try: self._results.get_nowait()          # single slot: newest result wins
            except queue.Empty: pass
            self._results.put_nowait((time.time(),faces))
            time.sleep(config.FACE_SCAN_S)
    def latest(self):
        """(timestamp, [(box, vec)]) or None. Consumed by brain on the tick thread -- cheap."""
        try: return self._results.get_nowait()
        except queue.Empty: return None

    def capture_for_enrolment(self):
        """FR-2100-001: FACE_ENROL_FRAMES frames over ~FACE_ENROL_S, exactly one face in each.
        Returns (vectors, None) or ([], spoken reason). Runs on the caller's thread -- callers
        must not be the tick thread."""
        vecs=[]; gap=config.FACE_ENROL_S/max(1,config.FACE_ENROL_FRAMES)
        for _ in range(config.FACE_ENROL_FRAMES):
            faces=self.embed(self._frame_source())
            if len(faces)>1: return [],"I can see more than one person. Just the one being introduced, please."
            if faces: vecs.append(faces[0][1])
            time.sleep(gap)
        if len(vecs)<max(2,config.FACE_ENROL_FRAMES//2):
            return [],"I couldn't see a face clearly. Stand in front of me and try again."
        return vecs,None
