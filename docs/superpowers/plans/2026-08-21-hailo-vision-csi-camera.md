# Hailo Vision + CSI Camera Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap `vision.py`'s object detector from CPU `ultralytics` YOLOv8 (pointed at the wrong, rear-facing Arducam) to Hailo-10H-accelerated YOLOv8 running against the correct front-facing CSI camera (imx708), using the official `picamera2.devices.Hailo` integration already installed on the rover.

**Architecture:** `ObjectDetector` gains a second backend branch selected by `config.ENABLE_HAILO_VISION`. When on, it uses `picamera2.Picamera2` (dual-stream: full-res for any future display use, low-res matching the Hailo model's input shape for inference) + `picamera2.devices.Hailo` running a pre-installed `.hef` file, whose output already includes NMS/box-decoding (confirmed from the official reference implementation — no manual postprocessing needed). When off, the existing CPU/Arducam path is unchanged. The public interface (`detect()`, `localize()`, `available`, `close()`) stays identical either way, so `retrieval_task.py`/`pursuit_task.py`/`mapping.py`/`brain.py` need zero changes — this is a backend swap, exactly as `vision.py`'s own pre-existing docstring already anticipated.

**Tech Stack:** `picamera2` (already installed, `/usr/lib/python3/dist-packages/picamera2`), `picamera2.devices.Hailo` (real class, source read directly from the installed package — see Task 2), pre-installed HEF model at `/usr/share/hailo-models/yolov8m_h10.hef` (confirmed present on this exact rover, compiled for this exact chip — `hailo_architecture()` returns `'HAILO10H'`, live-verified).

**Spec:** `docs/superpowers/specs/2026-08-21-hailo-npu-offload-design.md` — this plan implements §4 (vision half only) and §7 of that spec. The voice/STT and voice/LLM halves of the spec (§4 voice portions, §3's Whisper/Phi-2 sections) are **not** covered here — no `.hef` files or reference code exist yet for those on this rover (confirmed absent via live `find` during planning), so they need their own follow-up plan once that groundwork exists. Do not try to extend this plan to cover them.

## Global Constraints

- This is Python 3.13 on Raspberry Pi OS (the rover, `willie.local` via Cockpit) — nothing here can be tested on the Windows dev machine (no `picamera2`, no Hailo hardware, no `RPi`-family imports import there at all). Every step in this plan runs on the live rover terminal.
- `config.SIMULATE_HARDWARE`/`WILLY_SIMULATE=1` gates all real hardware access throughout this codebase — the Hailo/CSI path must respect this exactly like every other hardware branch in `vision.py`/`sensors.py`/`motors.py`/`arm.py` (`if not config.SIMULATE_HARDWARE:` guards the import and the real object construction).
- `config.ENABLE_HAILO_VISION` and `config.ENABLE_OBJECT_RETRIEVAL` both default `False`. Never flip either to `True` in committed code — that happens live, on the rover, only after each step's own live verification passes (matching how `ENABLE_WITTY_PI`/`ENABLE_AUTONOMOUS_ROAM` were enabled this session: verify live first, edit+commit+push+pull-on-rover+restart, confirm again).
- Existing camera-orientation bug stands until this plan lands: do not flip `ENABLE_OBJECT_RETRIEVAL=True` (the CPU/Arducam path) at any point — it stays disabled per the 2026-08-20 finding (Arducam is rear-facing). `ENABLE_HAILO_VISION=True` is the only path that should ever go live, once verified against the actual front camera.
- Follow this repo's existing code style exactly: no comments explaining *what* code does, only non-obvious *why*; compact style matching the rest of `vision.py`/`config.py` (see those files as the style reference — semicolon-joined single-purpose lines, no blank-line-heavy formatting).

---

### Task 1: Add COCO labels file and Hailo config flags

**Files:**
- Create: `models/coco.txt`
- Modify: `config.py` (after line 303, the existing `YOLO_CONF_THRESHOLD=0.5` line, before `RETRIEVAL_APPROACH_STOP_CM`)

**Interfaces:**
- Produces: `config.ENABLE_HAILO_VISION` (bool), `config.HAILO_YOLO_MODEL_PATH` (str, absolute path), `config.HAILO_COCO_LABELS_PATH` (str, relative to repo root, matching `YOLO_MODEL_PATH`'s existing convention).

- [ ] **Step 1: Create the standard COCO 80-class labels file**

This is the standard, unchanging 80-class COCO label list used by every YOLO/COCO-trained model — the same file referenced by the official `picamera2/examples/hailo/detect.py` reference implementation (`coco.txt`, one class name per line, in COCO's canonical class-index order).

Write `models/coco.txt`:
```
person
bicycle
car
motorcycle
airplane
bus
train
truck
boat
traffic light
fire hydrant
stop sign
parking meter
bench
bird
cat
dog
horse
sheep
cow
elephant
bear
zebra
giraffe
backpack
umbrella
handbag
tie
suitcase
frisbee
skis
snowboard
sports ball
kite
baseball bat
baseball glove
skateboard
surfboard
tennis racket
bottle
wine glass
cup
fork
knife
spoon
bowl
banana
apple
sandwich
orange
broccoli
carrot
hot dog
pizza
donut
cake
chair
couch
potted plant
bed
dining table
toilet
tv
laptop
mouse
remote
keyboard
cell phone
microwave
oven
toaster
sink
refrigerator
book
clock
vase
scissors
teddy bear
hair drier
toothbrush
```

- [ ] **Step 2: Verify it has exactly 80 lines**

Run (on the rover, via Cockpit terminal — or locally on Windows, this is a plain text file, no hardware needed):
```
wc -l models/coco.txt
```
Expected: `80 models/coco.txt` (or `79` if the file has no trailing newline — either is fine as long as reading it with Python's `.read().splitlines()` yields exactly 80 non-empty entries; verify with `python3 -c "print(len(open('models/coco.txt').read().splitlines()))"` → expect `80`).

- [ ] **Step 3: Add the two new config flags**

In `config.py`, immediately after the existing line `YOLO_CONF_THRESHOLD=0.5`, add:

```python
# --- Hailo-10H vision backend, 2026-08-21. Pre-installed HEF confirmed present on this exact
# rover (/usr/share/hailo-models/yolov8m_h10.hef, compiled for HAILO10H specifically -- verify
# with `python3 -c "from picamera2.devices import hailo_architecture; print(hailo_architecture())"`
# before trusting this path again if the OS image ever changes). Does NOT replace
# ENABLE_OBJECT_RETRIEVAL/CAMERA_DEVICE above -- those stay as the (currently-wrong-facing,
# disabled) CPU/Arducam fallback path. This is a separate backend selector: when True, detect()
# uses the CSI front camera (imx708) + Hailo NPU instead of the Arducam + CPU.
ENABLE_HAILO_VISION=False
HAILO_YOLO_MODEL_PATH='/usr/share/hailo-models/yolov8m_h10.hef'
HAILO_COCO_LABELS_PATH='models/coco.txt'
```

- [ ] **Step 4: Verify config.py still imports cleanly under simulate mode**

Run (Windows dev machine is fine for this — no hardware import happens under `WILLY_SIMULATE=1`):
```
cd C:\Users\himme\repos\willy-rover
set WILLY_SIMULATE=1
C:\Python314\python.exe -c "import config; print(config.ENABLE_HAILO_VISION, config.HAILO_YOLO_MODEL_PATH, config.HAILO_COCO_LABELS_PATH); config.validate()"
```
Expected: prints `False /usr/share/hailo-models/yolov8m_h10.hef models/coco.txt` then no error from `validate()`.

- [ ] **Step 5: Commit**

```bash
git add config.py models/coco.txt
git commit -m "Add Hailo vision config flags and COCO labels file"
```

---

### Task 2: Add the Hailo/CSI backend to ObjectDetector, gated and CPU-fallback-safe

**Files:**
- Modify: `vision.py`

**Interfaces:**
- Consumes: `config.ENABLE_HAILO_VISION`, `config.HAILO_YOLO_MODEL_PATH`, `config.HAILO_COCO_LABELS_PATH` (from Task 1).
- Produces: `ObjectDetector` keeps its exact existing public shape — `__init__(self)`, `available` (property, bool), `detect(self, classes=None) -> list[dict]` (each dict: `{'class':str,'conf':float,'bbox':(x1,y1,x2,y2),'frame_w':int,'frame_h':int,'timestamp':float,'camera_id':str}`), `localize(self, detection) -> (distance_cm, bearing_deg)`, `close(self)`. No caller outside `vision.py` needs to change.

This task is not TDD in the usual sense — there is no way to unit-test real Hailo/camera hardware access, and this repo has no test framework for hardware-dependent code (confirmed: the Windows dev machine cannot import `picamera2`, `hailo_platform`, or any Pi-specific hardware library at all). Instead, each step's "test" is a live, read-only verification command run on the actual rover via Cockpit terminal, following the exact pattern used throughout this session for Witty Pi/vision/arm work.

- [ ] **Step 1: Read the current `vision.py` in full before editing**

Confirm the exact current content and line numbers before making changes — this file may have been touched by other work since this plan was written.
```
cat -n vision.py
```

- [ ] **Step 2: Add the Hailo-branch imports, gated the same way the existing CPU imports are**

At the top of `vision.py`, the existing structure is:
```python
import time,config,logsetup,privacy
log=logsetup.setup('vision')
```
Change it to additionally prepare (but not yet import) the Hailo path — the real imports happen lazily inside `_load_hailo()` in Step 4 below, matching how `_load()`'s existing `cv2`/`ultralytics` imports are already lazy (inside the method, not at module level), so a rover without `ENABLE_HAILO_VISION` set never pays the import cost or risks an import error from a subsystem it isn't using. No top-of-file change needed for this step — skip directly to Step 3. (This step exists only to confirm you've read and understood the existing lazy-import pattern before replicating it — no code change here.)

- [ ] **Step 3: Branch `__init__` and `_load()` on the new flag**

Current `__init__`:
```python
class ObjectDetector:
    def __init__(self):
        self._enabled=config.ENABLE_OBJECT_RETRIEVAL
        self._cap=None; self._model=None
        if self._enabled: self._load()
```

Replace with:
```python
class ObjectDetector:
    def __init__(self):
        self._hailo_backend=config.ENABLE_HAILO_VISION
        self._enabled=config.ENABLE_HAILO_VISION or config.ENABLE_OBJECT_RETRIEVAL
        self._cap=None; self._model=None; self._hailo=None; self._picam2=None
        self._hailo_labels=None; self._hailo_input_hw=None
        if self._hailo_backend: self._load_hailo()
        elif self._enabled: self._load()
```

- [ ] **Step 4: Write `_load_hailo()`, following the CPU `_load()`'s exact fail-safe shape**

The existing `_load()` (for reference — do not remove it, it stays as the CPU/Arducam fallback):
```python
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
            self._cap=cv2.VideoCapture(config.CAMERA_DEVICE,cv2.CAP_V4L2)
            self._cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
            if not self._cap.isOpened():
                raise RuntimeError(f'could not open {config.CAMERA_DEVICE}')
        except Exception as e:
            log.error(f'Vision backend load failed, staying disabled: {e}')
            self._enabled=False
```

Add `_load_hailo()` immediately after it, same fail-safe shape:
```python
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
            with open(config.HAILO_COCO_LABELS_PATH,encoding='utf-8') as f:
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
```

Why `get_input_shape()` returns `(model_h, model_w, _)` and `lores`'s `size` is `(model_w, model_h)`: confirmed from the official `picamera2/examples/hailo/detect.py` reference (fetched and read directly during planning) — Picamera2's `size` tuples are `(width, height)` while the Hailo shape helper returns `(height, width, channels)`; getting this backwards would silently distort the image fed to the model.

- [ ] **Step 5: Live-verify `_load_hailo()` works, standalone, before wiring `detect()`**

On the rover, with `willy-rover.service` stopped (avoid I2C/camera contention with the live service, same precaution used throughout this session):
```
sudo systemctl stop willy-rover.service
cd ~/rover
git pull
./venv/bin/python3 -c "
import config
config.ENABLE_HAILO_VISION=True
from vision import ObjectDetector
d=ObjectDetector()
print('available:', d.available)
print('labels loaded:', len(d._hailo_labels) if d._hailo_labels else None)
print('input hw:', d._hailo_input_hw)
d.close()
"
```
Expected: `available: True`, `labels loaded: 80`, `input hw:` some `(height, width)` tuple (likely `(640, 640)` or similar for a YOLOv8 model — record whatever it actually prints, it's needed to sanity-check Step 7).

If this fails: read the actual exception message (it will be logged via `log.error` per Step 4's try/except) and fix before continuing — do not proceed to Step 6 with a backend that doesn't load.

- [ ] **Step 6: Write `_detect_hailo()`, matching the existing `detect()`'s output shape exactly**

Existing `detect()` (for reference, stays unchanged, still used for the CPU/Arducam path):
```python
    def detect(self,classes=None):
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
```

Change `detect()` to branch, and add `_detect_hailo()`:
```python
    def detect(self,classes=None):
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
```

`results` shape (`hailo.run(frame)` returns a per-class list of `[y0,x0,y1,x1,score]` detections, coordinates normalized 0-1) is confirmed from the official reference implementation's `extract_detections()` function, fetched and read directly during planning — not guessed.

- [ ] **Step 7: Update `close()` to release both backends**

Current:
```python
    def close(self):
        if self._cap is not None: self._cap.release()
```
Replace with:
```python
    def close(self):
        if self._cap is not None: self._cap.release()
        if self._picam2 is not None: self._picam2.stop()
        if self._hailo is not None: self._hailo.close()
```

- [ ] **Step 8: Live-verify a real detection round-trip**

Point the camera at something recognizable (a person, a chair, a bottle — anything in COCO's 80 classes) before running this. With the service still stopped:
```
cd ~/rover
./venv/bin/python3 -c "
import config
config.ENABLE_HAILO_VISION=True
from vision import ObjectDetector
d=ObjectDetector()
print('available:', d.available)
dets=d.detect()
print('detections:', dets)
d.close()
"
```
Expected: `available: True`, and `detections:` a non-empty list if something recognizable was actually in frame (an empty list is also a valid, non-error result if nothing recognizable was pointed at — re-run pointing at something obvious like a person if the first attempt is empty, to positively confirm the pipeline detects something rather than silently always returning nothing).

- [ ] **Step 9: Commit**

```bash
git add vision.py
git commit -m "Add Hailo/CSI backend to ObjectDetector, CPU/Arducam path unchanged as fallback"
git push origin main
```

---

### Task 3: Deploy, enable live, and verify against the running service

**Files:** none (deployment/verification only — no new code).

**Interfaces:** none new.

- [ ] **Step 1: Restart the live service and confirm it's healthy with the flag still off**

```
sudo systemctl start willy-rover.service
sleep 8
systemctl status willy-rover.service --no-pager | head -8
```
Expected: `active (running)`, no crash-loop. This confirms Task 2's changes didn't break the default (CPU-backend, `ENABLE_HAILO_VISION=False`) path — critical, since the CPU path is what everything else in the codebase currently depends on.

- [ ] **Step 2: Flip `ENABLE_HAILO_VISION=True` in config.py, deploy**

On the Windows dev machine:
```python
# config.py, Task 1's block:
ENABLE_HAILO_VISION=True  # 2026-08-21: live-verified working end-to-end (real front-camera
                           # frame, real Hailo detection round-trip) — see CLAUDE.md/plan for
                           # the verification steps run before this flip.
```
Verify syntax, commit, push:
```
cd C:\Users\himme\repos\willy-rover
C:\Python314\python.exe -c "import ast; ast.parse(open('config.py').read()); print('OK')"
git add config.py
git commit -m "Enable Hailo vision backend after live verification"
git push origin main
```

- [ ] **Step 3: Pull and restart on the rover**

```
cd ~/rover
git pull
sudo systemctl restart willy-rover.service
sleep 8
journalctl -u willy-rover.service --no-pager -S '15 sec ago' | grep -viE 'xkbcommon|GetGpuDevices|ReadFileContents'
```
Expected: clean startup, `Self-test passed`, no traceback referencing `vision.py`/`Hailo`/`Picamera2`. If the self-test or startup fails here specifically (not the already-known, separate I2C-flicker issue from earlier this session), check whether `ObjectDetector()`'s construction inside `brain.py::RoverBrain.__init__` is colliding with the CSI camera being held open by anything else — e.g. confirm nothing else on the rover has `/dev/video0` open at the same time (`sudo lsof /dev/video0` if this happens).

- [ ] **Step 4: Confirm `self.detector.available` is True on the live service**

```
journalctl -u willy-rover.service --no-pager -S '30 sec ago' | grep -iE 'vision|hailo|camera'
```
(Expect no errors — `_load_hailo()`'s only log lines are on failure, so silence here alongside a clean self-test is the positive signal, same pattern established earlier this session for `vision.py`'s CPU backend.)

- [ ] **Step 5: Update CLAUDE.md's camera-orientation note**

The existing note (added 2026-08-20) says the front camera integration is "completely untested." Update it to reflect this plan's completion — find the section (search `CLAUDE.md` for "Camera orientation — corrected 2026-08-20") and add a follow-up line noting the CSI/Hailo path is now live-verified and enabled, with the date. Commit this doc update on its own:
```bash
git add CLAUDE.md
git commit -m "docs: CSI/Hailo vision backend live-verified and enabled"
git push origin main
```

---

## Self-review notes (completed during plan writing, not a task for the executor)

- **Spec coverage**: this plan covers spec §4 (vision half), §5 (vision data flow), §7 (CSI camera) in full. Spec §4's voice half, §3's Whisper/Phi-2 research, §6's LLM-reliability risk, and §8's later voice testing steps are explicitly out of scope here — flagged for a separate follow-up plan once Whisper/Phi-2 HEF files and reference code exist (neither currently does, confirmed live on the rover during planning).
- **Type consistency**: `detect()`'s return shape (`class`/`conf`/`bbox`/`frame_w`/`frame_h`/`timestamp`/`camera_id` keys) is identical between `_detect_cpu()` and `_detect_hailo()`, matching what `retrieval_task.py`/`pursuit_task.py` already consume from the existing CPU path — verified against the actual current `vision.py` source read at plan-writing time, not assumed.
- **No placeholders**: every code block above is either copied verbatim from the actual current `vision.py`/`config.py` (read directly during planning) or grounded in the official `picamera2.devices.Hailo` source and the official `picamera2/examples/hailo/detect.py` reference implementation (both fetched and read directly during planning, not recalled from general knowledge).
