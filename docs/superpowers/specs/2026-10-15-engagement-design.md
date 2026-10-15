# Engagement: greeting people, asking about what he sees and remembers — design

**Date:** 2026-10-15 · **Owner request:** "make Willie more engaging with people and the environment.
Greet people he sees and ask questions about what he sees and remembers."
**Requirement group:** FR-2400 (new). Supersedes the greeting half of FR-2100-002/003.

## 1. Intent and decisions (owner, 2026-10-15)

| Question | Decision |
|---|---|
| When | **Idle and roaming.** While roaming he stops, turns toward the person or thing, speaks, resumes. Never during a task (fetch, find Storm, tidy toys, come here), avoid, stuck, a fault or low battery. |
| How often | **Moderate.** Each person greeted once per visit (30 min unseen ends a visit). At most one remark or question every 5 min. Never the same topic about the same subject twice in a day. |
| Topics | **All four:** name new things, memory callbacks, ask about people, changes he notices. |
| Strangers | **Friendly hello:** "Hi, I'm Willie! What's your name?" The name is kept for this visit only; no face is stored without the owner's approval (FR-2100-006 unchanged). "Stranger danger" is removed. |
| Wording | **Cloud model writes the line; templates when offline or slow.** The cloud is given a short text fact sheet, never an image (FR-1800 unchanged). |

**Known limit, accepted:** "things" are the classes his detector knows (COCO-80: ball, cup, backpack,
dog, chair…). A truly novel object is invisible to him. Naming applies to instances of known classes
("Storm's ball"). Adapting this later (e.g. an owner-approved image description) is out of scope.

## 2. Components

### 2.1 `engage.py` (new) — the decision-maker
`Engagement(memory, identity, world_model, clock=time.time)`; one public call per tick:

```
tick(state, dets, faces, pose, busy) -> Topic | None
```

- `state`: the brain FSM state. Only `IDLE`, `ROAM`, `SLOW` may engage.
- `dets`: the front detector's latest detections (class, bbox, frame size).
- `faces`: the recogniser's latest result, already matched: `[(band, name|None, bbox)]`.
- `busy`: True while voice is speaking/listening/processing, privacy is on, a prompt is open, or the
  battery tier is not normal. Busy = no topic.
- Returns at most one `Topic(kind, subject, facts, question, target_bearing_deg)`; the brain acts
  on it (§2.4). Choosing a topic records it in the "said today" set (kind, subject) and starts the
  5-minute gap — even if it is never spoken, so a failure cannot make him repeat.

Rules, in priority order (first that fires wins):

| # | kind | fires when | subject | question? |
|---|---|---|---|---|
| 1 | `greet_known` | a RECOGNISED face, not greeted this visit | name | no |
| 2 | `greet_stranger` | UNKNOWN face on `ENGAGE_STRANGER_CONFIRM_N` (3) consecutive scans, not asked this visit | `stranger` | yes ("What's your name?") |
| 3 | `ask_room` | in no named room, idle or roaming, at most once per hour | 1 m pose cell | yes ("What room is this?") |
| 4 | `ask_thing` | a thing of `ENGAGE_THING_CLASSES` with no stored name for its kind in this room | kind+room | yes ("Whose ball is that?") |
| 5 | `callback` | a person/dog/thing with a stored history (last seen > 2 h ago, or a stored note) | name/kind | no |
| 6 | `change` | in a named room: a thing seen here that was never seen here before, or a thing whose usual room is this one and that has not been seen here for > `ENGAGE_MISSING_H` (4 h) while he has looked | kind+room | no |
| 7 | `ask_person` | a known person, greeted ≥ 2 min ago this visit, still in view | name | yes ("How was your day?") |

Greetings (1, 2) ignore the 5-minute gap (they are once per visit anyway) but still respect `busy`.

### 2.2 `engage_words.py` (new) — the words
- `line(topic) -> str`: asks the cloud model (`CloudAIProvider.ask_sync`, `CLAUDE_CHAT_SYSTEM` persona)
  for ONE short spoken line given `topic.kind` and `topic.facts` (plain text: names, kinds, rooms,
  times as "this morning"/"yesterday"). Hard limit `ENGAGE_WORDS_TIMEOUT_S` (3 s), run capped like
  `_ask_local_capped`. On timeout, error, offline or an empty/long (> 200 chars) reply: a template from
  `ENGAGE_TEMPLATES[kind]` (several per kind, rotated) filled with the facts.
- `extract(topic, answer_text) -> dict | None`: for questions. Cloud call with a JSON schema per kind:
  - `greet_stranger` → `{"name": str}`
  - `ask_room` → `{"room": str}`
  - `ask_thing` → `{"owner": str|null, "label": str}` (e.g. owner "Storm", label "Storm's ball")
  - `ask_person` → `{"note": str}`
  Offline fallback: simple patterns (`_NAME_REPLY`, "it's X's", "this is the X", free text as the
  note). Unusable → None.

### 2.3 Memory (`memory_store.py`, same SQLite file, WAL)
- **`things`**: `kind, label, owner, room, first_seen, last_seen`. One row per (kind, room, owner);
  updated by sightings; `label` from answers.
- **`person_notes`**: `name, note, at`. Purged after `EXPERIENCE_KEEP_DAYS` (30) like experiences.
- **Sightings:** `_note_sightings` widens from `EXPERIENCE_SIGHT_CLASSES` to also cover
  `ENGAGE_THING_CLASSES` — movable COCO classes: sports ball, frisbee, teddy bear (the
  `TOY_CLASSES`), cup, bottle, wine glass, bowl, backpack, handbag, suitcase, umbrella, cell phone,
  remote, laptop, book, scissors, kite, skateboard. Furniture, people, animals and fixtures are
  excluded. Each sighting updates `things.last_seen` and the room (if named).
- **Rooms:** `ask_room` answers call the existing `world_model` room naming (same as "this is the
  kitchen"). Rooms are dead-reckoned and blur over a long run; change remarks may occasionally be
  wrong. Accepted.
- **Reuse:** "whose/what is that X", "when did you last see Storm's ball" and the cloud chat context
  (`get_context_for`) include `things` labels and the 3 most recent `person_notes` for the person.

### 2.4 Brain wiring (`brain.py`)
- `self.engage=Engagement(...)` in `__init__`; `ENABLE_ENGAGEMENT` switch.
- Each tick (after the face scan, before state dispatch), when the state is IDLE/ROAM/SLOW:
  `topic=self.engage.tick(...)`. If a topic is returned, `_start_engage(topic)`:
  1. ROAM/SLOW: `safety.stop()`, state → `ENGAGE` (new, behaves like IDLE for safety).
  2. If `|target_bearing_deg| > ENGAGE_TURN_MIN_DEG` (15): turn toward it through `rotate.py` (the
     normal Rotation, all its guards). A refused turn → speak without turning.
  3. Words on a background thread (`engage_words.line`), then `voice.speak`. If a question:
     `voice.prompt_listen(cb, FACE_ASK_TIMEOUT_S)`; `cb` runs `extract` (background) and stores.
  4. Back to the previous state (ROAM resumes; IDLE stays). `ENGAGE` times out after
     `ENGAGE_MAX_S` (20 s) whatever happens.
- "Stop" (voice or screen) ends `ENGAGE` and drops a pending answer.
- The old `_face_tick` greeting/stranger code is removed; `_face_tick` keeps only scanning, matching,
  `note_seen` and `set_current_person`, and feeds `faces` to `engage.tick`. Face scanning runs in
  ROAM/SLOW too (it was IDLE only) at `FACE_SCAN_S`.
- A stranger's spoken name → `voice.set_current_person(name)` for `FACE_SPEAKER_WINDOW_S`; no vector
  stored. If the name matches an enrolled person the existing "Sorry, I didn't recognise you" path
  stays (it may add a vector only from the UNCERTAIN band, as now).

## 3. Safety and failure handling
- Engagement never drives by itself: the stop goes through `SafetyController`, the turn through
  `Rotation`; obstacle, tilt, battery and stop limits all apply. `ENGAGE` is not a motion state.
- Never during a task, AVOID, STUCK, faults, low battery, privacy, or while voice is busy.
- Cloud slow/offline → template in ≤ 3 s. No answer → nothing more said; topic stays "said today".
- Unusable answer → nothing stored; logged `Engage answer not used: <kind> heard <text>`.
- Camera/face model down → no topics (start-up check already reports it).
- Every topic logged: `ENGAGE kind=… subject=… said=… answered=… stored=…`.

## 4. Config (`config.py`)
`ENABLE_ENGAGEMENT=True`, `ENGAGE_GAP_S=300`, `ENGAGE_VISIT_S=1800` (replaces `FACE_GREET_SESSION_S`),
`ENGAGE_STRANGER_CONFIRM_N=3`, `ENGAGE_THING_CLASSES=(…)`, `ENGAGE_MISSING_H=4`,
`ENGAGE_CALLBACK_MIN_H=2`, `ENGAGE_ASK_ROOM_GAP_S=3600`, `ENGAGE_ASK_PERSON_AFTER_S=120`,
`ENGAGE_TURN_MIN_DEG=15`, `ENGAGE_MAX_S=20`, `ENGAGE_WORDS_TIMEOUT_S=3.0`, `ENGAGE_TEMPLATES={…}`.

## 5. Testing
- `tests/test_engage.py` (fake clock, fake detections/faces, in-memory store): each rule fires on its
  trigger and not otherwise; priority order; 5-minute gap; once per visit; no repeat in a day; no
  topic in disallowed states or when busy; stranger needs 3 scans; change rule only in named rooms.
- `tests/test_engage_words.py`: cloud reply used; timeout/offline/over-long → template; `extract`
  for each kind from recorded sample replies; offline pattern fallback.
- `tests/test_memory_things.py`: things/person_notes rows, sighting updates, purge.
- Brain wiring: out-of-process test like `test_stuck_ai_fallback_chain.py` — ROAM stops, turns,
  speaks, resumes; a refused turn still speaks; "stop" cancels; old stranger-danger path gone.
- Live: idle first (greet the owner, ask about one ball), then roaming, watching the log.

## 6. Docs
FRD: new FR-2400 group (requirements 001-007 = the rules above + the safety gates); FR-2100-002/003
marked superseded by FR-2400. Software Design: engagement section. User Guide: what he says and how
to answer. Master Hardware Design: no change.

## 7. Out of scope
Image descriptions of unknown objects (privacy rule), rear-camera faces, multi-person conversation,
remarks during tasks, learning furniture.
