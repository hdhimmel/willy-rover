# Face Recognition (People) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Willy recognises Howard and Carolyn by face and greets them by name, and records who was last seen and when.

**Architecture:** Person detection stays on the existing Hailo YOLO pipeline. When a `person` box appears, a dedicated worker thread (never the tick thread) runs YuNet face detection on that box, aligns the face with `cv2.FaceRecognizerSF.alignCrop()`, embeds it with SFace, and matches it by nearest-neighbour against enrolled vectors in a standalone `identities.db`. `identity.py` holds vectors and names and knows nothing about cameras; `recognition.py` holds models and knows nothing about names.

**Tech Stack:** Python 3.13, `cv2` 5.0.0 (`FaceDetectorYN` + `FaceRecognizerSF`, both confirmed present on the rover 2026-08-25), SQLite (stdlib `sqlite3`), pytest 9.1.1. All already installed — the face path needs **no new Python dependency**, only two model files.

**Why YuNet + SFace rather than ArcFace:** alignment matters more than backbone size for this task. YuNet gives a real face box with landmarks and `alignCrop()` warps to a canonical pose, which removes the need for a crop heuristic entirely. ArcFace `w600k_r50` wins on benchmarks separating millions of identities; this rover needs to separate three, while sharing 4 cores with Whisper. If SFace proves too weak, swapping the embedder is a `recognition.py`-local change — `identity.py` never learns of it.

**Spec:** `docs/superpowers/specs/2026-08-25-person-pet-recognition-design.md`

## Global Constraints

- **This plan covers the human half only.** The pet half is gated on spec §10's spike and is not in scope here. Per-person memory (the `memory.db` migration) is not in scope here.
- **Tests run on the rover, not the laptop.** The owner's Windows laptop has neither `numpy` nor `pytest`; `voice.py` cannot even be imported there. Run `venv/bin/python3 -m pytest` on the rover via SSH.
- **`identity.py` must not import `numpy`.** Cosine distance over a few hundred floats against a handful of identities is trivial in stdlib arithmetic, and keeping it numpy-free keeps the module portable and independently testable. This is a design constraint, not a preference.
- **Never block the tick thread.** `retrieval_task.py::_grasp()` and `brain.py::_wave()` were both rewritten as step machines for exactly this reason. Recognition runs on its own worker.
- **Fail closed.** Missing models or absent hardware mean log-and-disable, never an exception escaping into a caller. Mirror `vision.py::_detect_hailo()`.
- **Default off:** `ENABLE_FACE_RECOGNITION=False`, matching `ENABLE_HAILO_LLM` and `ENABLE_OBJECT_RETRIEVAL`.
- **Embeddings only.** Enrolment images are embedded and deleted immediately. Never persist a face image.
- **Bias to unknown.** An uncertain match returns `None` and Willy says nothing. Greeting the wrong person by name is the failure that matters.
- **Do not run the full test suite against a live service.** On 2026-08-25 a 110-second suite run starved the CPU and made the wake word unresponsive. Stop `willy-rover` first, or run only the specific test file.
- **The rover pushes to `origin/main` on cron** (`scripts/auto_backup.sh` runs `git add -A`). Never leave uncommitted work in `/home/hhimmel/rover`; stage scratch files in `/tmp`.

---

### Task 1: Establish the face model on the rover (gating spike)

Spec §9 leaves the face model unresolved. Nothing downstream can be written honestly until it is. This task's deliverable is an answer plus a committed model path — no application code.

**Files:**
- Create: `scripts/face_model_check.py` (committed; it is a repeatable bench measurement, following `scripts/wheel_current_test.py`'s precedent)

**Interfaces:**
- Consumes: nothing
- Produces: a verified value for `config.FACE_EMBED_MODEL_PATH` (str), the embedding dimension (int), and a measured per-embedding latency in ms. Task 4 hard-codes the path; Task 2's tests use the dimension.

- [ ] **Step 1: Confirm the rover can reach the model source**

Run on the rover:

```bash
ssh hhimmel@<ip> 'curl -sI https://huggingface.co | head -1'
```

Expected: an HTTP status line. If this fails, the rover has no route to fetch models and the whole plan stalls here — report and stop.

- [ ] **Step 2: Fetch the YuNet and SFace models into `models/`**

`models/` is gitignored, so both are provisioned, not committed.

```bash
ssh hhimmel@<ip> 'mkdir -p ~/rover/models && cd ~/rover/models && \
  curl -L -o face_detection_yunet.onnx \
    https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx && \
  curl -L -o face_recognition_sface.onnx \
    https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx && \
  ls -la face_detection_yunet.onnx face_recognition_sface.onnx'
```

Expected: roughly 230KB and 37MB respectively. If either is a few hundred bytes, `curl` fetched an LFS pointer rather than the file — add `?raw=true` or fetch from the release assets instead.

- [ ] **Step 3: Write the bench script**

```python
#!/usr/bin/env python3
"""Confirms YuNet and SFace load, and measures what a recognition costs.

WHY THIS EXISTS: the face recognition config cannot specify a threshold, a latency budget or
an embedding dimension without these numbers, and guessing them would put invented values
into config.py. Run this before building anything that depends on the models.

Both run through cv2 rather than onnxruntime: OpenCV 5.0.0 on this rover exposes
FaceDetectorYN and FaceRecognizerSF directly, so the face path needs no new dependency.
"""
import os,sys,time
import numpy as np, cv2

DET=os.environ.get('YUNET','models/face_detection_yunet.onnx')
REC=os.environ.get('SFACE','models/face_recognition_sface.onnx')

def main():
    for p in (DET,REC):
        if not os.path.exists(p):
            print(f'missing: {p}',file=sys.stderr); return 1
    det=cv2.FaceDetectorYN.create(DET,'',(320,320))
    rec=cv2.FaceRecognizerSF.create(REC,'')
    print('both models loaded')

    # A synthetic frame only measures cost, not accuracy -- it usually contains no face, which
    # is why detection count is reported rather than asserted.
    img=(np.random.rand(480,640,3)*255).astype(np.uint8)
    det.setInputSize((img.shape[1],img.shape[0]))
    t=time.perf_counter()
    for _ in range(10): _n,faces=det.detect(img)
    det_ms=(time.perf_counter()-t)*100.0
    print(f'detection: {det_ms:.1f} ms per frame (mean of 10)')
    print(f'faces found in synthetic frame: {0 if faces is None else len(faces)}')

    # Embedding cost is independent of whether the crop is a real face.
    crop=(np.random.rand(112,112,3)*255).astype(np.uint8)
    rec.feature(crop)                                   # warm up
    t=time.perf_counter()
    for _ in range(10): v=rec.feature(crop)
    rec_ms=(time.perf_counter()-t)*100.0
    print(f'embedding dim: {v.shape[-1]}')
    print(f'embedding: {rec_ms:.1f} ms (mean of 10)')
    total=det_ms+rec_ms
    print(f'TOTAL per recognition: {total:.1f} ms')
    print(f'VERDICT: {"OK" if total<300 else "TOO SLOW -- reconsider the CPU path"}')
    return 0

if __name__=='__main__':
    sys.exit(main() or 0)
```

- [ ] **Step 4: Run it and record the numbers**

```bash
scp scripts/face_model_check.py hhimmel@<ip>:/tmp/
ssh hhimmel@<ip> 'cd ~/rover && venv/bin/python3 /tmp/face_model_check.py'
```

Expected: an embedding dim (512 for `w600k_r50`) and a latency figure. **Record both — later tasks reference them.** If latency exceeds ~300ms, stop and report: the CPU path in spec §3 may not hold and the design needs revisiting before more code is written.

- [ ] **Step 5: Commit the bench script**

```bash
git add scripts/face_model_check.py
git commit -m "Add a face embedding model bench check

Records the embedding dimension and per-embedding CPU latency that the
face recognition config and threshold both depend on, so those numbers
come from measurement rather than assumption."
```

---

### Task 2: `identity.py` — enrolment and matching

Pure logic. No camera, no models, no numpy. This is the only unit in the feature that is fully unit-testable.

**Files:**
- Create: `identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Consumes: the embedding dimension from Task 1 (tests use short synthetic vectors; the code is dimension-agnostic).
- Produces:
  - `IdentityStore(db_path=None)` — constructor; `None` means `config.WILLY_MEMORY_ROOT/identities.db`
  - `enrol(name: str, kind: str, vectors: list[list[float]]) -> int` — returns count stored
  - `match(vector: list[float], kind: str) -> tuple[str,float] | None` — `(name, distance)` or `None` below threshold
  - `names(kind: str|None=None) -> list[str]`
  - `forget_all() -> None`
  - `cosine_distance(a,b) -> float` — module-level, `0.0` identical, `2.0` opposite

- [ ] **Step 1: Write the failing tests**

```python
import os,sys,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import identity

# identity.py is deliberately numpy-free and hardware-free: vectors in, names out. That is what
# makes it the one part of face recognition that can be tested without a rover, a camera or a
# model, and it is why the boundary was drawn here (spec section 4).

@pytest.fixture
def store(tmp_path):
    return identity.IdentityStore(db_path=str(tmp_path/'identities.db'))

def test_cosine_distance_is_zero_for_identical_vectors():
    assert identity.cosine_distance([1.0,0.0,0.0],[1.0,0.0,0.0]) == pytest.approx(0.0,abs=1e-9)

def test_cosine_distance_is_one_for_orthogonal_vectors():
    assert identity.cosine_distance([1.0,0.0],[0.0,1.0]) == pytest.approx(1.0,abs=1e-9)

def test_cosine_distance_ignores_magnitude():
    # Embeddings arrive un-normalised; only direction carries identity.
    assert identity.cosine_distance([1.0,0.0],[7.0,0.0]) == pytest.approx(0.0,abs=1e-9)

def test_enrol_then_match_returns_the_enrolled_name(store):
    store.enrol('Carolyn','face',[[1.0,0.0,0.0]])
    assert store.match([1.0,0.0,0.0],'face')[0] == 'Carolyn'

def test_match_returns_none_when_nothing_is_enrolled(store):
    assert store.match([1.0,0.0,0.0],'face') is None

def test_unfamiliar_vector_returns_none_rather_than_the_nearest_name(store):
    # The failure that actually stings is greeting the wrong person by name, so an uncertain
    # match must resolve to unknown -- see spec section 7.
    store.enrol('Howard','face',[[1.0,0.0,0.0]])
    assert store.match([0.0,1.0,0.0],'face') is None

def test_multiple_vectors_per_identity_all_match(store):
    # Enrolment captures several poses; any of them should identify the person.
    store.enrol('Howard','face',[[1.0,0.0,0.0],[0.0,1.0,0.0]])
    assert store.match([0.0,1.0,0.0],'face')[0] == 'Howard'

def test_closest_identity_wins_when_several_are_enrolled(store):
    store.enrol('Howard','face',[[1.0,0.0,0.0]])
    store.enrol('Carolyn','face',[[0.0,1.0,0.0]])
    assert store.match([0.05,1.0,0.0],'face')[0] == 'Carolyn'

def test_kinds_do_not_match_across_each_other(store):
    # A dog embedding must never resolve to a person's name.
    store.enrol('Storm','pet',[[1.0,0.0,0.0]])
    assert store.match([1.0,0.0,0.0],'face') is None

def test_enrolment_persists_across_store_instances(tmp_path):
    p=str(tmp_path/'identities.db')
    identity.IdentityStore(db_path=p).enrol('Howard','face',[[1.0,0.0,0.0]])
    assert identity.IdentityStore(db_path=p).match([1.0,0.0,0.0],'face')[0] == 'Howard'

def test_forget_all_removes_every_identity(store):
    store.enrol('Howard','face',[[1.0,0.0,0.0]])
    store.forget_all()
    assert store.match([1.0,0.0,0.0],'face') is None
    assert store.names() == []

def test_re_enrolling_a_name_replaces_rather_than_duplicates(store):
    store.enrol('Howard','face',[[1.0,0.0,0.0]])
    store.enrol('Howard','face',[[0.0,1.0,0.0]])
    assert store.names('face') == ['Howard']
    assert store.match([1.0,0.0,0.0],'face') is None
    assert store.match([0.0,1.0,0.0],'face')[0] == 'Howard'
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
scp tests/test_identity.py hhimmel@<ip>:/tmp/
ssh hhimmel@<ip> 'cd ~/rover && PYTHONPATH=/home/hhimmel/rover venv/bin/python3 -m pytest /tmp/test_identity.py -q'
```

Expected: FAIL, `ModuleNotFoundError: No module named 'identity'`. That is the correct first failure.

- [ ] **Step 3: Write `identity.py`**

```python
import os,math,sqlite3,threading,time,json
import config,logsetup
log=logsetup.setup('identity')

# Vectors in, names out. This module deliberately holds no camera access, no models and no
# numpy: recognition.py owns all of that. The split means the matching logic is testable
# without hardware, and either side can be replaced without touching the other -- a voice
# embedding source later, or a different face model, both plug in here unchanged.
#
# Storage is its own SQLite file rather than a table in memory.db so that forgetting every
# enrolled identity is a single file delete, and so biometric data sits on a visibly separate
# boundary from ordinary learned facts (spec section 7).

_SCHEMA='''
CREATE TABLE IF NOT EXISTS identities(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    vector TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_identities_kind ON identities(kind);
'''

def cosine_distance(a,b):
    """0.0 identical direction, 1.0 orthogonal, 2.0 opposite. Magnitude is ignored --
    embeddings arrive un-normalised and only direction carries identity."""
    dot=sum(x*y for x,y in zip(a,b))
    na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(y*y for y in b))
    if na==0.0 or nb==0.0: return 1.0
    return 1.0-(dot/(na*nb))

class IdentityStore:
    def __init__(self,db_path=None):
        if db_path is None:
            db_path=os.path.join(config.WILLY_MEMORY_ROOT,'identities.db')
        self._path=db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)),exist_ok=True)
        self._lock=threading.Lock()
        self._conn=sqlite3.connect(db_path,check_same_thread=False)
        self._conn.executescript(_SCHEMA); self._conn.commit()

    def enrol(self,name,kind,vectors):
        """Replaces any existing enrolment for this name+kind rather than adding to it, so a
        re-enrolment after recognition drifts actually supersedes the old vectors."""
        with self._lock:
            self._conn.execute('DELETE FROM identities WHERE name=? AND kind=?',(name,kind))
            now=time.time()
            self._conn.executemany(
                'INSERT INTO identities(name,kind,vector,created_at) VALUES(?,?,?,?)',
                [(name,kind,json.dumps(list(map(float,v))),now) for v in vectors])
            self._conn.commit()
        log.info(f'Enrolled {name} ({kind}) with {len(vectors)} vector(s)')
        return len(vectors)

    def match(self,vector,kind):
        """Nearest enrolled vector of this kind, or None if nothing is close enough.

        Returning None on an uncertain match is the point: greeting the wrong person by name
        is the failure that stings, so the threshold errs toward silence (spec section 7)."""
        rows=self._conn.execute(
            'SELECT name,vector FROM identities WHERE kind=?',(kind,)).fetchall()
        best=None
        for name,blob in rows:
            d=cosine_distance(vector,json.loads(blob))
            if best is None or d<best[1]: best=(name,d)
        if best is None or best[1]>config.FACE_MATCH_MAX_DISTANCE: return None
        return best

    def names(self,kind=None):
        q='SELECT DISTINCT name FROM identities'; args=()
        if kind is not None: q+=' WHERE kind=?'; args=(kind,)
        return sorted(r[0] for r in self._conn.execute(q,args))

    def forget_all(self):
        with self._lock:
            self._conn.execute('DELETE FROM identities'); self._conn.commit()
        log.warning('All enrolled identities deleted.')
```

- [ ] **Step 4: Add the config constant the store depends on**

Add to `config.py` near the other vision flags:

```python
FACE_MATCH_MAX_DISTANCE=0.55  # cosine distance above which a match resolves to unknown.
                              # Provisional -- Task 6 measures the real value against live
                              # enrolments. Errs toward silence: a wrong name is the failure
                              # that stings, a missed greeting is not.
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
ssh hhimmel@<ip> 'cd ~/rover && PYTHONPATH=/home/hhimmel/rover venv/bin/python3 -m pytest /tmp/test_identity.py -q'
```

Expected: PASS, 12 tests. Output pristine.

- [ ] **Step 6: Commit**

```bash
git add identity.py tests/test_identity.py config.py
git commit -m "Add identity store: enrolment and nearest-neighbour matching

Vectors in, names out -- no camera, no models, no numpy, so the matching
logic is testable without hardware and either side can be replaced
independently.

Its own SQLite file rather than a table in memory.db, so forgetting every
enrolled identity is a single file delete and biometric data sits on a
separate boundary from ordinary learned facts."
```

---

### Task 3: `identity.py` — last-seen presence and greeting debounce

**Files:**
- Modify: `identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Consumes: `IdentityStore` from Task 2
- Produces:
  - `note_seen(name: str, room: str|None=None, now: float|None=None) -> None`
  - `last_seen(name: str) -> dict | None` — `{'name','room','at'}`
  - `everyone_seen() -> list[dict]` — most recent first
  - `should_greet(name: str, now: float|None=None) -> bool` — True at most once per session

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_identity.py`:

```python
def test_last_seen_is_none_before_anyone_is_seen(store):
    assert store.last_seen('Howard') is None

def test_note_seen_records_name_room_and_time(store):
    store.note_seen('Howard',room='kitchen',now=1000.0)
    rec=store.last_seen('Howard')
    assert rec['name']=='Howard' and rec['room']=='kitchen' and rec['at']==1000.0

def test_note_seen_overwrites_the_previous_sighting(store):
    store.note_seen('Howard',room='kitchen',now=1000.0)
    store.note_seen('Howard',room='hall',now=2000.0)
    assert store.last_seen('Howard')['room']=='hall'

def test_everyone_seen_lists_most_recent_first(store):
    store.note_seen('Howard',now=1000.0)
    store.note_seen('Carolyn',now=2000.0)
    assert [r['name'] for r in store.everyone_seen()]==['Carolyn','Howard']

def test_first_sighting_of_a_person_greets(store):
    assert store.should_greet('Howard',now=1000.0) is True

def test_second_sighting_soon_after_does_not_greet_again(store):
    # Without this he greets on every frame in which he sees a face.
    store.should_greet('Howard',now=1000.0)
    store.note_seen('Howard',now=1000.0)
    assert store.should_greet('Howard',now=1005.0) is False

def test_sighting_after_the_session_gap_greets_again(store):
    store.should_greet('Howard',now=1000.0)
    store.note_seen('Howard',now=1000.0)
    later=1000.0+config.GREET_SESSION_GAP_S+1.0
    assert store.should_greet('Howard',later) is True

def test_greeting_one_person_does_not_suppress_another(store):
    store.should_greet('Howard',now=1000.0); store.note_seen('Howard',now=1000.0)
    assert store.should_greet('Carolyn',now=1001.0) is True
```

Add `import config` to the test file's imports.

- [ ] **Step 2: Run to verify failure**

```bash
scp tests/test_identity.py hhimmel@<ip>:/tmp/
ssh hhimmel@<ip> 'cd ~/rover && PYTHONPATH=/home/hhimmel/rover venv/bin/python3 -m pytest /tmp/test_identity.py -q'
```

Expected: the 8 new tests FAIL with `AttributeError: 'IdentityStore' object has no attribute 'note_seen'`. The 12 from Task 2 still pass.

- [ ] **Step 3: Implement**

Add to `IdentityStore`. Presence is deliberately in memory, not SQLite: it is a decaying
observation, not a durable record, and it should not survive a restart claiming someone is
present when Willy has not actually seen them since booting.

```python
    # --- presence: "last seen", not tracking (spec section 5) ---
    # In-memory on purpose. A restart should forget who was around rather than assert a
    # stale sighting as current.
    def note_seen(self,name,room=None,now=None):
        with self._lock:
            self._seen[name]={'name':name,'room':room,'at':now if now is not None else time.time()}

    def last_seen(self,name):
        return self._seen.get(name)

    def everyone_seen(self):
        return sorted(self._seen.values(),key=lambda r:r['at'],reverse=True)

    def should_greet(self,name,now=None):
        """True at most once per session, where a session ends after GREET_SESSION_GAP_S of
        not seeing someone."""
        now=now if now is not None else time.time()
        last=self._greeted.get(name)
        if last is not None and (now-last)<config.GREET_SESSION_GAP_S: return False
        with self._lock: self._greeted[name]=now
        return True
```

And in `__init__`, before the sqlite connect:

```python
        self._seen={}; self._greeted={}
```

- [ ] **Step 4: Add the config constant**

```python
GREET_SESSION_GAP_S=600.0  # 10 min. How long someone must be unseen before Willy greets them
                           # again. Without a gap he greets on every frame he sees a face.
```

- [ ] **Step 5: Run to verify pass**

```bash
ssh hhimmel@<ip> 'cd ~/rover && PYTHONPATH=/home/hhimmel/rover venv/bin/python3 -m pytest /tmp/test_identity.py -q'
```

Expected: PASS, 20 tests.

- [ ] **Step 6: Commit**

```bash
git add identity.py tests/test_identity.py config.py
git commit -m "Add last-seen presence and greeting debounce to the identity store

Presence is in-memory on purpose: a sighting is a decaying observation, and
a restart should forget who was around rather than assert a stale sighting
as current.

should_greet() fires at most once per session so Willy does not greet on
every frame in which he sees a face."
```

---

### Task 4: `recognition.py` — face crop and embedding

**Files:**
- Create: `recognition.py`
- Create: `scripts/face_recognition_bench.py`

**Interfaces:**
- Consumes: `config.FACE_EMBED_MODEL_PATH` (Task 1), `cosine_distance` (Task 2)
- Produces:
  - `FaceEmbedder()` — constructor; `.available` (bool)
  - `embed(frame, box) -> list[float] | None` — `frame` is a BGR numpy array from the camera, `box` is `(x1,y1,x2,y2)` in pixels of a person detection

- [ ] **Step 1: Write `recognition.py`**

There is no unit test for this task — it needs a camera and a model. Its correctness is
established by the bench script in Step 2, following `scripts/wheel_current_test.py`'s
precedent of a committed, repeatable measurement rather than a hand-typed one.

```python
import os
import config,logsetup
log=logsetup.setup('recognition')

# Models and pixels live here; names and vectors live in identity.py. Neither imports the
# other's concerns. This module is the only hardware-dependent half of face recognition, and
# it fails closed the way vision.py::_detect_hailo() does -- a missing model or an absent
# device disables the subsystem, it never raises into the caller's thread.

_PAD=0.15   # fraction of the person box added around it before face detection, so a head at
            # the very top edge is not clipped by a tight YOLO box

class FaceEmbedder:
    def __init__(self):
        self.available=False; self._det=None; self._rec=None
        if not config.ENABLE_FACE_RECOGNITION:
            log.info('Face recognition disabled by config.'); return
        here=os.path.dirname(os.path.abspath(__file__))
        det_p=os.path.join(here,config.FACE_DETECT_MODEL_PATH)
        rec_p=os.path.join(here,config.FACE_EMBED_MODEL_PATH)
        missing=[p for p in (det_p,rec_p) if not os.path.exists(p)]
        if missing:
            log.warning(f'Face model(s) missing, staying disabled: {missing}'); return
        try:
            import cv2
            self._det=cv2.FaceDetectorYN.create(det_p,'',(320,320),
                                                config.FACE_DETECT_MIN_CONF)
            self._rec=cv2.FaceRecognizerSF.create(rec_p,'')
            self.available=True
            log.info('Face embedder ready (YuNet + SFace).')
        except Exception as e:
            log.warning(f'Face embedder failed to load, staying disabled: {e}')

    def embed(self,frame,box):
        """A vector for the face inside this person box, or None if there isn't one.

        YuNet locates the face and returns landmarks; alignCrop() then warps it to a canonical
        pose before embedding. The alignment is the point -- it is worth more to recognition
        accuracy than a larger backbone would be, and it removes any need to guess where in a
        person box the head sits."""
        if not self.available: return None
        try:
            import cv2
            x1,y1,x2,y2=[int(v) for v in box]
            H,W=frame.shape[:2]
            ph=int((y2-y1)*_PAD); pw=int((x2-x1)*_PAD)
            x1=max(0,x1-pw); y1=max(0,y1-ph); x2=min(W,x2+pw); y2=min(H,y2+ph)
            if x2<=x1 or y2<=y1: return None
            roi=frame[y1:y2, x1:x2]
            if roi.size==0: return None
            self._det.setInputSize((roi.shape[1],roi.shape[0]))
            _n,faces=self._det.detect(roi)
            if faces is None or len(faces)==0: return None
            # Largest face in the box -- the person the box is about, not someone behind them.
            face=max(faces,key=lambda f:f[2]*f[3])
            aligned=self._rec.alignCrop(roi,face)
            vec=self._rec.feature(aligned)
            return [float(v) for v in vec.flatten()]
        except Exception as e:
            log.warning(f'Face embedding failed: {e}')
            return None
```

- [ ] **Step 2: Write the bench script**

```python
#!/usr/bin/env python3
"""Measures whether face embeddings actually separate the enrolled people.

WHY THIS EXISTS: config.FACE_MATCH_MAX_DISTANCE was set provisionally. The real value has to
come from measured distances between and within people, not from a guess -- too tight and
Willy never greets anyone, too loose and he greets the wrong person, which is the failure
that matters (spec section 7).

Run with the rover seeing one person at a time:
    sudo systemctl stop willy-rover
    venv/bin/python3 scripts/face_recognition_bench.py Howard
"""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config,identity,recognition,vision

def main():
    if len(sys.argv)<2:
        print('usage: face_recognition_bench.py <name-to-sample>',file=sys.stderr); return 1
    name=sys.argv[1]
    emb=recognition.FaceEmbedder()
    if not emb.available:
        print('face embedder unavailable -- check ENABLE_FACE_RECOGNITION and the model path',
              file=sys.stderr); return 1
    det=vision.ObjectDetector()
    store=identity.IdentityStore()
    vecs=[]
    print(f'sampling {name} -- stand in view, 10 frames')
    for i in range(10):
        frame=det.last_frame()
        dets=det.detect(classes=['person'])
        if not dets or frame is None:
            print(f'  {i}: no person detected'); time.sleep(0.5); continue
        v=emb.embed(frame,dets[0]['bbox'])
        if v is None: print(f'  {i}: no embedding'); time.sleep(0.5); continue
        vecs.append(v)
        m=store.match(v,'face')
        print(f'  {i}: embedded; current store says {m}')
        time.sleep(0.5)
    if len(vecs)<2:
        print('not enough samples',file=sys.stderr); return 1
    ds=[identity.cosine_distance(vecs[i],vecs[j])
        for i in range(len(vecs)) for j in range(i+1,len(vecs))]
    print(f'\nwithin-{name} distance: min={min(ds):.3f} mean={sum(ds)/len(ds):.3f} max={max(ds):.3f}')
    print(f'config.FACE_MATCH_MAX_DISTANCE is {config.FACE_MATCH_MAX_DISTANCE}')
    print('Set the threshold ABOVE this max and BELOW the between-people distance.')
    print('Re-run for each person, then compare.')
    return 0

if __name__=='__main__':
    sys.exit(main() or 0)
```

- [ ] **Step 3: Add the config constants**

```python
ENABLE_FACE_RECOGNITION=False  # default off, same convention as ENABLE_HAILO_LLM. Turning it
                               # on makes Willy greet enrolled people by name.
# Both provisioned by Task 1, not tracked in git (models/ is gitignored). Run through cv2's
# built-in FaceDetectorYN/FaceRecognizerSF -- no onnxruntime session handling needed.
FACE_DETECT_MODEL_PATH='models/face_detection_yunet.onnx'
FACE_EMBED_MODEL_PATH='models/face_recognition_sface.onnx'
FACE_DETECT_MIN_CONF=0.7   # YuNet score below which a candidate is not treated as a face
```

- [ ] **Step 4: Verify it loads on the rover**

```bash
scp recognition.py hhimmel@<ip>:/home/hhimmel/rover/
ssh hhimmel@<ip> 'cd ~/rover && venv/bin/python3 -c "
import config; config.ENABLE_FACE_RECOGNITION=True
import recognition; e=recognition.FaceEmbedder(); print(\"available:\",e.available)"'
```

Expected: `available: True`. If False, read the logged warning — the model path is the usual cause.

- [ ] **Step 5: Commit**

```bash
git add recognition.py scripts/face_recognition_bench.py config.py
git commit -m "Add the face embedder and a bench script for the match threshold

Models and pixels live in recognition.py, names and vectors in identity.py;
neither imports the other's concerns.

Crops the upper portion of the person box rather than running a separate
face detector -- no second model, at the cost of a looser crop. If accuracy
disappoints, a real face detector is the first thing to try.

The bench script exists because FACE_MATCH_MAX_DISTANCE is provisional: the
real value must come from measured within- and between-person distances,
not a guess."
```

---

### Task 5: Voice enrolment and forget commands

**Files:**
- Modify: `voice.py` (pattern block near `_TIME_PATTERN`, and `_fast_path`)
- Test: `tests/test_voice_fast_path.py`

**Interfaces:**
- Consumes: `IdentityStore` (Tasks 2-3), `FaceEmbedder` (Task 4)
- Produces: fast-path intents `enrol_face` (with `args={'name': str}`) and `forget_identities`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_voice_fast_path.py`:

```python
# Enrolment is voice-driven, so un-enrolment must be too -- otherwise the only way to undo it
# is SSH (spec section 5).
@pytest.mark.parametrize('utterance,name',[
    ('this is Carolyn','Carolyn'),
    ('Willie, this is Carolyn','Carolyn'),
    ('this is Howard','Howard'),
    ('remember this face as Storm','Storm'),
    ('learn this face as Carolyn','Carolyn'),
])
def test_enrolment_phrasings_capture_the_name(utterance,name):
    r=_fast(utterance)
    assert r is not None and r['intent']=='enrol_face'
    assert r['args']['name']==name

@pytest.mark.parametrize('utterance',[
    'forget everyone',
    'forget all faces',
    'Willie, forget everyone',
])
def test_forget_phrasings_reach_the_forget_intent(utterance):
    assert _intent(utterance)=='forget_identities'

def test_enrolment_does_not_fire_on_ordinary_speech():
    # fullmatch keeps "this is nice" from enrolling somebody called "nice".
    assert _intent('this is nice') != 'enrol_face'
```

- [ ] **Step 2: Run to verify failure**

```bash
scp tests/test_voice_fast_path.py voice.py hhimmel@<ip>:/tmp/
ssh hhimmel@<ip> 'cd ~/rover && PYTHONPATH=/tmp:/home/hhimmel/rover venv/bin/python3 -m pytest /tmp/test_voice_fast_path.py -q'
```

Expected: the new tests FAIL (`_fast_path` returns `None`); the 23 existing ones pass.

- [ ] **Step 3: Add the patterns**

In `voice.py`, after `_DATE_PATTERN`:

```python
# Name is captured, so this cannot go in _FAST_PATH_PATTERNS (whose entries carry no args).
# Handled inline in _fast_path() alongside time and date. Deliberately narrow: a false
# positive here enrols a stranger under a wrong name, which is worse than a miss.
_ENROL_PATTERN=re.compile(
    _ADDRESS+r"(?:this is|remember this face as|learn this face as) "
    r"(?P<name>[A-Za-z][A-Za-z'\-]{1,30})"+_TRAILER,re.I)

_FORGET_PATTERN=re.compile(
    _ADDRESS+r"(?:forget (?:everyone|all faces|everybody)|"
    r"delete (?:all )?(?:faces|identities))"+_TRAILER,re.I)
```

In `_fast_path`, after the `_DATE_PATTERN` block:

```python
        m=_ENROL_PATTERN.fullmatch(norm)
        if m:
            return {'intent':'enrol_face','args':{'name':m.group('name').capitalize()},
                    'reply':''}
        if _FORGET_PATTERN.fullmatch(norm):
            return {'intent':'forget_identities','args':{},'reply':''}
```

- [ ] **Step 4: Run to verify pass**

```bash
scp voice.py tests/test_voice_fast_path.py hhimmel@<ip>:/tmp/
ssh hhimmel@<ip> 'cd ~/rover && PYTHONPATH=/tmp:/home/hhimmel/rover venv/bin/python3 -m pytest /tmp/test_voice_fast_path.py -q'
```

Expected: PASS, 32 tests.

- [ ] **Step 5: Commit**

```bash
git add voice.py tests/test_voice_fast_path.py
git commit -m "Add voice enrolment and forget-everyone fast-path intents

'Willie, this is Carolyn' enrols; 'forget everyone' wipes. Enrolment is
voice-driven so un-enrolment must be too, otherwise the only way to undo it
is SSH.

Both patterns are deliberately narrow. A false positive enrols a stranger
under the wrong name, which is worse than a miss -- the opposite of the
tier 1 trade-off the time and date patterns make."
```

---

### Task 6: Wire recognition into `brain.py`

The integration task. Everything before this is inert.

**Files:**
- Modify: `brain.py` (`__init__`, `_tick`, `close`)

**Interfaces:**
- Consumes: everything from Tasks 2-5
- Produces: no new public API; behaviour only

- [ ] **Step 1: Construct the subsystems**

In `RoverBrain.__init__`, alongside the other `_init_device` calls:

```python
        self.identities=identity.IdentityStore()
        self.face=_init_device(recognition.FaceEmbedder,'recognition')
        # Single-slot: if a recognition is in flight, drop the frame rather than queue it.
        # Under load this recognises less often instead of building a backlog -- the same
        # failure direction the rest of the rover takes.
        self._recog_q=queue.Queue(maxsize=1)
        self._recog_thread=threading.Thread(target=self._recognition_loop,daemon=True)
        self._recog_thread.start()
```

Add `import identity,recognition` at the top.

- [ ] **Step 2: Add the worker loop**

Never on the tick thread — 50-100ms per embedding is far past what `_tick` tolerates, and
`retrieval_task._grasp()` and `_wave()` were both rewritten for exactly this reason.

```python
    def _recognition_loop(self):
        while self._running:
            try: frame,box=self._recog_q.get(timeout=0.5)
            except queue.Empty: continue
            try:
                vec=self.face.embed(frame,box)
                if vec is None: continue
                hit=self.identities.match(vec,'face')
                if hit is None: continue          # unknown: stay silent, do not guess
                name,_dist=hit
                room=self.world_model.current_room() if self.world_model else None
                self.identities.note_seen(name,room=room)
                if self.identities.should_greet(name):
                    self.voice.speak(f'Hello {name}.')
            except Exception as e:
                log.warning(f'Recognition failed: {e}')   # never kill the worker
```

- [ ] **Step 3: Expose the frame from `vision.py`**

**The spec is wrong on this point** and should be corrected: it states `vision.py` is unchanged,
but `detect()` captures a frame internally and discards it, returning only
`{'class','conf','bbox','frame_w','frame_h'}`. Recognition needs the pixels. The minimal
honest change is to retain the last frame rather than have `recognition.py` capture a second,
differently-timed one whose contents no longer match the boxes.

In `_detect_cpu` and `_detect_hailo`, immediately after the frame is obtained:

```python
            self._last_frame=frame
```

And on `ObjectDetector`:

```python
    def last_frame(self):
        """The frame the most recent detect() ran on, or None.

        Retained so face recognition can crop the same pixels the boxes were computed from.
        Capturing a fresh frame instead would pair current pixels with stale boxes, which
        misaligns exactly when someone is moving -- the case that matters."""
        return getattr(self,'_last_frame',None)
```

Initialise `self._last_frame=None` in `__init__`.

- [ ] **Step 4: Feed the worker from the tick**

Where `_tick` already handles detections. Note the key is **`bbox`**, not `box`:

```python
            if self.face is not None and self.face.available:
                frame=self.detector.last_frame()
                if frame is not None:
                    for d in detections:
                        if d.get('class')!='person': continue
                        try: self._recog_q.put_nowait((frame,d['bbox']))
                        except queue.Full: pass  # already recognising; drop this frame
                        break                    # one person per tick is enough
```

- [ ] **Step 5: Act on the enrolment and forget intents**

Task 5 produces the intents; without this they resolve and then nothing happens. In
`_act_on_intent`'s dispatch:

```python
        if intent=='forget_identities':
            self.identities.forget_all()
            self.voice.speak('I have forgotten everyone.')
            return
        if intent=='enrol_face':
            name=args.get('name')
            if not name: return
            self._enrol_face(name)
            return
```

And the capture itself. It runs on the recognition worker, not the tick thread, for the same
reason recognition does — it holds the camera for roughly two seconds:

```python
    def _enrol_face(self,name):
        """Capture several poses and store them under one name.

        Multiple vectors per identity is the point: matching against a handful of poses is
        markedly more robust than against a single shot, and enrolment is the one moment where
        collecting them costs nothing."""
        if self.face is None or not self.face.available:
            self.voice.speak("I can't see well enough to learn a face right now."); return
        vecs=[]
        for _ in range(config.ENROL_SAMPLE_COUNT):
            frame=self.detector.last_frame()
            dets=[d for d in (self.detector.detect(classes=['person']) or [])
                  if d.get('class')=='person']
            if frame is not None and len(dets)==1:
                v=self.face.embed(frame,dets[0]['bbox'])
                if v is not None: vecs.append(v)
            elif len(dets)>1:
                self.voice.speak('I can see more than one person. Let me see just you.'); return
            time.sleep(config.ENROL_SAMPLE_INTERVAL_S)
        if len(vecs)<config.ENROL_MIN_SAMPLES:
            self.voice.speak(f"I couldn't get a clear enough look at you, {name}."); return
        self.identities.enrol(name,'face',vecs)
        self.voice.speak(f'I will remember you, {name}.')
```

Config constants:

```python
ENROL_SAMPLE_COUNT=8         # frames attempted during a voice enrolment
ENROL_SAMPLE_INTERVAL_S=0.25 # ~2s total, long enough for a person to shift pose slightly
ENROL_MIN_SAMPLES=4          # below this, refuse rather than enrol a weak identity
```

- [ ] **Step 6: Shut it down cleanly**

In `close()`, guarded the way the 2026-08-21 review required so a failure here cannot skip
motor or sensor cleanup:

```python
        try:
            if self._recog_thread is not None: self._recog_thread.join(timeout=2.0)
        except Exception as e: log.warning(f'Recognition thread join failed: {e}')
```

- [ ] **Step 7: Verify no regression with the feature off**

`ENABLE_FACE_RECOGNITION` is still `False`, so this must change nothing.

```bash
ssh hhimmel@<ip> 'sudo systemctl stop willy-rover && cd ~/rover && \
  venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -5; sudo systemctl start willy-rover'
```

Expected: the same 4 pre-existing failures as the 2026-08-25 baseline (`test_brain_reset_gate`, `test_brain_wave`, `test_navigation`, `test_sim_hardware`) and **no new ones**. Stop the service first — a full suite run against a live service starved the CPU and made the wake word unresponsive on 2026-08-25.

- [ ] **Step 8: Commit**

```bash
git add brain.py vision.py config.py
git commit -m "Wire face recognition into the brain

Recognition runs on a dedicated worker with a single-slot queue, never on
the tick thread: an embedding costs 50-100ms, and a blocking call on the
tick thread means a fault cannot preempt it -- the same reason _grasp() and
_wave() were rewritten as step machines.

A full queue drops the frame rather than backing up, so load degrades to
recognising less often. An unknown face stays silent rather than guessing."
```

---

### Task 7: Live bring-up and threshold calibration

No code. This is where the provisional numbers become measured ones.

- [ ] **Step 1: Enable the feature**

Set `ENABLE_FACE_RECOGNITION=True` in `config.py`, deploy, restart.

- [ ] **Step 2: Measure within-person distances**

```bash
ssh hhimmel@<ip> 'sudo systemctl stop willy-rover && cd ~/rover && \
  venv/bin/python3 scripts/face_recognition_bench.py Howard'
```

Repeat for Carolyn. Record both.

- [ ] **Step 3: Set the threshold from the measurements**

`FACE_MATCH_MAX_DISTANCE` goes **above** the largest within-person distance and **below** the
smallest between-person distance.

If those ranges overlap, **do not simply loosen the threshold** — that trades a missed
greeting for a wrong-name greeting, which is the failure the whole design is biased against.
Investigate in this order: lighting and distance during enrolment; whether `alignCrop` is
receiving good landmarks (log the YuNet score); then re-enrol with more varied poses. Only if
all three are clean is the embedder itself the suspect, and then the fix is swapping SFace for
ArcFace `w600k_r50` — a `recognition.py`-local change, since `identity.py` is dimension-agnostic.

- [ ] **Step 4: Enrol both people by voice**

Say "Willie, this is Howard", then the same for Carolyn. Confirm each is acknowledged.

- [ ] **Step 5: Verify end to end**

Walk into view. Expect a greeting by name, once, not repeated on every frame. Have the other
person walk in; expect their name, not yours. Have a stranger walk in; expect silence.

- [ ] **Step 6: Commit the measured threshold**

```bash
git add config.py
git commit -m "Enable face recognition and set the measured match threshold

Threshold set from bench measurements of within- and between-person
distances rather than the provisional guess it replaces."
```

---

## Not in this plan

- **Pet recognition.** Gated on spec §10's spike, which needs photos of Storm and of other dogs. Its own plan once the spike reports.
- **Per-person memory.** The `memory.db` migration is the riskiest edit in the feature and needs a backup, a reversible migration, and a test against a copy of the real database. Its own plan and its own review.
- **A new FRD requirement for biometric retention.** Spec §7 records that enrolment goes beyond what FR-1800-002 permits. That is an owner decision and belongs in the FRD, not in this plan.
