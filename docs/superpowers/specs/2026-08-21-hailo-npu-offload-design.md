# Hailo-10H NPU Offload — Voice + Vision Design

Status: approved by owner in brainstorming, ready for writing-plans.
Date: 2026-08-21

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

## 4. Architecture

One shared `VDevice` (Hailo's device/scheduler handle) is constructed once, in
`brain.py::RoverBrain.__init__`, alongside the other hardware singletons (`self._i2c`
pattern). It's passed into three new wrapper classes:

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

- Exact HailoRT Python API calls for loading/running the converted Whisper HEF
  (the referenced Pi 5 writeup used "runtime code from Hailo's Application Code
  Examples" — needs a closer read at implementation time).
- Whether the Phi-2 HEF is invoked directly via HailoRT or through `hailo-ollama`
  pointed at the official model — whichever proves simpler once actually tried.
- Exact `.hef` filenames/download locations in Hailo's current model zoo for
  Phi-2 and YOLOv8n/m on Hailo-10H specifically (URLs age quickly; re-verify at
  implementation time rather than trusting this doc's research date).
