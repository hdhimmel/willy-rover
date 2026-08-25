# Person and Pet Recognition — Design

Status: **DESIGN APPROVED, NOT IMPLEMENTED.** No code written. §10's spike must run
before the pet half of §4/§5 is built — it can invalidate that half's approach.

Date: 2026-08-25

## 1. Problem

Willy cannot tell people apart. `vision.py` detects the COCO `person` and `dog` classes
(both present in `models/coco.txt` and live today), so he knows *a* human is present and
*a* dog is present, but every human is interchangeable and Storm is indistinguishable from
any visiting dog.

`memory_store.py` (FR-1900) can hold facts he has been *told* — "Carolyn is my wife" —
and `get_context_for()` surfaces them by substring match on the fact key. That is
knowledge, not recognition. Nothing connects a name to a face.

The owner wants Willy to know three individuals: Howard, Carolyn, and the dog Storm.

## 2. Scope

In scope, as agreed 2026-08-25:

1. **Greet and address by name** on sight.
2. **Per-person memory** — facts and instructions scoped to the person who taught them,
   so Howard's and Carolyn's do not collide.
3. **Presence awareness** — "last seen" only: name, timestamp, and room if the world
   model knows one. A decaying record, not continuous tracking.
4. **Storm distinguished from other dogs**, not merely detected as a dog.

Explicitly **out of scope**:

- **Permissions by person.** Deliberately excluded. Nothing about who may command motion,
  the arm, or shutdown depends on identity. This is load-bearing for the whole design:
  it means a misidentification is embarrassing, never dangerous, which is what permits
  the practical accuracy target in §7 and the CPU-cost trade-offs in §4.
- **Voice/speaker identification.** Face only for now. §4's boundaries are drawn so a
  voice-embedding source can be added later without reworking the store or the matcher.
- **Re-identification across frames / multi-person tracking.** See §5.

## 3. Why this approach (over alternatives)

Three approaches were considered. **Hybrid (B) was chosen.**

**A — All CPU.** SCRFD face detection plus ArcFace embedding, both ONNX on CPU; a generic
CPU embedding for pet crops. Needs no new heavy dependencies: `onnxruntime` 1.28.0,
`cv2` 5.0.0, `numpy`, `sklearn` and `PIL` are all already installed on the rover
(`onnxruntime` because openwakeword uses it). Rejected as the primary path because it puts
all of the cost on the same 4 cores Whisper runs on, and CPU contention degrading voice is
not hypothetical here — it was observed live on 2026-08-25 when a 110-second test suite
run made the wake word unresponsive.

**B — Hybrid. CHOSEN.** Person and dog boxes come from the Hailo YOLO pipeline already
running. Face embedding runs on CPU (ArcFace ONNX) — affordable because it fires once per
person-detection *event*, not per frame. Pet embedding runs on `resnet_v1_50_h10.hef`,
which is already present in `/usr/share/hailo-models/` and already compiled for this
rover's chip.

**C — Full Hailo.** Would need an ArcFace HEF, requiring the Hailo Dataflow Compiler on a
separate x86 Ubuntu machine — the same blocker that has stalled Hailo-Whisper since
2026-08-21. Ruled out as unavailable, not as wrong. If an x86 machine appears, migrating
the face embedder from CPU to Hailo is a `recognition.py`-local change by §4's boundaries.

### 3.1 Storm needs no trained classifier

The owner initially chose "train a classifier to distinguish Storm". The design instead
treats Storm the same way as a person: crop the dog box, embed it, match by nearest
neighbour against a handful of enrolled vectors. **One store, one matcher, two embedding
sources.** No training, no dataset collection, and enrolling Storm is the same gesture as
enrolling Carolyn.

This is unproven and §10 exists to test it before it is relied upon. ImageNet-style
features separating *individual* dogs should work against a different-breed visitor and
may fail against a similar-looking one. If the spike fails, the fallback is the trained
classifier originally chosen; §4's boundaries confine that change to `recognition.py`.

### 3.2 Unverified premise: the `_h8l` model files

`/usr/share/hailo-models/` also contains `scrfd_2.5g_h8l.hef` (a face detector) and
`yolov5s_personface_h8l.hef`. The `_h8l` suffix denotes Hailo-8L; **this rover is a
Hailo-10H**, and HEFs are architecture-specific. These are therefore assumed **not**
loadable and nothing in this design depends on them. Only `_h10` files are treated as
usable. Confirm by attempting a load before any future work assumes otherwise — if they
do load, face *detection* could also move off the CPU.

## 4. Architecture

Three new units and one modified. The boundary that matters: **`identity.py` knows nothing
about cameras, and `recognition.py` knows nothing about names.** Either can be replaced
without touching the other.

**`identity.py` — store and matcher.** Takes an embedding and a kind (`face` | `pet`);
returns the best-matching name with a distance score, or `None` for unknown. Owns
persistence, enrolment, wipe, and the "last seen" record. No camera, no models, no frames.
Pure vectors in, names out — which makes it the one part of this feature that is fully
unit-testable off-rover (see §8).

Storage is its **own SQLite file**, `identities.db` under `WILLY_MEMORY_ROOT` —
deliberately not a table inside `memory.db`. Wiping every enrolled identity becomes a
single file delete rather than a careful `DELETE`, and the biometric data sits on a visibly
separate boundary from ordinary learned facts, which is what makes §7's privacy position
defensible.

**`recognition.py` — embedding source.** Turns *(frame, detection box)* into a vector.
ArcFace ONNX on CPU for faces; `resnet_v1_50_h10.hef` on the Hailo for pet crops. The only
hardware-dependent unit. Follows `vision.py`'s established pattern: missing models or an
absent device mean the subsystem logs and stays disabled, never raises into the caller.
The two sources degrade **independently** — no Hailo means pets stop being recognised
while faces keep working.

**`vision.py` — unchanged.** It already returns `person` and `dog` detections with boxes.
Recognition consumes its output; it does not reach inside it.

**`memory_store.py` — modified.** Per-person memory requires a person dimension on
`environment_facts`. This is the riskiest edit in the feature and the only one touching a
live database holding real data; see §6.

## 5. Data flow

**Recognition.** `brain._tick()` already receives detections. A `person` or `dog` box
triggers recognition **on a dedicated worker thread, never on the tick thread.** This is
not a stylistic preference: `retrieval_task.py::_grasp()` and `brain.py::_wave()` were both
rewritten as deadline-serviced step machines precisely because a blocking call on the tick
thread meant a fault could not preempt it. ArcFace on CPU is 50-100ms, well past that bar.

The worker has a **single-slot queue**: if a recognition is already in flight, new frames
are dropped rather than queued. Under load the system recognises *less often* rather than
accumulating a backlog — the same failure direction the rest of the rover already takes.

**Presence.** Results update a "last seen" record in `identity.py`: name, timestamp, and
room if the world model knows one. There is no tracking, no re-identification across
frames, and no attempt to follow a person between detections. Presence queries read this
decaying record.

**Greeting.** Debounced off the same record: a person is greeted once per *session*, where
a session ends once they have been unseen for a configured number of minutes. Without this
he greets on every frame in which he sees a face. Greeting uses `voice.speak()`, which
enqueues and returns immediately.

**Enrolment.** "Willy, this is Carolyn" enters through the voice fast path, captures
several frames over roughly two seconds, embeds each, and stores **multiple vectors per
identity** — matching against a handful of poses is markedly more robust than against one
shot. He speaks confirmation. He refuses cleanly, with a spoken reason, when he sees no
face or sees more than one person.

**Un-enrolment.** A `forget everyone` command deletes `identities.db`. Enrolment is
voice-driven, so un-enrolment must be too; otherwise the only way to undo it is SSH.

### 5.1 Known weakness: who is speaking

Per-person memory needs a "who am I talking to", and it is inferred from **the last face
seen**. Face and voice are different modalities — the person speaking may not be the
person in frame.

Because permissions are out of scope (§2), the worst case is recalling Carolyn's facts
while answering Howard: annoying, not harmful. This is recorded as a real soft spot rather
than buried. A voice-embedding source is the proper fix and is what §4's boundaries leave
room for.

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `memory.db` migration corrupts real learned facts | Back up first; reversible migration; test against a copy of the real `memory.db` before it runs on the rover. Highest-risk edit in the feature. |
| ResNet embeddings cannot separate individual dogs | §10 spike runs **before** the pet half is built. Fallback is the trained classifier. |
| Recognition CPU cost degrades voice | Event-driven not per-frame; dedicated worker; single-slot queue. Contention is a measured, not theoretical, risk on this rover. |
| Greeting the wrong person by name | Conservative match threshold (§7); uncertain resolves to unknown and he says nothing. |
| `_h8l` HEFs assumed unusable | Nothing depends on them (§3.2). |
| Recognition raising into the tick thread | `recognition.py` fails closed, mirroring `vision.py::_detect_hailo()`'s 2026-08-21 fix. |

## 7. Privacy and accuracy posture

**Embeddings only. Enrolment images are converted to vectors and deleted immediately.**
An embedding cannot be viewed as a face. Re-enrolment requires new photos — accepted as
the cost of not keeping a folder of family photographs on the rover.

This is a deliberate, explicit addition to what FR-1800-002 permits. That requirement says
camera frames are "not transmitted or persisted beyond what's needed for the current
task", and enrolment persists derived biometric data indefinitely by design. It is
recorded here as a decision, not slipped in as an exception. **A new requirement should be
added to the FRD rather than stretching FR-1800-002 to cover it.**

The existing privacy flag needs no new code: recognition rides on `vision.py`, which must
already check `privacy.camera_enabled()` before opening the device, so setting
`MIC_CAMERA_DISABLE_FLAG_PATH` suspends recognition.

**Accuracy biases toward "unknown".** Greeting the wrong person by name is the failure that
actually stings, so an uncertain match resolves to `None` and he says nothing rather than
guessing. Unknown people are still recorded present, unnamed.

Defaults: `ENABLE_FACE_RECOGNITION=False`, matching the convention already used by
`ENABLE_HAILO_LLM` and `ENABLE_OBJECT_RETRIEVAL`.

## 8. Testing

The §4 boundary was drawn partly to make this possible.

**`identity.py` — real unit tests, no hardware.** Vectors in, names out. Enrolment,
matching, threshold edges either side of the cutoff, multiple vectors per identity,
unknown-below-threshold, wipe. Synthetic embeddings; no mocks.

Note the constraint that decides *where* those tests run: `numpy` is **not** installed on
the owner's Windows laptop — `voice.py` cannot be imported there at all. Either
`identity.py` avoids importing numpy at module scope (using stdlib arithmetic for cosine
distance over short vectors), or these tests only ever run on the rover. The former is
preferred and is a real design constraint on `identity.py`, not an afterthought.

**`recognition.py` — bench script, not unit tests.** Needs the camera and the Hailo. Follows
`scripts/wheel_current_test.py`'s precedent: a committed, repeatable measurement rather
than a hand-typed one.

**Enrolment phrasings — pattern tests** in `tests/test_voice_fast_path.py`, which exists as
of `c6473ee`. The time/date patterns regressed three times for want of exactly this.

**Migration — tested against a copy of the real `memory.db`**, not a synthetic one.

## 9. Open questions for implementation

1. Which ArcFace ONNX model, and where does it come from? Not present on the rover; must
   be fetched. `models/` is gitignored.
2. Face *detection* on CPU: SCRFD ONNX, or crop from the YOLO person box? The latter needs
   no new model but gives a looser crop, which costs embedding quality.
3. What exactly is the match threshold, in the chosen model's distance metric? §7 fixes the
   *direction*; the number needs measuring against real enrolments.
4. How long is a greeting "session"?
5. Does per-person scoping apply to learned *instructions* as well as facts, or facts only?

## 10. Prerequisite spike — run before building the pet half

**Question:** do `resnet_v1_50_h10.hef` embeddings separate Storm from other dogs by
nearest-neighbour, without training?

**Method:** enrol several photos of Storm; embed; compare cosine distance against further
Storm photos versus photos of other dogs, ideally including one of similar breed and
colour. Report the separation between the two distance distributions.

**Decision:** clear separation → build §4/§5 as written. Poor separation → the pet half
reverts to a trained classifier and this document is revised before implementation. The
human half is unaffected either way and can proceed in parallel.

**Cost of skipping it:** building the store and matcher around an approach that does not
work, then discovering it only once Storm is standing in front of the rover.
