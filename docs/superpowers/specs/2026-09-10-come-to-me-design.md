# "Willie, I'm in the kitchen, come to me" — design

**Date:** 2026-09-10
**Status:** design approved in chat; not yet planned or implemented
**Owner decisions:** real room navigation (not a search heuristic); rooms labelled
after a mapping run; labelling via export → browser page → import; doorways
labelled and routed through.

---

## 1. Goal

One spoken command — *"Willie, I'm in the kitchen, come to me"* — sends Willy to a
named room and then has him find the speaker inside it, stopping a polite distance
away.

Success is **not** arriving in the kitchen. Success is being within
`PURSUIT_STANDOFF_CM` of an actual person. Arriving and failing to find anyone is a
distinct, separately-reported outcome.

## 2. Blocking dependency — read before scheduling this

**The navigate leg cannot be live-validated until the wheel encoders work.**
`Navigator` steers by `odometry.pose`, and the encoders have produced no edges on
any of six channels since 2026-08-25. With no pose updates Willy cannot know he has
moved, let alone arrived. The odometry constants were corrected on 2026-08-25 but
have never been confirmed by a driven, measured run.

Everything in this spec is designable, buildable and unit-testable now against
`hw_sim` (`WILLY_SIMULATE=1` already fakes odometry). Only live validation waits on
the hardware. Build it, test it in simulation, and hold the live acceptance test in
§7.

Secondary: the wake word has been unreliable and unexplained since 2026-08-21. The
2026-09-09 mic swap may or may not have addressed it. If "hey Willie" is not heard,
none of this is reachable by voice.

## 3. What already exists

Substantially more than it first appears. Re-check this table before writing
anything.

| Piece | State |
|---|---|
| `go_to` intent, `Mission(room=…)` | Wired, `brain.py:759` |
| `rooms` / `doorways` tables, `add_room()`, `add_doorway()`, `all_doorways()` | Exist in `world_model.py` |
| Room-graph shortest path over doorways | **Already implemented** — `navigation.py::_graph_path()`, networkx |
| `Navigator` waypoint following, SEEKING/AVOIDING, `abort()` | Exists |
| `PursuitTask` — person detection, bearing correction, approach to standoff | Exists |
| `MappingSession` — sonar obstacle map + vision landmarks | Exists |
| Room identification from a mapping run | **Gap** — `_rooms` starts empty, nothing populates it |

## 4. Design

### 4.1 Teaching flow (one-time per house)

```
"Willie, start mapping"   → sonar obstacle map + vision landmarks accumulate
"Willie, stop mapping"    → world_model.save()
scripts/export_map.py     → map.json
tools/label_rooms.html    → drag in map.json; click to name a room;
                             click room A then room B to drop a doorway between them
                          → rooms.json
scripts/import_rooms.py   → add_room()/add_doorway() → world_model.db
```

The labeller is a **local HTML file, not a hosted page**. It has to write
`rooms.json` back to disk, which a sandboxed hosted artifact cannot do. A plain file
opens in any browser — including a phone — with no server on the robot and no new
dependency, and adds no network surface to a machine that drives motors.

### 4.2 Runtime flow

```
"Willie, I'm in the kitchen, come to me"
  → intent come_to_me {room: 'kitchen'}, drained at Directive 6
  → ComeToMeTask.start('kitchen'); brain._go('COME_TO_ME')

  LEG_NAVIGATE   Navigator, Mission(room='kitchen')
  LEG_FIND       sweep, then PursuitTask in come_here mode
  DONE           "Found you."
```

### 4.3 New module: `come_to_me_task.py`

Sequences the two existing machines. It owns one top-level `brain.py` FSM state,
`COME_TO_ME`, and its own sub-states — the same shape as `RetrievalTask`,
`Navigator` and `PursuitTask`, so Directives 1–5 are enforced by
`RoverBrain._tick()` before it ever ticks, and `abort(reason)` is the uniform
preemption contract.

Rejected alternatives:

- **Chaining `NAVIGATE` → `PURSUE` with a "then pursue" flag in `brain.py`.** Puts
  orchestration into an already-large `_tick()` and adds exactly the kind of hidden
  pending-state that has caused bugs in this codebase before.
- **A navigate-first leg inside `PursuitTask`.** Conflates two concerns in a module
  that is currently single-purpose and readable.

### 4.4 Change to `navigation.py` — route through doorways, not centroids

`_graph_path()` already returns the correct room sequence. The gap is one line:
`_resolve_room()` emits `[(rooms[n].cx, rooms[n].cy) for n in path[1:]]`, i.e. the
**room centroids** along the route. Each `Doorway` carries its own `x, y`, and that
coordinate is never used as a waypoint.

Steering centroid-to-centroid drives at the wall between two rooms and leaves sonar
to scrape along it until something gives. Interleave the doorway coordinates instead
— for each consecutive pair in the path, the doorway point between them, then that
room's centroid, ending at the target centroid:

```
lounge → hall → kitchen
  [ doorway(lounge,hall).xy, hall.centroid,
    doorway(hall,kitchen).xy, kitchen.centroid ]
```

Keep the existing honest fallbacks unchanged: unknown current room, or no graph path,
still yields a direct waypoint with the existing log line. Do not invent planning
that is not there — `world_model.py`'s "do not pretend this is full SLAM" applies
here too.

### 4.5 The find leg needs a search sweep

Arriving in the kitchen, Willy faces an arbitrary direction.
`PursuitTask._localize()` currently takes a frame, and if no person is in it,
increments a counter and looks at the *same view* again — failing after 20 ticks
without ever moving. It can approach a person it can already see; it cannot look for
one.

LEG_FIND therefore adds a sweep: on no detection, point-turn a fixed increment, look
again, up to one full rotation before reporting failure.

### 4.6 Person width — a prerequisite, not a nice-to-have

`vision.py::localize()` computes range from bounding-box width using
`_ASSUMED_OBJECT_WIDTH_CM = 8.0`, commented as "generic small handheld object — no
real per-class size table". A person is roughly 50 cm across, so distance comes out
about 6× too near, and Willy decides he has "arrived" while still across the room.

Add a minimal per-class width table with an entry for `person`, falling back to the
existing 8.0 for anything else. Without this the find leg cannot work, so it belongs
in this change rather than in a separate one.

`_ASSUMED_HFOV_DEG = 70.0` is likewise unmeasured for this camera and sets bearing
accuracy. Leave it alone, but record it as a known error source rather than
silently depending on it.

## 5. Failure handling

Every failure is spoken and distinct. Silent failure is the recurring bug pattern in
this codebase; no path ends in a quiet stop.

| Failure | Leg | Behaviour |
|---|---|---|
| Room name unknown | `start()` | Refuse before moving — *"I don't know where the kitchen is."* |
| No route between rooms | navigate | Direct-waypoint fallback, logged (existing behaviour) |
| Pose not inside any known room | navigate | Direct waypoint, and say so — *"I'm not sure where I am, heading over."* |
| Navigator FAILED (blocked/stuck) | navigate | *"I couldn't get to the kitchen."* → FAILED |
| Arrived, full sweep, no person | find | *"I'm in the kitchen but I can't see you."* → FAILED |
| Directive 1–4 preemption | any | `abort(reason)`, same contract as the other tasks |
| Spoken "stop" | any | `voice.stop_requested` bypasses the queue and aborts |

**Odometry drift is expected and tolerated by design.** The navigate leg is
dead-reckoned with no loop closure, so error accumulates across a multi-room route.
The find leg is what rescues it: Willy does not need to land on the kitchen
centroid, only close enough to see a person. This is why the feature can work on
odometry that will never be excellent — and also why the sweep in §4.5 is
load-bearing rather than cosmetic.

## 6. Testing

TDD throughout. Tests run on the rover under `WILLY_SIMULATE=1` — the laptop has
neither `pytest` nor `pygame` and cannot import `brain`.

- **Route resolution.** Synthetic room/doorway graph: a multi-hop route interleaves
  doorway coordinates; an unknown room refuses; no path falls back to a direct
  waypoint; already-in-target-room is a single waypoint.
- **Leg sequencing.** Navigate DONE → find starts. Navigate FAILED → find is
  **never** started and the task reports FAILED. Abort during each leg stops motion
  and reports.
- **Persistence.** `add_room`/`add_doorway` → `save()` → `load()` round-trips, and
  `import_rooms.py` rejects a malformed `rooms.json` rather than writing partial
  state.
- **Person width.** A bounding box of known width yields a plausible person
  distance, and a non-person class still uses the old constant.

The labeller page is exercised manually, but the JSON schema it emits is validated
by `import_rooms.py`'s tests — that is the contract between the two.

## 7. Live acceptance (held until the encoders work)

1. Mapping run; label at least three rooms and the doorways between them.
2. From a room that is **not** the kitchen, with a person standing in the kitchen:
   *"Willie, I'm in the kitchen, come to me"* → he routes through the doorway,
   arrives, sweeps, approaches, stops at standoff, says *"Found you."*
3. The same command with nobody in the kitchen → he arrives, sweeps, and reports
   *"I'm in the kitchen but I can't see you."*
4. Say "stop" mid-route → immediate halt.

## 8. Out of scope

Multiple people, and knowing which one is you; audio bearing (a single mono capsule,
no array); re-planning if a door is shut; SLAM or loop closure; following the person
after arrival — `PursuitTask` already has a `follow` mode, and wiring it to this
command is a separate decision.
