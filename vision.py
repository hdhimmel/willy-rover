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
        self._enabled=config.ENABLE_OBJECT_RETRIEVAL
        self._cap=None; self._model=None
        if self._enabled: self._load()

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
            self._cap=cv2.VideoCapture(config.CAMERA_DEVICE)
            if not self._cap.isOpened():
                raise RuntimeError(f'could not open {config.CAMERA_DEVICE}')
        except Exception as e:
            log.error(f'Vision backend load failed, staying disabled: {e}')
            self._enabled=False

    @property
    def available(self): return self._enabled and privacy.camera_enabled()

    def detect(self,classes=None):
        # FR-1700-001. Returns [] if disabled, camera unavailable, or privacy-disabled — callers
        # must treat that as "nothing detected right now", never raise.
        if not self.available: return []
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
