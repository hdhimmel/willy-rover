import time,config,logsetup,privacy
log=logsetup.setup('vision')

# FR-1700/FR-1800 object detection. BACKEND NOTE: the FRD assumes Hailo-accelerated YOLOv8;
# this unit has no Hailo NPU installed (checked 2026-08-06: no /dev/hailo*, no hailortcli), so
# this runs YOLOv8 on CPU via ultralytics against the Arducam OV9281 (USB, /dev/video0,
# confirmed present). detect() is the swap point — replace _load()/detect()'s internals with a
# Hailo runtime call later without touching callers (retrieval_task.py, brain.py).
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
_CAMERA_ID='front'             # §12: this unit has one camera (config.CAMERA_DEVICE) — named
                                # rather than a bare magic string so a second camera later is an
                                # obvious addition here, not a silent inconsistency.

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
                            'timestamp':time.time(),'camera_id':_CAMERA_ID})
        return out

    def localize(self,detection):
        # FR-1700-002. See module docstring — heuristic, not calibrated.
        x1,y1,x2,y2=detection['bbox']; w=detection['frame_w']
        bbox_w=max(1.0,x2-x1)
        distance_cm=(_ASSUMED_OBJECT_WIDTH_CM*_FOCAL_PX_ESTIMATE)/bbox_w
        center_x=(x1+x2)/2.0; offset=(center_x-w/2.0)/(w/2.0)  # -1..1
        bearing_deg=offset*(_ASSUMED_HFOV_DEG/2.0)
        return distance_cm,bearing_deg

    def close(self):
        if self._cap is not None: self._cap.release()
        if self._picam2 is not None: self._picam2.stop()
        if self._hailo is not None: self._hailo.close()
