# Hailo-10H NPU Offload — Voice + Vision Design

Status: **PARTIALLY IMPLEMENTED — VISION SHIPPED, VOICE HALF NEEDS REDESIGN.**

- **Vision half** (§4's vision bullet, §5's vision paragraph, §7): implemented, live-verified on
  the rover, merged to `main` 2026-08-21. See `docs/superpowers/plans/2026-08-21-hailo-vision-
  csi-camera.md`. `config.ENABLE_HAILO_VISION=True`.
- **Voice half** (§2 items 1-2, §3's Whisper/Phi-2 bullets, §4's STT/LLM wrappers, §5's voice
  paragraph, §8 steps 4-6): **BLOCKED — do not write a plan against §3/§4 as originally
  written.** §9 told the implementer to re-verify model availability and the HailoRT API story
  before trusting this doc. That re-verification was done 2026-08-21 and found two load-bearing
  premises wrong. **Read §10 first.**

Date: 2026-08-21 (revised same day — see §10)

## 1. Problem

Willy's voice pipeline is unacceptably slow. Live-measured 2026-08-20: a fast-path
command (skips the LLM) takes ~16.4s total, dominated by STT alone at ~11.6s. A
command that needs LLM intent parsing takes ~56.5s total, with the LLM step alone
at ~40.9s. The owner's explicit requirement is that voice response feel "immediate,"
not just incrementally faster — this is out of reach on the current CPU-only path
(`faster-whisper` STT + local `Llama-3.2-3B-Instruct-Q4` via `llama.cpp`, both
competing for the Pi 5's 4 CPU cores).

Separately, `vision.py` is CPU-only YOLOv8 via `ultralytics` — its own module
docstring already anticipated this exact fix: *"Swap in a .hef path + hailo runtime
later; vision.py's detector interface is written to make that a backend swap, not a
rewrite."* An AI HAT+2 (Hailo-10H) has been physically installed and working
(`hailortcli fw-control identify` succeeds) since 2026-08-16 but nothing uses it.

Note: a live under-voltage/regulator issue was found and mostly fixed the same day
these latency numbers were measured. CPU throttling from that may have inflated the
numbers above; they have not been re-measured post-fix. This design proceeds
regardless, since the owner wants the NPU offload built either way, but the exact
before/after latency comparison during testing should account for this.

## 2. Scope

Three components, sharing one piece of common infrastructure:

1. **Hailo-Whisper** — STT, replacing `faster-whisper` on CPU.
2. **Hailo LLM (Phi-2)** — intent parsing, replacing local `Llama-3.2-3B` on CPU.
3. **Hailo YOLOv8** — object detection, replacing CPU `ultralytics` in `vision.py`.
4. **Shared infrastructure**: one `VDevice`/Model Scheduler instance, constructed
   once, that all three subsystems load their models onto.

Explicitly bundled into this scope by owner instruction (2026-08-21): the vision
CSI front-camera integration (see §7) is a hard prerequisite for the vision piece
to be useful at all, independent of Hailo, and is built as part of this effort
rather than deferred.

Explicitly out of scope: anything about the local-LLM prompt/schema *content*
beyond what's needed to validate Phi-2 produces reliable JSON intents (i.e., not a
redesign of the intent taxonomy itself); any change to the wake-word detector
(`openwakeword` stays CPU — it's already cheap and not the bottleneck); Bluetooth
companion and dynamic command learning (separate specs, untouched by this one).

## 3. Why this approach (over alternatives)

Two cheaper alternatives were considered and explicitly rejected by the owner in
favor of going straight for Hailo offload:

- **CPU-only tuning** (smaller Whisper model, trimmed LLM prompt, more fast-path
  coverage) — real but bounded gains, ships faster, lower risk. Rejected: owner
  wants the underlying pipeline actually fast, and CPU tuning alone can't reach
  "immediate."
- **Keep the current Llama-3.2-3B model, route it through `hailo-ollama`** instead
  of switching to a Hailo-native small model — lower effort (no reprompting), but
  the exact model at issue is reported at only ~2.65 tok/s on Hailo, not
  meaningfully faster than likely CPU decode speed. Rejected in favor of switching
  to a genuinely Hailo-fast model (Phi-2 at ~19 tok/s, ~7x faster) since the LLM
  step is the dominant cost.

Real numbers behind the choices below (verified via web research 2026-08-21, not
assumed):

- Hailo-Whisper: real, documented, works on Hailo-10H specifically (a public
  writeup exists of running it on a Pi 5, this unit's exact hardware). Model
  conversion (ONNX export → Hailo Dataflow Compiler → calibration → HEF) must run
  on a separate x86 Ubuntu machine — the compiler does not run on ARM/the Pi
  itself. This is a one-time offline step, not part of rover runtime. Base model
  accepts 5s audio chunks, which comfortably fits the existing ~4s capture window
  with no new chunking logic needed. Realistic expectation from the one real-world
  report found: roughly a 40% total-latency reduction, not a dramatic leap — set
  expectations accordingly during testing.
- Hailo LLM: Phi-2 (2.7B) is an officially-benchmarked Hailo-10H model at ~19
  tok/s, available as a pre-compiled HEF (no custom compilation needed, unlike
  Whisper). Qwen2-1.5B (~9.45 tok/s) is a documented fallback if Phi-2's JSON
  reliability doesn't hold up under testing (see §6 risk).
  > **SUPERSEDED 2026-08-21 — see §10.1.** Phi-2 is not obtainable as a
  > pre-compiled HEF on this rover's actual delivery path. The named *fallback*
  > (Qwen2-1.5B) is. Treat the "~19 tok/s Phi-2" figure above as unverified.
- Hailo YOLOv8: the most mature of the three — pre-compiled HEFs exist for
  standard YOLOv8n/m in Hailo's model zoo, real-world Hailo-10H numbers around
  40-50 FPS. No custom compilation needed for standard variants.
- Multi-model sharing: HailoRT's Model Scheduler supports multiple models sharing
  one device *within a single process* without needing the more complex
  multi-process service configuration (separate `group_id`s, round-robin across
  OS processes) — and voice + vision already run in one process
  (`willy-rover.service`/`RoverBrain`), so this is the simpler in-process sharing
  case. The one hard constraint: the Hailo-10H is exclusive to whichever single
  process holds the `VDevice` — naturally satisfied since it's all one process.
  > **PARTIALLY SUPERSEDED 2026-08-21 — see §10.2.** The exclusivity constraint is
  > real and confirmed (`HAILO_OUT_OF_PHYSICAL_DEVICES(74)` on a second claim). But
  > "naturally satisfied since it's all one process" no longer holds: (a) the
  > shipped vision backend took a *private* `Hailo()` handle rather than the shared
  > `VDevice` §4 specified, and (b) the obvious LLM delivery vehicle
  > (`hailo-ollama`) is a separate server process and cannot share at all.

## 4. Architecture

One shared `VDevice` (Hailo's device/scheduler handle) is constructed once, in
`brain.py::RoverBrain.__init__`, alongside the other hardware singletons (`self._i2c`
pattern). It's passed into three new wrapper classes:

> **NOT AS BUILT — 2026-08-21.** This shared-`VDevice`-injected-from-`brain.py` design was
> never implemented. The vision half shipped first and instead constructs its own private
> `Hailo(config.HAILO_YOLO_MODEL_PATH)` inside `vision.py::ObjectDetector._load_hailo()`,
> holding it for the life of the process. That was correct and self-contained for a
> vision-only change, but it means the rover process now owns the NPU exclusively, and this
> section's premise — that a shared handle already exists to pass to STT/LLM — is false.
> Adding either voice subsystem requires resolving §10.2 first, and that resolution will
> involve reworking `_load_hailo()`, which is live code.

- `hailo_stt.py::HailoWhisper` — loads the converted Whisper `.hef` + embedding
  `.npy` params, exposes a `transcribe(pcm) -> str` method matching the shape
  `voice.py::_process_utterance()` already expects from `faster_whisper`.
- `hailo_llm.py::HailoIntentModel` — loads the Phi-2 HEF, exposes an
  `ask_sync(prompt, schema) -> AIResult`-shaped call matching `ai_provider.py`'s
  existing `LocalAIProvider` interface, so `voice.py::_interpret_local()` doesn't
  need to know which backend it's talking to.
- `vision.py::ObjectDetector` gets a new Hailo backend branch alongside its
  existing CPU/`ultralytics` path — same public interface (`detect()`,
  `localize()`, `available`), swapped internals per its own docstring's plan.

Each of the three is gated behind its own `config.ENABLE_HAILO_STT` /
`ENABLE_HAILO_LLM` / `ENABLE_HAILO_VISION` flag, default `False`, independently
toggleable — so each can be brought up and verified on real hardware one at a time
without the others being at risk. If a flag is on but the shared `VDevice` can't be
claimed at startup (busy, missing runtime, missing model file), that specific
subsystem logs and falls back to its existing CPU path — same fail-safe pattern
`vision.py::_load()` already uses today, extended to STT and LLM.

## 5. Data flow

Voice: wake word (unchanged, CPU) → capture ~4s audio (unchanged) → STT routes to
`HailoWhisper` if `ENABLE_HAILO_STT` else the existing `faster_whisper` CPU path →
fast-path regex check (unchanged, still runs on the resulting text either way) → if
no fast-path match, intent parsing routes to `HailoIntentModel` if
`ENABLE_HAILO_LLM` else the existing CPU `LocalAIProvider` → dispatch (unchanged).

Vision: `ObjectDetector.detect()` routes to the Hailo YOLOv8 backend if
`ENABLE_HAILO_VISION` else the existing CPU `ultralytics` path. Capture itself
switches from the Arducam (cv2/V4L2) to the CSI imx708 (libcamera/picamera2) per
§7, independent of which detection backend runs against the frame.

## 6. Risks and mitigations

- **Phi-2/Qwen2 may not reliably produce valid JSON intents** the way
  Llama-3.2-3B does — smaller models can be less reliable at structured output.
  Mitigation: test a representative batch of real utterances against
  `_interpret_local()`'s existing prompt before enabling live; if reliability is
  poor, try Qwen2-1.5B (documented "strongest small-model reasoning") or simplify
  the prompt/schema. Do not enable `ENABLE_HAILO_LLM` live until this is verified
  — `confidence < LOCAL_LLM_CONFIDENCE_FLOOR` already routes to "I'm not confident
  I understood that" per existing FR-1500-005 behavior, so a less-reliable model
  degrades to more clarification requests, not silently wrong actions — but it
  should still be *tested*, not assumed.
- **Whisper's 40% (not dramatic) real-world improvement** may undersell the
  owner's "immediate" bar on its own. This design doesn't solve that by itself —
  worth revisiting the deferred "Gotcha" immediate-acknowledgment idea (see
  CLAUDE.md 2026-08-21 note) as a complementary, cheap perceived-latency fix once
  this lands, since it's independent of this work and was explicitly deferred
  rather than rejected.
- **Shared VDevice contention** once all three subsystems are live — voice STT/LLM
  calls could compete with a mapping-session's vision calls for scheduler time.
  Mitigation: HailoRT's round-robin scheduler handles this automatically; no
  custom code needed unless testing reveals a specific starvation problem.

## 7. CSI front-camera integration (vision prerequisite)

Separate from Hailo, but required for vision to have any real value: swap
`vision.py`'s capture source from the Arducam OV9281 (USB, confirmed rear-facing
2026-08-20) to the CSI imx708 (`/dev/video0`-`7`, `rp1-cfe` driver, the actual
front-facing camera). The Arducam's existing cv2 `VideoCapture(..., cv2.CAP_V4L2)`
+ forced MJPG approach is specific to that USB camera's quirks (documented in
`vision.py::_load()`) and likely won't work for the CSI camera — `rp1-cfe`-based
CSI capture on this OS typically needs `libcamera`/`picamera2` instead of plain
V4L2. This needs its own small capture-path implementation and live verification
(open the CSI camera, confirm a real non-trivial frame, same verification style
used for the Arducam on 2026-08-20) before wiring it into `ObjectDetector`.
`vision.py::_CAMERA_ID='front'` becomes accurate once this lands, instead of
mislabeling the rear-facing Arducam as documented in CLAUDE.md.

## 8. Testing

None of the three Hailo backends can be tested on the Windows dev machine — no
HailoRT, no device. All real testing happens live on the rover, same as this
session's other hardware work (Witty Pi, vision, arm). What *can* be tested
off-hardware: the config-flag gating and CPU-fallback logic (mirroring the
existing `WILLY_SIMULATE`-style test pattern already used throughout this repo).

Live test sequence, one subsystem at a time, flags off by default:
1. Bring up the shared `VDevice` alone, confirm `hailortcli`-equivalent liveness
   from Python.
2. CSI camera capture path (§7) — verify a real frame independent of any
   detection backend.
3. Hailo YOLOv8 — enable `ENABLE_HAILO_VISION`, confirm detection accuracy/FPS
   against the (now-correct) front camera. Lowest risk, most mature path — good
   first real test of the shared VDevice under real load.
4. Hailo-Whisper — enable `ENABLE_HAILO_STT` alone (LLM still CPU), compare
   before/after latency using the existing `voice timing:` log instrumentation
   already in `voice.py::_synthesize_and_play()`.
5. Hailo LLM — enable `ENABLE_HAILO_LLM` alone (STT back to CPU or combined with
   step 4), run the JSON-reliability test batch from §6 risk before trusting it
   live, then compare latency the same way.
6. All three enabled together — confirm no scheduler contention issues under
   combined voice + vision load (e.g., speaking a command while mapping is
   actively running vision detection).

## 9. Open questions for implementation-phase investigation

Not blocking this design, but not yet nailed down at the API-call level — the
writing-plans skill / implementation should resolve these against Hailo's actual
current SDK/docs rather than this design guessing further:

> **Partially answered 2026-08-21 — see §10.** The third bullet's re-verification was
> carried out and is what invalidated §3/§4 for the voice half. The first two bullets are
> still open, and bullet 2 turns out not to be a free choice between equivalents: see §10.2.

- Exact HailoRT Python API calls for loading/running the converted Whisper HEF
  (the referenced Pi 5 writeup used "runtime code from Hailo's Application Code
  Examples" — needs a closer read at implementation time).
- Whether the Phi-2 HEF is invoked directly via HailoRT or through `hailo-ollama`
  pointed at the official model — whichever proves simpler once actually tried.
- Exact `.hef` filenames/download locations in Hailo's current model zoo for
  Phi-2 and YOLOv8n/m on Hailo-10H specifically (URLs age quickly; re-verify at
  implementation time rather than trusting this doc's research date).

---

## 10. 2026-08-21 re-verification — voice half blocked, decision required

§9 instructed the implementer to re-verify model availability and the HailoRT API story
before trusting this doc. That was done on 2026-08-21, immediately after the vision half
merged. Two load-bearing premises did not survive. This section supersedes §3's LLM bullet
and §4's shared-`VDevice` architecture **for the voice half only** — the vision half is
already shipped and unaffected.

Caveat on method: this re-verification was done from published sources, **not** by a live
check on the rover (the dev machine has no SSH key for `willie.local`; the vision half's
checks were run through Cockpit). Everything below should be confirmed on the device before
a plan hard-codes it, exactly as the vision plan confirmed
`/usr/share/hailo-models/yolov8m_h10.hef` before depending on it.

### 10.1 Phi-2 is not available on this rover's delivery path

§3 chose Phi-2 (2.7B, ~19 tok/s) specifically because it was "available as a pre-compiled HEF
(no custom compilation needed, unlike Whisper)". That is the whole reason the LLM half was
considered cheaper than the STT half. It does not hold up:

- The Hailo GenAI Model Zoo set reachable from the Raspberry Pi / AI HAT+ 2 path is
  `llama3.2:3b`, `deepseek_r1_distill_qwen:1.5b`, `qwen2.5-coder:1.5b`,
  `qwen2.5-instruct:1.5b`, `qwen2:1.5b`. **No Phi-2.**
- One aggregator does list Phi-2 as "Official" at 19 tok/s — but it also lists Qwen2-1.5B at
  9.45 tok/s. Both figures match §3 verbatim, so it is most likely *this spec's own source*
  rather than independent confirmation of it. It additionally lists Llama 2 7B / Llama 3 8B
  as official on a 40 TOPS part, which reads as an unvetted aggregate table.
- Practical ceiling for ready-made Hailo-10H models is reported around 3B.

**Consequence:** the model choice has to be remade from what actually exists. The good news
is that §3's own named fallback survives — `qwen2:1.5b` is in the zoo. §6's risk ("smaller
models may not reliably produce valid JSON intents") therefore moves from a contingency to
the *primary* risk, because there is no 2.7B option to fall back *from*. §6's mitigation
(test a batch of real utterances against `_interpret_local()`'s existing prompt before
enabling live) becomes a hard gate, not a precaution.

Note also that §3 explicitly *rejected* routing the existing Llama-3.2-3B through
`hailo-ollama` at ~2.65 tok/s. `llama3.2:3b` being in the zoo does not revive that option —
the rejection was on throughput, which is unchanged.

### 10.2 The NPU is single-process-exclusive, and vision already claimed it

This is the more serious finding, and it is a direct consequence of what just shipped.

- The Hailo-10H `VDevice` is **exclusive to one process**. A second claim fails hard with
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74): Failed to create vdevice`.
- `hailo-ollama` — the obvious vehicle for the LLM half, and the one §9 bullet 2 assumed was
  a free alternative to direct HailoRT — is a **separate server process**, and is reported to
  be "bundled up in a binary that won't play nice" with device-sharing strategies. There is a
  documented hard crash from exactly this shape: `hailo-ollama` initialising a `VDevice` while
  `hailo-whisper` holds the device.
- **`vision.py::ObjectDetector._load_hailo()` now constructs `Hailo(...)` inside
  `willy-rover.service` and holds it until `close()`.** As of `ENABLE_HAILO_VISION=True`, the
  rover process owns the NPU for its entire lifetime.

So §4's reasoning that in-process sharing is "naturally satisfied since it's all one process"
is now false in both directions: vision did not share its handle, and a `hailo-ollama`-based
LLM would not be in that process anyway.

**Immediate operational consequence (true today, independent of the voice work):** while
`willy-rover.service` is running with vision enabled, nothing else on the rover can open the
NPU — `hailortcli`, standalone Hailo scripts, and any verification one-liner will fail until
the service is stopped. The existing plans already stop the service before such checks; that
precaution is now load-bearing for the NPU, not just for I2C/camera contention.

### 10.3 The decision that has to be made before any voice plan

Three shapes are possible. They are not equivalent, and two of them require touching live
vision code.

**Option A — one in-process `VDevice`, direct HailoRT for all three.** What §4 originally
intended. `brain.py::RoverBrain.__init__` constructs the device handle; `ObjectDetector`,
STT, and LLM all receive it by injection.
- *Cost:* rework `_load_hailo()` to accept an injected handle instead of constructing its own
  (live code, currently deployed, would need re-verification on hardware). Requires invoking
  the LLM HEF **directly via HailoRT**, not via `hailo-ollama` — and §9 bullet 1's "exact
  HailoRT Python API calls" question is still open, so this path's real cost is unknown.
- *Benefit:* the only shape where vision and voice genuinely run concurrently.

**Option B — a device-manager daemon; every subsystem is a client.** A separate process holds
the exclusive `VDevice` and serialises inference requests over a Unix socket; the rover
process becomes a lightweight client. This is what the community converged on.
- *Cost:* a whole new IPC surface and failure mode, plus added latency, on a path that
  `brain.py`'s tick thread already touches (`detect()` is synchronous on that thread, against
  `WatchdogSec=500ms`). Also still requires reworking `_load_hailo()` into a client.
- *Note:* this does **not** rescue `hailo-ollama`, which reportedly won't cooperate with a
  device manager either. It enables multiple *custom* HailoRT services, not that binary.

**Option C — time-share: only one subsystem holds the NPU at a time.** Vision releases the
device when voice needs it and vice versa.
- *Cost:* almost certainly unacceptable for a rover. Vision would go blind mid-task every
  time someone spoke, and `close()`/reload cycles on the HEF are not free.
- Recorded for completeness so it is visibly rejected rather than silently skipped.

**Recommendation:** Option A, on the grounds that it is what this spec always intended, it is
the only one that keeps vision live during voice, and it avoids inventing an IPC layer on a
robot whose control loop is already watchdog-constrained. But it should not be committed to
until §9 bullet 1 is actually answered — i.e. until someone confirms, on the rover, that a
GenAI HEF can be loaded and run through the HailoRT Python API against an
externally-supplied `VDevice`. That single experiment is the real next step, and it is
cheap: it needs no integration work, just a script run with the service stopped.

### 10.4 STT remains separately blocked

Unchanged from §3 and from the vision plan's scoping note: Hailo-Whisper needs its HEF
compiled through the Hailo Dataflow Compiler on an **x86 Ubuntu machine** (the compiler does
not run on ARM), and no such HEF exists on this rover. That groundwork is a prerequisite for
any STT plan regardless of how §10.3 is decided.

### 10.5 Suggested sequencing

1. Answer §9 bullet 1 with the cheap on-rover experiment described in §10.3 (service stopped;
   load a GenAI HEF via HailoRT Python against an explicit `VDevice`).
2. Decide §10.3 with that result in hand.
3. Pick the LLM model from §10.1's actually-available list; run §6's JSON-reliability batch
   against `voice.py::_interpret_local()`'s existing prompt **before** any integration work.
4. Only then write the LLM plan. It will need a task for the `_load_hailo()` rework.
5. STT stays parked until §10.4's x86 compilation groundwork exists.
