# Hailo Voice Offload (STT + LLM) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move voice intent-parsing (LLM) onto the Hailo-10H NPU alongside the
already-shipped vision backend, sharing the NPU in-process; leave STT scaffolded
but blocked until an x86 compilation machine is available.

**Architecture:** Option A from the spec's §10.3 — one Hailo device shared
in-process by vision and the voice LLM, no separate device-manager daemon. The
open question this plan resolves first (Task 1) is whether that sharing needs a
bespoke `VDevice`-injection rework of `vision.py::_load_hailo()`, or whether
`picamera2.devices.Hailo`'s own class-level `TARGET`/`TARGET_REF_COUNT` singleton
(confirmed present in `picamera2/devices/hailo.py`, already relied on implicitly
by the shipped vision code) already shares correctly across two different HEFs
in one process, with zero rework needed. Task 2 only exists if Task 1 finds
rework is required.

**Tech Stack:** `picamera2.devices.Hailo` (already a project dependency via the
shipped vision backend), `hailo_platform`/HailoRT Python bindings, existing
`ai_provider.py::AIProvider`/`AIResult` interface.

**Spec:** `docs/superpowers/specs/2026-08-21-hailo-npu-offload-design.md` — read
§10 in full before starting; it supersedes §3/§4 for the voice half.

## Global Constraints

- The Hailo-10H `VDevice` is exclusive to one process at a time
  (`HAILO_OUT_OF_PHYSICAL_DEVICES(74)` on a second claim from a *different*
  process). `willy-rover.service` must be **stopped** before any standalone
  verification script touches the NPU — this is load-bearing, not just a
  precaution (spec §10.2).
- Phi-2 is **not** available on this rover's delivery path. The real Hailo
  GenAI Model Zoo set is `llama3.2:3b`, `deepseek_r1_distill_qwen:1.5b`,
  `qwen2.5-coder:1.5b`, `qwen2.5-instruct:1.5b`, `qwen2:1.5b` (spec §10.1).
  This plan targets `qwen2:1.5b` unless Task 3's reliability batch says
  otherwise.
- `ENABLE_HAILO_LLM` must default `False` and gate the whole subsystem, same
  pattern as `ENABLE_HAILO_VISION` — one flag, independently toggleable,
  fail-safe fallback to the existing CPU `LocalAIProvider` on any load error.
- No test framework exists for hardware-dependent code on the Windows dev
  machine (no HailoRT, no device import). All real verification happens live
  on the rover, via SSH (`hhimmel@willie.local`, key-based, confirmed working
  2026-08-23) or Cockpit.
- STT (Task 5) cannot be implemented past scaffolding until an x86 Ubuntu
  machine is available to run the Hailo Dataflow Compiler (spec §10.4) — the
  compiler does not run on ARM, and no Whisper HEF exists for this rover yet.
- Do not touch `_load_hailo()`'s CSI camera / vision detection path itself —
  only its `Hailo(...)` device-construction line is in scope if Task 1 finds
  rework is needed.

---

### Task 1: On-rover experiment — does dual-HEF sharing need a rework?

**Files:**
- Create: `~/rover/experiments/hailo_dual_load.py` (on the rover directly via
  SSH — this is a throwaway investigation script, not committed to git)

**Interfaces:**
- Consumes: nothing from other tasks — this is the first task.
- Produces: a written finding (Task 1's report) that Task 2 and Task 3 are
  gated on. Specifically: whether `picamera2.devices.Hailo(hef_path)` can be
  constructed a second time, for a *different* HEF, while vision's existing
  instance is alive in the same process — and whether that requires
  HailoRT ≥ 5.3.0 or works on the currently-installed 5.1.1.

This is investigation work by design (spec §9 bullet 1 and §10.3 both call it
an open question to resolve at implementation time, not something to guess
here) — the steps below are a concrete, bounded methodology with a clear
pass/fail read, not a placeholder.

- [ ] **Step 1: Confirm the installed HailoRT version and find a real GenAI HEF**

Over SSH:
```bash
ssh hhimmel@willie.local
python3 -c "import hailo_platform; print(hailo_platform.__version__)" 2>&1 || \
  dpkg -l | grep -i hailort
find / -iname "*.hef" 2>/dev/null
ls /usr/share/hailo-models/ 2>/dev/null
```

Record the exact version string and whatever `.hef` files already exist on
the device (vision's `yolov8m_h10.hef` will show up — that one doesn't help
here, it's the same model family vision already loads). If no GenAI LLM HEF
is present, check whether one is reachable without the `hailo-ollama` binary
specifically — e.g. a direct download URL from Hailo's model zoo for
`qwen2:1.5b`'s HEF. If the only way to obtain one requires `hailo-ollama` or
a HailoRT version this device doesn't have, **stop here and write that up as
the finding** — it means Task 1's remaining steps are blocked on prerequisite
2 (the HailoRT upgrade), not just guessable in advance.

- [ ] **Step 2: Write the dual-load experiment script**

```python
# ~/rover/experiments/hailo_dual_load.py
# Run with willy-rover.service STOPPED. Tests whether a second Hailo() instance,
# for a different HEF, can coexist with a first one in the same process --
# i.e. whether picamera2.devices.Hailo's class-level VDevice sharing (TARGET/
# TARGET_REF_COUNT) extends across different models, not just repeated loads
# of the same one. This is the load-bearing question for spec section 10.3.
import sys
from picamera2.devices import Hailo

VISION_HEF = '/usr/share/hailo-models/yolov8m_h10.hef'
LLM_HEF = sys.argv[1] if len(sys.argv) > 1 else None
if not LLM_HEF:
    print('Usage: python3 hailo_dual_load.py /path/to/llm.hef')
    sys.exit(1)

print(f'Loading vision HEF: {VISION_HEF}')
vision = Hailo(VISION_HEF)
print('Vision HEF loaded OK. Input shape:', vision.get_input_shape())

print(f'Loading second HEF while vision handle is still open: {LLM_HEF}')
try:
    llm = Hailo(LLM_HEF)
    print('SECOND HEF LOADED OK -- sharing works without rework.')
    print('LLM input shape:', llm.get_input_shape())
    llm.close()
except Exception as e:
    print(f'SECOND HEF FAILED: {type(e).__name__}: {e}')
    print('This means Task 2 (VDevice injection rework) is required.')
finally:
    vision.close()
```

- [ ] **Step 3: Run it and record the result**

```bash
sudo systemctl stop willy-rover.service
cd ~/rover
python3 experiments/hailo_dual_load.py /path/to/the/llm/hef/found/in/step1
sudo systemctl start willy-rover.service
```

Two possible outcomes, both are a valid, useful finding:
- **`SECOND HEF LOADED OK`** — sharing works via the existing class-level
  singleton. Skip Task 2 entirely; proceed straight to Task 3 with
  `picamera2.devices.Hailo(config.HAILO_LLM_MODEL_PATH)` as `HailoIntentModel`'s
  loading approach, same shape as vision's own `_load_hailo()`.
- **`SECOND HEF FAILED` with `HAILO_OUT_OF_PHYSICAL_DEVICES` or similar** —
  confirms spec §10.2's exclusivity finding extends to same-process,
  different-model loads too. Task 2 is required: rework `_load_hailo()` to
  accept an externally-constructed device handle instead of constructing its
  own, so both vision and the LLM wrapper share one.

- [ ] **Step 4: Write up the finding**

Append a dated note to this plan file's Task 1 section (edit this file
directly) recording: HailoRT version, which HEF was tested, the exact
output, and which branch (skip Task 2 / do Task 2) applies. Delete
`~/rover/experiments/hailo_dual_load.py` from the rover afterward — it's a
throwaway script, not part of the deployed codebase, so it should not survive
in `~/rover/` past this investigation.

---

### Task 2: Rework `_load_hailo()` for shared device injection

**Only do this task if Task 1 found sharing fails without it.** If Task 1
found the second `Hailo()` load succeeds unmodified, skip straight to Task 3
and delete this task's checkbox as not-applicable in the ledger.

**Files:**
- Modify: `vision.py:60-88` (`ObjectDetector._load_hailo()`)
- Modify: `brain.py` (`RoverBrain.__init__`, wherever `ObjectDetector()` is
  currently constructed)

**Interfaces:**
- Consumes: Task 1's confirmed failure mode (exact exception type/message) to
  know what to catch/handle.
- Produces: `ObjectDetector.__init__` accepting an optional pre-built device
  handle; `RoverBrain` owning construction of that handle once and passing it
  to both `ObjectDetector` and Task 3's `HailoIntentModel`.

The exact exception type Task 1 hit is the only unknown here — the injection
shape itself is fully determined by the existing code (`vision.py:27-34,60-88`)
and does not need to wait.

- [ ] **Step 1: Add an optional injected-device parameter to `ObjectDetector.__init__`**

Current (`vision.py:27-34`):
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

New:
```python
class ObjectDetector:
    def __init__(self,hailo_device=None):
        # hailo_device: pre-constructed shared device handle from RoverBrain, only
        # used when Task 1 found dual same-process HEF loads fail without one.
        # None (the default) preserves today's behaviour exactly -- _load_hailo()
        # constructs its own, same as before this task.
        self._hailo_backend=config.ENABLE_HAILO_VISION
        self._enabled=config.ENABLE_HAILO_VISION or config.ENABLE_OBJECT_RETRIEVAL
        self._cap=None; self._model=None; self._hailo=None; self._picam2=None
        self._hailo_labels=None; self._hailo_input_hw=None
        self._injected_device=hailo_device
        if self._hailo_backend: self._load_hailo()
        elif self._enabled: self._load()
```

- [ ] **Step 2: Use the injected device in `_load_hailo()` if present, falling back to today's construction otherwise**

Modify `vision.py:71-88`'s try block — replace the line
`self._hailo=Hailo(config.HAILO_YOLO_MODEL_PATH)` with:
```python
            if self._injected_device is not None:
                self._hailo=self._injected_device  # already constructed/shared by RoverBrain
            else:
                self._hailo=Hailo(config.HAILO_YOLO_MODEL_PATH)  # unchanged fallback
```
Everything else in `_load_hailo()` — the `SIMULATE_HARDWARE` guard, the missing-
model-file check, the `except Exception` fail-safe wrapper — stays exactly as
written. `_load()` (the CPU/Arducam path) is untouched entirely.

- [ ] **Step 3: Construct the shared device once in `RoverBrain.__init__`, pass it to `ObjectDetector`**

Find where `ObjectDetector()` is currently constructed in `brain.py::RoverBrain.__init__`
(same `self._i2c`-style singleton section other hardware objects live in) and
change it to construct the device Task 1's script proved works, then pass it:
```python
self.detector=ObjectDetector(hailo_device=self._hailo_device)  # self._hailo_device built above
```
Use Task 1's exact successful construction call (recorded in Task 1 Step 4's
write-up) for `self._hailo_device` — do not re-derive it here.

- [ ] **Step 4: Live-verify vision still works exactly as before**

Same check as `docs/superpowers/plans/2026-08-21-hailo-vision-csi-camera.md`'s
Step 5: stop the service, run a standalone detection round-trip, confirm no
regression versus the currently-deployed behavior. This is live, currently-
deployed code — do not skip this because the change looks small.

- [ ] **Step 5: commit**

```bash
git add vision.py brain.py
git commit -m "Rework ObjectDetector to accept an injected shared Hailo device"
```

---

### Task 3: JSON-reliability test harness for the target LLM model

**Files:**
- Create: `experiments/llm_reliability_batch.py` (repo-tracked this time —
  it's reusable, not throwaway, since it needs to run again if the model
  choice changes)

**Interfaces:**
- Consumes: `ai_provider.py::AIProvider.ask_sync(prompt,system=None,schema=None,history=None) -> AIResult`
  — the same interface `voice.py::_interpret_local()` already calls on
  `self._local_ai`. This harness must work against *any* object exposing that
  method, so it can run against the current CPU `LocalAIProvider` now (as a
  smoke test of the harness itself) and against Task 4's `HailoIntentModel`
  once that exists.
- Produces: a pass/fail report per test case, and an aggregate reliability
  percentage — the number that decides whether `qwen2:1.5b` is usable or a
  simpler prompt/schema is needed first (spec §6, promoted from contingency
  to hard gate by §10.1).

This can be built and smoke-tested against the CPU path **right now**, with
no Hailo hardware or prerequisite involved — only re-running it against the
real target model is blocked (on Task 1/2 landing and prerequisite 2).

- [ ] **Step 1: Write the test utterance batch**

Pull the exact intent list `_interpret_local()`'s prompt already documents
(`voice.py:368-395` — read it in full before writing this list, it names
every intent and example phrasing verbatim). Build at least 3 real-sounding
utterances per intent, including ones with filler words the fast-path regex
wouldn't catch (this harness is specifically for utterances that *miss* the
fast path and reach the LLM):

```python
# experiments/llm_reliability_batch.py
TEST_CASES = [
    # (utterance, expected_intent, expects_args)
    ("can you go fetch the red ball for me", "retrieve", True),
    ("grab the blue cup off the floor", "retrieve", True),
    ("I need you to bring me my slippers", "retrieve", True),
    ("power yourself off", "shutdown", False),
    ("I think it's time you went to sleep", "shutdown", False),
    ("how's your status looking", "status", False),
    ("are you doing okay buddy", "status", False),
    ("what's your charge level at right now", "battery", False),
    ("do you have much juice left", "battery", False),
    # ... continue for every intent named in _interpret_local()'s prompt
]
```

- [ ] **Step 2: Write the harness runner**

```python
def run_batch(provider, cases):
    results = []
    for utterance, expected_intent, expects_args in cases:
        result = provider.ask_sync(utterance, schema={'intent': str, 'args': dict, 'reply': str})
        ok = (result.parse_success
              and result.payload.get('intent') == expected_intent
              and (bool(result.payload.get('args')) == expects_args))
        results.append((utterance, expected_intent, ok, result.payload, result.reason))
    passed = sum(1 for *_, ok, _, _ in results if ok)
    return results, passed / len(cases)
```

- [ ] **Step 3: Smoke-test against the existing CPU `LocalAIProvider`**

```bash
cd ~/rover
python3 -c "
from ai_provider import LocalAIProvider
from experiments.llm_reliability_batch import TEST_CASES, run_batch
p = LocalAIProvider()
results, rate = run_batch(p, TEST_CASES)
for u, exp, ok, payload, reason in results:
    print(f'{\"OK \" if ok else \"FAIL\"} [{exp}] {u!r} -> {payload} ({reason})')
print(f'Pass rate: {rate:.0%}')
"
```

Run this via SSH with the service stopped (it constructs a second
`LocalAIProvider`/`llama_cpp.Llama`, which will contend for CPU with the live
service's own instance otherwise). Confirm the harness itself works
end-to-end and the CPU baseline passes close to 100% — that's the control
that proves the harness logic is correct before pointing it at Hailo.

- [ ] **Step 4: Commit**

```bash
git add experiments/llm_reliability_batch.py
git commit -m "Add LLM intent-reliability test harness, smoke-tested against CPU baseline"
```

- [ ] **Step 5 (blocked on Task 1/2 landing and prerequisite 2): re-run against `HailoIntentModel`**

Once Task 4 exists, re-run the same script with `HailoIntentModel()` in place
of `LocalAIProvider()`. Record the pass rate. If it's meaningfully below the
CPU baseline, per spec §6/§10.1 this is now the primary risk, not a
contingency — do not enable `ENABLE_HAILO_LLM` live until this is addressed
(prompt simplification or accept the degradation, since
`confidence < LOCAL_LLM_CONFIDENCE_FLOOR` already routes to a clarification
request rather than a wrong action per existing FR-1500-005 behavior).

---

### Task 4: `HailoIntentModel` wrapper and `voice.py` wiring

**Blocked on:** Task 1's finding (and Task 2 if required), Task 3's
reliability batch passing an acceptable rate, and prerequisite 2 (HailoRT
upgrade, if Task 1 found the GenAI HEF path needs ≥5.3.0).

**Files:**
- Create: `hailo_llm.py`
- Modify: `config.py` — add `ENABLE_HAILO_LLM=False`, `HAILO_LLM_MODEL_PATH`
- Modify: `voice.py` — wherever `self._local_ai=LocalAIProvider()` is
  currently constructed in `_load_models()`

**Interfaces:**
- Consumes: `ai_provider.py::AIProvider` as the base class/interface shape
  (`ask_sync`, returning `AIResult` from `ai_provider.py:27-32`); Task 1/2's
  device-sharing approach (either bare `Hailo(HAILO_LLM_MODEL_PATH)`
  construction, or the injected-handle shape from Task 2).
- Produces: `HailoIntentModel.ask_sync(prompt,system=None,schema=None,history=None) -> AIResult`,
  a drop-in replacement for `LocalAIProvider` wherever `voice.py` holds
  `self._local_ai`.

The exact HailoRT/`picamera2.devices.Hailo` inference call for a GenAI-style
LLM HEF (prompt in, token stream or completed text out) is the one genuinely
open item from spec §9 bullet 1 — everything around it (the class shape, the
`AIResult` construction, the config gating, the fallback wiring) is fully
determined by the existing `ai_provider.py` interface and does not need to
wait.

- [ ] **Step 0 (prerequisite): extend Task 1's script to run one real inference call**

Before writing this task's real code, add one more block to
`~/rover/experiments/hailo_dual_load.py` (or a copy of it) that runs
`llm.run(...)` or whatever the actual GenAI inference call turns out to be —
consult the HailoRT Python API docs/examples for GenAI-style models at
implementation time, since §9 bullet 1 explicitly flags this as needing "a
closer read" rather than being knowable in advance. Record the exact call
signature and output shape (raw tokens? decoded string? does it stream?) in
this task's write-up before Step 1 below.

- [ ] **Step 1: Write `hailo_llm.py`'s class shape (inference call itself filled in from Step 0's finding)**

```python
# hailo_llm.py
import os
import config
from ai_provider import AIResult

class HailoIntentModel:
    """Drop-in replacement for LocalAIProvider (ai_provider.py) once Step 0's
    real inference call shape is confirmed on-device. ask_sync's signature and
    AIResult construction match ai_provider.py:27-32,155-158 exactly so
    voice.py::_interpret_local() does not need to know which backend it's
    talking to."""
    def __init__(self,hailo_device=None):
        model_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),config.HAILO_LLM_MODEL_PATH)
        if not os.path.exists(model_path):
            raise RuntimeError(f'Hailo LLM HEF not found at {model_path}')
        # TODO(Step 0 finding): construct the model handle here, using
        # hailo_device if provided (Task 2's injection) else constructing its
        # own via picamera2.devices.Hailo(model_path) if Task 1 found that
        # works standalone. Use Task 1/Task 2's exact confirmed construction
        # call -- do not re-derive it here.

    def ask_sync(self,prompt,system=None,schema=None,history=None):
        # TODO(Step 0 finding): the real inference call. Must return an
        # AIResult built the same way ai_provider.py's other providers do --
        # see ai_provider.py:27-32 for the exact fields (parse_success,
        # intent_confidence, action_confidence, safety_validation, payload,
        # reason). JSON-parse the model's output against `schema`, matching
        # the existing providers' parse-failure handling (parse_success=False,
        # a reason string, rather than raising) so voice.py's existing
        # `if not result.parse_success:` handling (voice.py:397-398) keeps
        # working unchanged.
        raise NotImplementedError('Fill in from Step 0 finding before this task ships.')
```

The two `TODO(Step 0 finding)` blocks are the plan's only remaining
placeholders, and they are placeholders on purpose: Step 0 is the actual
investigation that resolves them, run immediately before this step, not left
open-ended. Do not commit this file with either TODO still in it.

- [ ] **Step 2: gate behind `config.ENABLE_HAILO_LLM`, same fail-safe pattern as `ENABLE_HAILO_VISION`**

```python
# config.py, near ENABLE_HAILO_VISION
ENABLE_HAILO_LLM=False  # 2026-08-23: scaffolded, blocked on Task 1's device-sharing
                        # finding and Task 3's reliability batch passing. See spec
                        # section 10.1 -- targets qwen2:1.5b, not Phi-2.
HAILO_LLM_MODEL_PATH='models/hailo_qwen2_1_5b.hef'  # exact filename from Task 1 Step 1
```

- [ ] **Step 3: wire into `voice.py::_load_models()`, falling back to `LocalAIProvider` on any load failure**

Find where `self._local_ai=LocalAIProvider()` is currently constructed and
change it to:
```python
if config.ENABLE_HAILO_LLM:
    try:
        from hailo_llm import HailoIntentModel
        self._local_ai=HailoIntentModel()
    except Exception as e:
        log.warning(f'Hailo LLM unavailable, falling back to CPU: {e}')
        config.ENABLE_HAILO_LLM=False
if not config.ENABLE_HAILO_LLM:
    self._local_ai=LocalAIProvider()  # existing construction, unchanged
if not self._local_ai.available: raise RuntimeError('local LLM failed to load')
```

- [ ] **Step 4: live-verify via Task 3's harness before flipping the flag on for real use**

Run Task 3 Step 5 (the harness re-pointed at `HailoIntentModel`) and confirm
an acceptable pass rate before treating `ENABLE_HAILO_LLM=True` as safe to
leave on. Also confirm `voice.py`'s existing `_interpret_local()` call path
works end-to-end with a real spoken command that misses the fast path, not
just the harness in isolation.

- [ ] **Step 5: commit**

```bash
git add hailo_llm.py config.py voice.py
git commit -m "Add HailoIntentModel, wire ENABLE_HAILO_LLM with CPU fallback"
```

---

### Task 5: STT scaffolding (blocked on prerequisite 1 — x86 compilation machine)

**Files:**
- Create: `hailo_stt.py` (skeleton only)
- Modify: `config.py` — add `ENABLE_HAILO_STT=False`, `HAILO_STT_MODEL_PATH`

**Interfaces:**
- Consumes: nothing from Tasks 1-4 (STT and LLM are independent subsystems
  per spec §2 — the shared-device question Task 1 resolves applies to STT too
  once it's implementable, but the scaffolding here doesn't need that answer
  yet).
- Produces: `HailoWhisper.transcribe(pcm) -> str`, matching the shape
  `voice.py::_process_utterance()` already expects from `faster_whisper`
  (spec §4).

This task exists so the flag/fallback pattern is in place and reviewed before
the real blocker (an x86 Ubuntu machine to run the Hailo Dataflow Compiler)
clears — it does **not** attempt the Whisper HEF conversion or real
inference, since neither is possible without that machine.

- [ ] **Step 1: Add the config flag, defaulted off, matching the existing pattern**

```python
# config.py, near ENABLE_HAILO_VISION
ENABLE_HAILO_STT=False  # blocked on compiling a Whisper HEF via Hailo's Dataflow
                        # Compiler on a separate x86 Ubuntu machine (ARM/this rover
                        # can't run the compiler) -- see spec section 10.4. Do not
                        # enable until HAILO_STT_MODEL_PATH points at a real HEF.
HAILO_STT_MODEL_PATH='models/hailo_whisper.hef'  # does not exist yet
```

- [ ] **Step 2: Write the skeleton class, raising clearly if ever constructed**

```python
# hailo_stt.py
import os
import config

class HailoWhisper:
    """Blocked on prerequisite 1 (x86 Dataflow Compiler machine) -- see spec
    section 10.4. transcribe() matches voice.py::_process_utterance()'s existing
    faster_whisper call shape so this is a drop-in once the HEF exists."""
    def __init__(self):
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.HAILO_STT_MODEL_PATH)
        if not os.path.exists(model_path):
            raise RuntimeError(
                f'Hailo STT HEF not found at {model_path} -- this needs a Whisper '
                f'model compiled on a separate x86 Ubuntu machine via the Hailo '
                f'Dataflow Compiler; ARM cannot run the compiler. See spec section 10.4.')
        # Real loading/inference implementation blocked until that HEF exists --
        # do not guess the HailoRT call shape here.

    def transcribe(self, pcm):
        raise NotImplementedError('HailoWhisper is scaffolding only -- see class docstring.')
```

- [ ] **Step 3: Wire the fallback in `voice.py::_load_models()`, same fail-safe shape as the LLM/vision flags**

```python
if config.ENABLE_HAILO_STT:
    try:
        from hailo_stt import HailoWhisper
        self._whisper = HailoWhisper()
    except Exception as e:
        log.warning(f'Hailo STT unavailable, falling back to CPU: {e}')
        config.ENABLE_HAILO_STT = False  # so downstream code doesn't re-check a broken flag
if not config.ENABLE_HAILO_STT:
    # existing faster_whisper construction, unchanged
    ...
```

Since `HailoWhisper.__init__` always raises today (no HEF exists), this falls
back to the CPU path immediately and correctly — verify that live (start the
service, confirm voice still works via the CPU path, confirm the warning log
line appears) before committing.

- [ ] **Step 4: commit**

```bash
git add hailo_stt.py config.py voice.py
git commit -m "Scaffold Hailo STT behind ENABLE_HAILO_STT, blocked on x86 compilation machine"
```
