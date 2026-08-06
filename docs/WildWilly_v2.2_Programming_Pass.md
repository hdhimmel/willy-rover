# WildWilly — v2.2 subsystems programming pass (2026-08-06)

Companion to `WildWilly_Functional_Requirements_Document_v2.2.md` and
`WildWilly_Master_Engineering_Package_rev6.0.7.md`. Tracks what this pass implemented against
the FRD's new requirements (M-013–M-020 / FR-1300–FR-2000), and what's still open. See also
`WildWilly_Baseline_Programming_Pass_2026-08.md` (the prior, narrower hardware/safety pass this
one builds on top of).

## Scope and instruction for this pass

User asked for all of v2.2 implemented, code only, no live testing/verification against
hardware this session (explicit instruction — differs from the baseline pass, which did
constructor/read-only test each new class against the real board). Nothing below has been run
on the live unit. Treat every module here the way `arm.py`/`steering` were treated after the
baseline pass: present, plausible, but unverified until someone actually runs it.

## Two blockers no amount of code solves

- **No Hailo NPU is installed** on this unit (`/dev/hailo*` absent, no `hailortcli`, checked
  2026-08-06). FR-1700 assumes Hailo-accelerated YOLOv8; `vision.py` runs YOLOv8 on CPU via
  `ultralytics` against the confirmed-present Arducam OV9281 (USB, `/dev/video0`) instead. The
  detector interface is written so a Hailo backend can drop in later without touching callers.
- **Willie's own Google account doesn't exist yet.** FR-1300/1400/2000 all authenticate as
  `willie.pi5.droid@gmail.com` (config.py), not the owner's personal account — that account has
  not been created, so none of smart home, Gemini fallback, or email can actually connect no
  matter how correct the code is. `ENABLE_SMART_HOME` / `ENABLE_CLOUD_AI` / `ENABLE_EMAIL` all
  default `False` in config.py until real credentials exist at the paths documented there.

## What shipped

- **`config.py` / `requirements.txt` / `.gitignore`**: a new v2.2 block — one `ENABLE_*` flag
  per subsystem (all default off except display expressions and the local memory store, which
  have no external dependency), credential paths under `secrets/` (new gitignore entry,
  alongside `*.db` for the memory store), model asset paths under the already-gitignored
  `models/`. New deps added unpinned (not installed/import-tested this pass).
- **`privacy.py`** (FR-1800, new): `mic_camera_disabled()` flag-file check (independent of
  E-stop, FR-1800-005) that `voice.py`/`vision.py` poll continuously, not just at startup;
  `purge_expired()` generic retention sweep (FR-1800-004); `note_cloud_send()` for the
  "data is leaving the device" indication FR-1800-003 requires whenever Gemini fires.
- **`memory_store.py`** (FR-1900, new): SQLite store for demonstrations/environment
  facts/instructions/routines. `get_context_for()` is keyword-match retrieval, not
  embeddings — there's no local embedding model to run a semantic search with, so this is
  explicitly the "gets better context, not smarter model" framing the FRD's feasibility note
  asked for. `save_all_now()` WAL-checkpoints; wired into `brain.py` at the RTH battery
  threshold (the *guaranteed* save FR-200-005 specifies) and again as a best-effort backstop at
  the actual SHUTDOWN tier, plus on every `RoverBrain.stop()`.
- **`smart_home.py`** (FR-1300, new): the FRD's own text flags its command direction as an
  unconfirmed assumption — separately, "control another account's Google Home devices" isn't a
  public API surface Google exposes to third parties. This client talks to a **Home Assistant**
  REST API instead, the realistic local bridge for that use case; swap if that's not actually
  what's running on the network. Fails soft to an empty device list / failure tuple on any
  network/credential problem, never raises into the caller.
- **`cloud_ai.py`** (FR-1400, new): Gemini REST call via `urllib` (no SDK dependency, matches
  `claude_client.py`'s existing style), short timeout, fallback-only — `voice.py` is the only
  caller, and only when local interpretation confidence is low.
- **`voice.py`** (FR-1500, new): openwakeword → faster-whisper → llama.cpp (local gguf) →
  piper pipeline, all in background threads. Motion-triggering intents go on a queue brain.py
  alone drains, and only at Directive 6. Personality tone (funny/silly/bashful) is forced back
  to neutral for anything text-pattern-matched as safety-related, on top of callers being
  expected to pass `tone='neutral'` correctly — defense in depth, mirroring FR-2000's layered
  allowlists. **Bug caught and fixed during this pass**: `speak()` originally called the
  synthesis subprocess (piper + aplay, up to ~25s) directly — fine when invoked from voice.py's
  own thread, but brain.py's `_tick()` now calls `voice.speak()` too (email/retrieval
  announcements), which would have stalled the safety tick loop for the duration of a spoken
  sentence. Fixed by routing all `speak()`/`speak_safety()` calls through a queue drained by a
  dedicated speaker thread — every call site is non-blocking now, regardless of caller.
- **`display.py`** (FR-1600, extended, not new): added `listening`/`processing`/`fault`/
  `lowbatt`/`bashful`/`silly` to the existing `WillyFace` state vocabulary. Split the visual
  state into a true `state` (drives the HUD badge — always the ground-truth FSM/fault state)
  and a `vis` state (drives the face/eyes/mouth — personality-substitutable). Personality only
  ever substitutes `vis`, and only when `state` is in a small safe set (idle/roam/slow/
  listening/processing/speak) — fault/lowbatt/warn/stuck are never in that set, so
  FR-1600-008's "personality must never override mandatory states" is structural, not a
  convention someone has to remember to honor at each call site.
- **`vision.py` + `retrieval_task.py`** (FR-1700, new — the FRD calls this the core mission):
  detect → localize → approach → grasp → verify → deliver → await-confirm state machine, run
  as its own top-level `RETRIEVE` state in `brain.py`'s FSM (same pattern as DOCK/AVOID). Two
  honest approximations, not full implementations: **localization** is a pinhole heuristic off
  an assumed object width and an assumed camera FOV (no depth sensor, no camera calibration run
  on this unit); **grasp planning** is a fixed primitive pulse sequence, not inverse kinematics
  (§20.6 arm calibration still hasn't been bench-run, same gap the baseline pass flagged in
  `arm.py`). Hand-off confirmation is time-based with an optional voice "got it" override —
  there's no tactile/force sensor on the gripper to actually sense receipt; this is logged
  loudly at the point it fires, not silently assumed to be fine.
- **`email_client.py`** (FR-2000, new): IMAP/SMTP via a Gmail app password (env var), not
  OAuth — simpler to stand up without a browser consent flow, and moot until the account
  exists anyway. Three independent layers per the FRD's own security note: outbound send
  requires an explicit `confirm_and_send()` call on a previously `queue_outbound()`'d id
  (FR-2000-004); the recipient allowlist is checked at both queue time and send time, hard-coded
  in `config.py`, single entry (FR-2000-009); inbound sender allowlist gates whether a body is
  ever parsed at all (FR-2000-010), and `add_allowed_sender()` requires an explicit
  `owner_confirmed=True` from the caller (FR-2000-011) — **caveat**: there's no voiceprint/
  biometric auth anywhere in this codebase, so in practice "owner-confirmed" means "a command
  spoken at the physical device", not a cryptographically verified identity. `build_summary_prompt()`
  is the one canonical template for handing email content to an LLM, wrapped in an explicit
  untrusted-data delimiter (FR-2000-006) — any future caller should use it rather than rolling
  its own prompt.
- **`brain.py`**: instantiates and wires all of the above. `_tick()`'s existing Directive
  1-3-ish checks (tilt fault, battery ladder) now also abort an in-progress `RetrievalTask`
  before transitioning away (FR-1700-007). A new `RETRIEVE` top-level state delegates to
  `RetrievalTask.tick()`. Voice-queued commands are only drained from `IDLE`, and only a
  `retrieve` intent is actually wired to an executor this pass — other voice motion intents
  (forward/reverse/turn/go_to) are logged, not silently dropped, but have no executor behind
  them, since free-form voice-driven manual/autonomous driving wasn't part of what got built.

## FRD coverage after this pass

Code exists for every FR-1300–FR-2000 requirement group. None of it has run against real
hardware/credentials yet. Practically nothing will actually turn on until: the model files in
`models/` are downloaded, Willie's Google account is created with Gmail/Gemini API access
enabled, a Home Assistant instance (or a real backend swap) is confirmed as the smart-home
bridge, and `secrets/google_home_token.json` / `WILLIE_GMAIL_APP_PASSWORD` /
`GEMINI_API_KEY` are populated. Flip each `ENABLE_*` flag in `config.py` only after its
prerequisite is actually in place, one at a time, and bench-test before trusting anything near
the arm or near a person (the hand-off path especially).

## Open items, roughly in the order they'd need attention

1. Provision `willie.pi5.droid@gmail.com` and generate real credentials for Home
   Assistant/Gemini/Gmail.
2. Confirm the FR-1300 direction assumption with the owner (Willie sending commands out, per
   the FRD's own flagged note) and confirm Home Assistant (or pick a different backend) is
   actually the right smart-home bridge.
3. Download/place the voice model assets (`hey_willy.onnx`, a faster-whisper model, a Llama
   3.2 3B gguf, a Piper voice) and bench-test the wake word threshold in the actual room.
4. Run the §20.6 arm bench calibration that's been pending since the baseline pass — everything
   in `retrieval_task.py`'s grasp sequence is a rough guess until that exists.
5. Camera calibration (real focal length, real FOV) for `vision.py`'s localization to be
   anything more than a coarse heuristic.
6. Decide on a real hand-off confirmation method (weight-sensing gripper, timeout tuning, or
   accept voice-confirmation-or-timeout as the permanent design) before this runs near a person
   for real.
