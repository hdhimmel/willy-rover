# Dynamic Command Learning — Design

**Status:** Approved by owner (Howard Himmel), 2026-08-20. Ready for implementation planning.
**Owner:** Howard Himmel
**Companion docs:** `docs/WildWilly_Functional_Requirements_v3.1.md`,
`docs/WildWilly_Software_Design_v1.0.md`, `CLAUDE.md`.

## 1. Purpose

Today, teaching Willy a new voice command means a developer edits `voice.py`'s intent-recognition
prompt and `brain.py`'s dispatch code by hand, then redeploys. The owner wants two things instead:

1. **Recombinations of existing capabilities** learnable live, with no code change or redeploy.
2. **Genuinely new capabilities** (requiring new code) to be *requested* by Willy automatically,
   approved by the owner via email reply, and then implemented by an unattended coding agent that
   stops at a pull request for human review — never deployed to the rover without that review.

This spec covers both, as two independent components sharing one hard safety line: **neither
component may ever add a new hardware-level capability, bypass `SafetyController`, or reach the
physical rover without a human explicitly reviewing and deploying the change.** Component 1 can
never violate this by construction (it only ever calls already-gated existing code). Component 2
enforces it by restricting which files an unattended agent may touch and by never auto-merging or
auto-deploying.

## 2. Component 1 — Macro system (live, no redeploy)

### 2.1 What it is

A **macro** is a named sequence of existing, already-implemented voice intents (the same intents
`voice.py`/`brain.py` already dispatch today — `retrieve`, `come_here`, `wave`, `forward`, etc.),
each with its own args, stored as data. Defining a new macro requires no code change and no
service restart: it's an insert into a small on-disk store the running process already has open.

### 2.2 Storage

A new `macro_store.py`, following the same SQLite/WAL pattern `memory_store.py` and
`world_model.py` already use (per `storage.py`'s shared root resolution) — not a new flat file,
so it's crash-safe and consistent with the rest of the persistence layer. Schema: `name` (the
trigger phrase or a normalized key), `steps` (JSON array of `{intent, args}`), `created_at`.

### 2.3 Defining a macro

The owner (or eventually anyone) says something like *"Willy, when I say 'clean sweep,' go to
the kitchen then come find me."* `voice.py`'s existing local-LLM interpretation gains one more
recognized
intent, `define_macro`, whose args are `{"name": "...", "steps": [{"intent": "...", "args": {...}}, ...]}` —
the LLM decomposes the spoken definition into steps using the *exact same* intent vocabulary it
already uses for direct commands (§2.4 explains how new intents can still be added, so this
vocabulary can grow, but macros are never required to invent an intent that doesn't exist).
Willy confirms back ("I'll remember that as 'clean sweep': go to the kitchen, then come find
you. Say 'confirm' to save it.") before persisting — no macro is saved from a single ambiguous
utterance.

### 2.3.1 Reconciling with the existing FR-1900-006 teaching feature (found 2026-08-20)

`voice.py::_maybe_learn()` already has a similar-sounding, already-shipped mechanism: saying
*"when I say X, do Y"* today calls `memory_store.py::add_instruction(X, Y)`, storing `Y` as raw
text with no structure, no validation, and no confirmation step. Later, when the trigger phrase
recurs, that raw text is fed back into the local LLM as extra context (`get_context_for()`),
which must freshly reinterpret what `Y` means *at that moment* — nothing guarantees it resolves
to a real or safe intent. This predates this spec and is a materially less safe mechanism than
§2's macro system (structured steps, confirmed once, replayed deterministically forever after by
calling the same dispatch path — never re-interpreted).

Both mechanisms currently listen for the identical phrasing (`"when I say ..., do ..."`), and
`_maybe_learn()` runs *before* the local-LLM intent interpretation in `voice.py`'s handling order
— so as written today, it would short-circuit and swallow every attempt to define a macro before
the new `define_macro` intent (§2.3) ever saw it. **The implementation must replace
`_maybe_learn()`'s instruction-teaching branch with a call into the new macro system**, keeping
the same trigger phrasing so nothing changes from the owner's side, but switching the underlying
behavior from "store raw text, reinterpret later" to "decompose into a structured, validated,
confirmed step list once, then replay deterministically." `_maybe_learn()`'s *other* branch
(`"remember that X"` → `add_fact()`, general fact memory) is unrelated and stays untouched.
Any instructions already stored via the old mechanism should be left alone (not silently
migrated/executed as macros without the owner re-confirming them under the new, safer flow).

### 2.4 Running a macro

A new `MacroRunner` (small, in `brain.py` or its own `macro_runner.py`) is invoked when a spoken
command matches a stored macro's trigger name instead of a built-in intent. It steps through the
stored sequence one step per tick (same non-blocking, deadline-serviced pattern as
`retrieval_task.py`'s `_grasp()` and `brain.py`'s `_wave()` — no new blocking call is introduced),
feeding each step through **the exact same dispatch path a directly-spoken command would use**
(`_drain_voice_commands`'s existing intent handling). This is the safety property that makes
macros safe by construction: a macro cannot do anything a direct voice command couldn't already
do, because it never bypasses that dispatch — it just calls it multiple times in sequence. Any
Directive 1–5 fault (tilt, battery, sensor, stall) that would abort a normal task aborts a
running macro exactly the same way, since `_check_stall()`/`_check_health()`/tilt/battery checks
all run every tick regardless of what's driving `_tick()`'s dispatch that cycle.

### 2.5 What this component cannot do

It cannot create a new *intent* — every step must name an intent that already exists in
`voice.py`'s recognized set. That boundary is what keeps this component entirely within "already
reviewed, already safety-gated code," with zero new attack surface. Teaching Willy to do
something with no existing primitive for it is Component 2's job.

## 3. Component 2 — Capability-gap request → owner approval → unattended PR

### 3.1 Trigger: gap detection

`ai_provider.py`'s `AIResult` already carries `intent_confidence` (§14/§15, existing). When a
spoken command's local-LLM interpretation comes back with confidence below
`config.LOCAL_LLM_CONFIDENCE_FLOOR` (existing constant, currently gates cloud-AI fallback) *and*
neither a built-in intent nor a stored macro name fits, that is a capability gap. This reuses an
existing signal — no new AI call, no new model.

### 3.2 Request record

A new `docs/capability_requests/NNNN.md` file per request (sequential, zero-padded — e.g.
`0001.md`), plain Markdown, git-tracked:

```markdown
# Capability request 0001

- Status: pending
- Requested: 2026-08-20 14:03 EDT
- Transcript: "can you check if the back door is locked"
- Local LLM's guess: needs a new `check_door_lock` intent — no existing sensor/action for this.
- PR: (none yet)
```

Plain files (not a database) so they're human-readable in a PR diff, greppable, and durable
without a new dependency. `status` is one of `pending` / `approved` / `rejected` / `needs-human`
/ `pr-opened` / `implemented`.

### 3.3 Dedup

Before creating a new file, Willy checks existing `pending`/`approved` requests for a
transcript/guess that's a near-duplicate (same normalized intent guess) and, if found, does not
create a second request or send a second email — it just logs that the existing request N still
covers this.

### 3.4 Notification

Reuses `email_client.py` (already working, `ENABLE_EMAIL=True`) to email the owner: the
transcript, the guess, and "Reply 'approve 1' or 'reject 1' to this email." Sent once per new
request (not per repeated utterance, per §3.3).

### 3.5 Approval capture

`email_client.py`'s existing inbound-mail handling (FR-2000-010/011 — already parses replies
from an owner-managed sender allowlist) gains a new pattern: a reply matching `approve N` /
`reject N` updates that request file's `status` field and commits + pushes immediately (not
waiting for the next `scripts/auto_backup.sh` cron cycle — same git remote/credentials, just
triggered on-demand for responsiveness).

### 3.6 The unattended agent

A scheduled cloud agent (Claude Code's own cron/scheduled-agent mechanism), running periodically
— hourly is a reasonable starting cadence, easy to change later. Each run:

1. Fetches `origin/main`, scans `docs/capability_requests/*.md` for `status: approved` with no
   `PR:` link yet.
2. For each one, in a fresh worktree, attempts an implementation restricted to the file-level
   fence in §3.7. It reads `CLAUDE.md` and both current design docs first, and follows this
   repo's established conventions exactly: the subprocess/`WILLY_SIMULATE=1` test pattern (see
   any `tests/test_brain_*.py`), a standalone verification harness before writing the committed
   test (this repo's dev machines can't import `brain.py`/`display.py` directly — missing
   `pygame` etc. — so tests always go through that pattern), and doc updates to FRD v3.1 /
   Software Design v1.0 mirroring whatever code changed, matching every prior session's pattern.
3. If it can implement the request within the §3.7 fence: commits to a new branch
   (`capability-request-NNNN`), pushes, opens a PR via `gh pr create` describing what it built
   and how it was tested, then updates the request file (`status: pr-opened`, `PR: <url>`) and
   pushes that too.
4. If it determines the request needs something outside the fence (a new hardware capability, a
   change to `safety.py`'s gating logic, anything the fence forbids): it does **not** attempt a
   workaround. It sets `status: needs-human`, writes a one-paragraph explanation of why, commits,
   pushes, and stops. No PR is opened for a fenced-out request.

### 3.7 The file-level fence (hard boundary, not just an instruction)

The agent's own operating instructions state explicitly that it may only modify:
- `voice.py` — adding new recognized intents to the interpretation prompt and `_INTENT_SCHEMA`-
  compatible parsing, never touching STT/TTS/wake-word code.
- `brain.py` — adding new dispatch branches in `_drain_voice_commands` (or a new FSM state
  following the exact pattern `'WAVE'`/`_wave()` already established) that call **only
  pre-existing methods** already reachable from a built-in intent today (`self.retrieval.start()`,
  `self.arm.center_all()`, `self.safety.forward_for()`, `self.pursuit.start()`, etc.).
- `tests/` — new test files for whatever it added.
- `docs/` — updates mirroring the code change, plus updating its own request file.

It may **never** modify `motors.py`, `sensors.py`, `safety.py`, `arm.py`, `config.py`'s hardware
constants, `main.py`, or any systemd/service file. This is enforced as an explicit instruction to
the agent (not a technical sandbox in v1) — the real backstop is §3.8: nothing it produces reaches
the rover without a human reviewing the PR first, so an instruction violation is caught at review,
not after deployment.

### 3.8 Human review and deployment (unchanged from today)

The owner reviews the PR (optionally via the existing `/code-review` skill), merges it — or
doesn't — and deploys it exactly the way every change has been deployed all session: `git pull`
on the rover, then `sudo systemctl restart willy-rover.service`. **No automation in this design
ever merges a PR or touches the running service.**

## 4. What this design deliberately does not include (YAGNI)

- No GitHub Issues integration — plain files in the repo already give a reviewable, git-tracked
  queue without a new API token/credential to manage.
- No webhook-triggered (event-driven) agent run — a periodic scheduled poll is simpler and the
  latency (up to the poll interval) is fine for a feature-request workflow, not a real-time one.
- No sandboxed/technically-enforced file fence in v1 — human PR review is the enforcement
  mechanism; a technical sandbox (e.g. CI check that fails the PR if forbidden files changed)
  is a reasonable future hardening step but not required to ship this safely, since nothing
  merges without review regardless.
- Macros cannot invent new intents (§2.5) — that gap always routes through Component 2.

## 5. Open items for the implementation plan

- Exact cron cadence for the scheduled agent (proposing hourly; trivially adjustable).
- Whether `define_macro` needs its own confirmation UX beyond a spoken "confirm" (e.g., should
  the touchscreen show the macro steps before saving, mirroring the existing "TAP TO RESUME"
  pattern for visibility) — a reasonable v2 enhancement, not required for v1.
- `macro_store.py`'s exact schema/API shape (sketched in §2.2, not fully specified) — normal
  implementation-plan-level detail, not a design-level open question.
