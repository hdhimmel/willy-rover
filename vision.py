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
# LOCALIZATION IS A HEURISTIC, NOT A CALIBRATED MEASUREMENT: there is no depth sensor and no
# camera calibration has been run on this unit (no focal-length/lens-distortion bench check,
# same category of gap as arm.py's uncalibrated joint limits — §20.6 territory). distance_cm
# below is a rough pinhole estimate from bounding-box size vs. an assumed object width; bearing
# is a rough estimate from pixel offset vs. an assumed horizontal FOV. Both are usable for
# coarse "closer/farther, left/right" approach control, not for precision placement.
_ASSUMED_OBJECT_WIDTH_CM=8.0   # generic small handheld object — no real per-class size table
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
        distance_cm=(_ASSUMED_OBJECT_WIDTH_CM*_FOCAL_PX_ESTIMATE)/bbox_w
        center_x=(x1+x2)/2.0; offset=(center_x-w/2.0)/(w/2.0)  # -1..1
        bearing_deg=offset*(_ASSUMED_HFOV_DEG/2.0)
        return distance_cm,bearing_deg

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
