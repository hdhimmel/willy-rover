import time,config,logsetup,privacy
log=logsetup.setup('vision')

# FR-1700/FR-1800 object detection. TWO BACKENDS, selected by config.ENABLE_HAILO_VISION:
# when on, picamera2 + the Hailo-10H NPU against the CSI imx708 — the actual FRONT camera
# (live-verified 2026-08-21); when off, the original CPU/ultralytics path against the Arducam
# OV9281 (USB, config.CAMERA_DEVICE), which is REAR-facing and stays disabled via
# ENABLE_OBJECT_RETRIEVAL=False. detect() branches internally — callers (retrieval_task.py,
# pursuit_task.py, mapping.py, brain.py) see one unchanged interface either way, which is what
# this module's original docstring anticipated when it called detect() "the swap point".
#
# LOCALIZATION IS A HEURISTIC, NOT A CALIBRATED MEASUREMENT. No camera calibration has been run
# on this unit (no focal-length/lens-distortion bench check,
# same category of gap as arm.py's uncalibrated joint limits — §20.6 territory). distance_cm
# below is a rough pinhole estimate from bounding-box size vs. an assumed object width; bearing
# is a rough estimate from pixel offset vs. an assumed horizontal FOV. Both are usable for
# coarse "closer/farther, left/right" approach control, not for precision placement.
#
# THERE IS A DEPTH SENSOR, AND IT IS NOT THIS MODULE. Corrected 2026-09-15 -- the line above
# used to read "there is no depth sensor", which stopped being true when the multi-zone ToF
# (DFRobot SEN0628, 8x8 zones, 20-3500mm) was specified. See tof.py and Master Hardware Design
# 6.5. Division of labour, and it matters because the two are easy to conflate:
#
#   vision.py  WHAT a thing is, and roughly where -- class, bearing, coarse range. Deliberative.
#              Feeds world_model.py for planning and classification. Per Master Hardware Design
#              12 rule 15 it does NOT gate a stop.
#   tof.py     HOW FAR the floor and obstacles actually are. Reflex layer. It is the actual drop
#              and near-obstacle detector; vision only proposes candidates for it to confirm.
#
# So do NOT reach for localize() when what you want is distance-to-floor or a cliff edge, and do
# not "improve" distance_cm by fusing ToF zones into it -- they answer different questions at
# different layers, and blending them would put a deliberative estimate inside a reflex path.
# Related trap already recorded in Master Hardware Design 5.4: localize() models no ground plane
# and no camera tilt, so it is wrong for floor geometry regardless of how accurate its ranging
# gets. ENABLE_TOF is currently False (no working sensor -- unit #1 faulty, replacement ordered
# 2026-09-15), which changes none of this.
_ASSUMED_OBJECT_WIDTH_CM=8.0   # fallback for a class not in _CLASS_WIDTH_CM
# FR-1000-006 / FR-1700-008 (2026-10-02): nominal real-world widths per COCO class, in cm. One
# 8 cm width for everything put a person (~45 cm across the shoulders) at about a sixth of their
# true range, so the 150 cm person gate let the rover close right in. Nominal sizes, not
# measured; the focal length below is still an estimate, so range stays a heuristic.
_CLASS_WIDTH_CM={'person':45.0,'cat':20.0,'dog':30.0,'chair':45.0,'couch':180.0,'bed':150.0,
                 'dining table':120.0,'tv':100.0,'laptop':33.0,'cell phone':7.5,'remote':5.0,
                 'book':15.0,'bottle':7.0,'cup':8.0,'wine glass':8.0,'bowl':15.0,'sports ball':20.0,
                 'teddy bear':25.0,'backpack':30.0,'handbag':30.0,'umbrella':10.0,'potted plant':30.0,
                 'clock':25.0,'vase':12.0,'scissors':8.0,'toothbrush':2.0,'banana':18.0,'apple':8.0,
                 'orange':8.0,'mouse':6.0,'keyboard':44.0,'shoe':10.0}
_ASSUMED_HFOV_DEG=70.0         # typical USB webcam-class FOV, not bench-measured for the OV9281
_FOCAL_PX_ESTIMATE=600.0       # rough: focal_px = (frame_w/2) / tan(HFOV/2) at 640px width
_CAMERA_ID='front'             # §12: accurate for the Hailo/CSI backend (imx708, front-facing).
                                # The CPU/Arducam fallback is REAR-facing — which is exactly why
                                # it stays disabled rather than being relabelled. Named rather
                                # than a bare magic string so a second camera later is an obvious
                                # addition here, not a silent inconsistency.

class ObjectDetector:
    def __init__(self):
        self._hailo_backend=config.ENABLE_HAILO_VISION
        self._enabled=config.ENABLE_HAILO_VISION or config.ENABLE_OBJECT_RETRIEVAL
        self._cap=None; self._model=None; self._hailo=None; self._picam2=None
        self._hailo_labels=None; self._hailo_input_hw=None
        if self._hailo_backend: self._load_hailo()
        elif self._enabled: self._load()

    def _load(self):
        import os
        model_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.YOLO_MODEL_PATH)
        if not os.path.exists(model_path):
            log.warning(f'YOLO model missing at {model_path} — object retrieval stays disabled.')
            self._enabled=False; return
        try:
            import cv2; from ultralytics import YOLO
            self._cv2=cv2
            self._model=YOLO(model_path)
            # cv2.VideoCapture's default backend fails to stream from the Arducam OV9281
            # (VIDIOC_QBUF: Bad file descriptor) even though the device opens successfully —
            # it only works with the V4L2 backend forced explicitly, plus an explicit MJPG
            # request since the camera doesn't advertise a raw BGR/YUV mode OpenCV defaults to.
            self._cap=cv2.VideoCapture(config.CAMERA_DEVICE,cv2.CAP_V4L2)
            self._cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
            if not self._cap.isOpened():
                raise RuntimeError(f'could not open {config.CAMERA_DEVICE}')
        except Exception as e:
            log.error(f'Vision backend load failed, staying disabled: {e}')
            self._enabled=False

    def _load_hailo(self):
        import os
        # Unlike the CPU path (inert regardless, since ENABLE_OBJECT_RETRIEVAL is False), this
        # backend's flag is ON — so without this guard `WILLY_SIMULATE=1` on the rover itself,
        # including main.py's I2C-offline degraded fallback, would still claim the NPU and start
        # the CSI camera. Simulate mode has to stay inert w.r.t. real hardware here like it does
        # in motors.py/sensors.py/arm.py.
        if config.SIMULATE_HARDWARE: self._enabled=False; return
        if not os.path.exists(config.HAILO_YOLO_MODEL_PATH):
            log.warning(f'Hailo model missing at {config.HAILO_YOLO_MODEL_PATH} — vision stays disabled.')
            self._enabled=False; return
        try:
            from picamera2 import Picamera2
            import hailo_server
            client=hailo_server.get_client()
            if client is not None and client.info.get('yolo'):
                # FR-1400-006: the chip lives in the Hailo server process; frames go to it.
                self._hailo=hailo_server.RemoteYolo(client)
            else:
                from picamera2.devices import Hailo
                self._hailo=Hailo(config.HAILO_YOLO_MODEL_PATH)
            model_h,model_w,_=self._hailo.get_input_shape()
            self._hailo_input_hw=(model_h,model_w)
            labels_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.HAILO_COCO_LABELS_PATH)
            with open(labels_path,encoding='utf-8') as f:
                self._hailo_labels=f.read().splitlines()
            self._picam2=Picamera2()
            main={'size':(1280,720),'format':'XRGB8888'}
            lores={'size':(model_w,model_h),'format':'RGB888'}
            picam_config=self._picam2.create_preview_configuration(main,lores=lores)
            self._picam2.configure(picam_config)
            self._picam2.start()
        except Exception as e:
            log.error(f'Hailo vision backend load failed, staying disabled: {e}')
            self._enabled=False

    @property
    def available(self): return self._enabled and privacy.camera_enabled()

    def detect(self,classes=None):
        # FR-1700-001. Returns [] if disabled, camera unavailable, or privacy-disabled — callers
        # must treat that as "nothing detected right now", never raise.
        if not self.available: return []
        return self._detect_hailo(classes) if self._hailo_backend else self._detect_cpu(classes)

    def _detect_cpu(self,classes=None):
        ok,frame=self._cap.read()
        if not ok: return []
        h,w=frame.shape[:2]
        results=self._model.predict(frame,conf=config.YOLO_CONF_THRESHOLD,verbose=False)[0]
        out=[]
        for box in results.boxes:
            cls_name=self._model.names[int(box.cls[0])]
            if classes and cls_name not in classes: continue
            x1,y1,x2,y2=box.xyxy[0].tolist()
            out.append({'class':cls_name,'conf':float(box.conf[0]),
                        'bbox':(x1,y1,x2,y2),'frame_w':w,'frame_h':h,
                        'timestamp':time.time(),'camera_id':_CAMERA_ID})  # §12
        return out

    def _detect_hailo(self,classes=None):
        # detect()'s contract above is "never raise", and this runs on brain.py's tick thread —
        # whose run() loop catches only KeyboardInterrupt, so an escaping camera/HailoRT error
        # would end the control loop and (Restart=on-failure) restart-loop the service. The CPU
        # path gets this for free: cap.read() returns False rather than raising. This one doesn't.
        try:
            w,h=1280,720  # matches _load_hailo()'s 'main' stream config
            frame=self._picam2.capture_array('lores')
            results=self._hailo.run(frame)  # postprocessed by the HEF itself -- no manual NMS/decode
            out=[]
            for class_id,dets in enumerate(results):
                cls_name=self._hailo_labels[class_id]
                if classes and cls_name not in classes: continue
                for det in dets:
                    score=det[4]
                    if score<config.YOLO_CONF_THRESHOLD: continue
                    y0,x0,y1,x1=det[:4]
                    out.append({'class':cls_name,'conf':float(score),
                                'bbox':(x0*w,y0*h,x1*w,y1*h),'frame_w':w,'frame_h':h,
                                'timestamp':time.time(),'camera_id':_CAMERA_ID})  # §12
            return out
        except Exception as e:
            log.error(f'Hailo detect failed, reporting no detections this frame: {e}')
            return []

    def localize(self,detection):
        # FR-1700-002. See module docstring — heuristic, not calibrated.
        x1,y1,x2,y2=detection['bbox']; w=detection['frame_w']
        bbox_w=max(1.0,x2-x1)
        width_cm=_CLASS_WIDTH_CM.get(detection.get('class'),_ASSUMED_OBJECT_WIDTH_CM)
        distance_cm=(width_cm*_FOCAL_PX_ESTIMATE)/bbox_w
        center_x=(x1+x2)/2.0; offset=(center_x-w/2.0)/(w/2.0)  # -1..1
        bearing_deg=offset*(_ASSUMED_HFOV_DEG/2.0)
        return distance_cm,bearing_deg

    def capture_frame(self):
        """FR-2100: one BGR frame from the already-open camera for face recognition, or None.
        Same privacy gate as capture_still (available honours privacy.camera_enabled()). The
        caller embeds it and drops it; nothing here keeps it."""
        if not self.available or getattr(self,'_picam2',None) is None: return None
        try:
            return self._picam2.capture_array('main')[:,:,:3].copy()   # XRGB8888 -> BGR
        except Exception:
            log.warning('capture_frame failed',exc_info=True); return None

    def capture_still(self):
        """JPEG bytes from the already-open camera, or None. Added 2026-08-24 for the STUCK
        help-photo feature.

        Exists because the Hailo backend holds the CSI camera for the process lifetime, so
        nothing else can open it -- a standalone capture requires stopping the service, which is
        exactly what a fault alert cannot do. This borrows a frame from the running picam2
        instead. Uses the 'main' stream (1280x720) rather than the 640x640 'lores' stream
        detect() consumes, so the photo is actually useful to look at.

        Honours privacy.camera_enabled() via `available` -- a privacy-disabled camera stays
        disabled even for a fault alert. Never raises: a failed capture returns None and the
        caller falls back to a text-only alert."""
        if not self.available or self._picam2 is None: return None
        try:
            import io
            from PIL import Image
            frame=self._picam2.capture_array('main')
            buf=io.BytesIO()
            # 'main' is XRGB8888 (see _load_hailo) -- drop the padding byte, keep RGB.
            Image.fromarray(frame[:,:,:3][:,:,::-1]).save(buf,format='JPEG',quality=80)
            return buf.getvalue()
        except Exception as e:
            log.warning(f'capture_still failed, alert will be text-only: {e}')
            return None

    def close(self):
        # brain.py::stop() runs memory.close()/world_model.close()/motors.cleanup() and every
        # sensor stop() AFTER this call, so an exception escaping here would silently skip all of
        # them — the same failure class as the 2026-08-08 memory.close() bug documented in
        # brain.py::stop(). Each release is independent so one failing backend can't block the
        # other, and none of them can block the caller.
        try:
            if self._cap is not None: self._cap.release()
        except Exception as e: log.warning(f'Arducam release failed during close(): {e}')
        try:
            if self._picam2 is not None: self._picam2.stop()
        except Exception as e: log.warning(f'Picamera2 teardown failed during close(): {e}')
        try:
            if self._hailo is not None: self._hailo.close()
        except Exception as e: log.warning(f'Hailo close failed during close(): {e}')


class RearCamera:
    """The REAR camera, Arducam OV9281 (config.CAMERA_DEVICE, by-id), 2026-10-10 (owner: "remember
    to use the rear camera"). Until now only scripts/rotate_test.py ever opened it: rotation mode
    was built to take a rear grab and brain.py never passed one.

    Opened ON DEMAND (rotation, reversing) and released after REAR_CAM_IDLE_CLOSE_S unused, so it
    costs nothing while he drives forward or sits. Honours privacy.camera_enabled() on every grab.
    Frames are used and dropped, never stored (owner rule: no camera data unless needed)."""
    def __init__(self,open_cap=None,clock=time.monotonic):
        self._open_cap=open_cap or self._default_open
        self._cap=None; self._last_use=0.0; self._clock=clock; self._labels=None; self._failed_at=None
        import threading; self._lock=threading.RLock()   # rotation (tick) and the reverse watcher share it
        self._opening=False
    @staticmethod
    def _default_open():
        import cv2
        cap=cv2.VideoCapture(config.CAMERA_DEVICE,cv2.CAP_V4L2)
        if not cap.isOpened(): cap.release(); return None
        return cap
    def grab(self):
        """One frame (BGR or grey ndarray), or None: privacy, no camera, or a failed read."""
        with self._lock: return self._grab()
    def _grab(self):
        if config.SIMULATE_HARDWARE or not privacy.camera_enabled():
            self.close(); return None
        now=self._clock(); self._last_use=now
        if self._cap is None:
            # NEVER open on the caller's thread: VideoCapture() takes ~0.9 s, and on 2026-10-10 the
            # tick waited that long on this lock while he reversed (TICK_OVERRUN 897 ms). Open in
            # the background; callers get None until it is ready.
            if self._failed_at is not None and now-self._failed_at<config.REAR_CAM_RETRY_S: return None
            if not self._opening:
                self._opening=True
                import threading; threading.Thread(target=self._open_async,daemon=True,name='rearcam-open').start()
            return None
        try:
            ok,f=self._cap.read()
            return f if ok else None
        except Exception:
            log.warning('Rear camera read failed',exc_info=True); self.close(); return None
    def _open_async(self):
        try: cap=self._open_cap()
        except Exception: cap=None
        with self._lock:
            self._opening=False
            if cap is None:
                if self._failed_at is None: log.warning(f'Rear camera would not open ({config.CAMERA_DEVICE})')
                self._failed_at=self._clock(); return
            self._cap=cap; self._failed_at=None; self._last_use=self._clock()
        log.info('Rear camera open')
    def close_if_idle(self):
        # Called from the TICK: never wait for the lock. If someone holds it, try next tick.
        if not self._lock.acquire(blocking=False): return
        try:
            if self._cap is not None and self._clock()-self._last_use>config.REAR_CAM_IDLE_CLOSE_S: self._close()
        finally: self._lock.release()
    def close(self):
        with self._lock: self._close()
    def _close(self):
        if self._cap is not None:
            try: self._cap.release()
            except Exception: pass
            self._cap=None; log.info('Rear camera released')
    def detect(self,client=None):
        """Detections behind him, through the Hailo server (no in-process fallback: the rear camera
        is an extra, and the chip lives in the server). [] when anything is unavailable."""
        if client is None:
            try:
                import hailo_server; client=hailo_server.get_client()
            except Exception: client=None
        if client is None or not client.info.get('yolo'): return []
        f=self.grab()
        if f is None: return []
        try:
            import cv2,numpy as np,os
            h,w=f.shape[:2]; mh,mw=client.info['input_shape'][:2]
            img=cv2.resize(f,(mw,mh),interpolation=cv2.INTER_AREA)
            img=cv2.cvtColor(img,cv2.COLOR_GRAY2RGB) if img.ndim==2 else cv2.cvtColor(img,cv2.COLOR_BGR2RGB)
            if self._labels is None:
                p=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.HAILO_COCO_LABELS_PATH)
                with open(p,encoding='utf-8') as fh: self._labels=fh.read().splitlines()
            out=[]
            for cid,dets in enumerate(client.detect(np.ascontiguousarray(img,dtype=np.uint8))):
                for det in dets:
                    if det[4]<config.YOLO_CONF_THRESHOLD: continue
                    y0,x0,y1,x1=det[:4]
                    out.append({'class':self._labels[cid],'conf':float(det[4]),'bbox':(x0*w,y0*h,x1*w,y1*h),
                                'frame_w':w,'frame_h':h,'timestamp':time.time(),'camera_id':'rear'})
            return out
        except Exception:
            log.warning('Rear detection failed; nothing reported',exc_info=True); return []


def rear_person_close(detections):
    """A person (or pet) close behind: their box fills REAR_CAM_NEAR_FRAC of the frame height.
    Height, not width -- a person side-on is narrow but still tall when near."""
    for d in detections:
        if d.get('class') not in config.REAR_CAM_STOP_CLASSES: continue
        x0,y0,x1,y1=d['bbox']
        if (y1-y0)>=config.REAR_CAM_NEAR_FRAC*d['frame_h']: return True
    return False
