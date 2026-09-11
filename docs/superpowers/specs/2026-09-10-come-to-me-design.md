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

## 2. Blocking dependencies — read before scheduling this

Two independent hardware blockers, on different legs. Neither prevents building or
unit-testing the software; both prevent live validation of the part they gate.

**A — the navigate leg cannot be live-validated until the wheel encoders work.**
`Navigator` steers by `odometry.pose`, and the encoders have produced no edges on
any of six channels since 2026-08-25. With no pose updates Willy cannot know he has
moved, let alone arrived. The odometry constants were corrected on 2026-08-25 but
have never been confirmed by a driven, measured run.

**B — the knock (§4.7) cannot be commanded on hardware until the arm works.** Two
open items: the arm servo connector(s) found disconnected on 2026-08-20 are still
unresolved (voice `arm_home` and `wave` dispatch correctly and produce zero physical
motion), and per-joint limits are recorded as "Not tested" — `arm_jog.py` has never
been run. Because the arm rail has no current monitor, an uncalibrated knock has no
safety net; see §4.7.

Everything in this spec is designable, buildable and unit-testable now against
`hw_sim` (`WILLY_SIMULATE=1` already fakes odometry). Only live validation waits on
the hardware. Build it, test it in simulation, and hold the live acceptance tests in
§7.

Note the two blockers are independent: the find leg (§4.5, §4.6) is gated by
neither, so it can be built *and* live-tested today by standing in front of Willy
and letting him approach.

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
scripts/import_rooms.py   → add_room()/add_doorway()/add_stair() → world_model.db
```

**Stairs are labelled in the same pass (FR-1200-005, added 2026-09-11).** The
cameras are mounted 15° downward, so the ground plane is in frame and the mapping
run can *propose* stair candidates from floor-plane discontinuities rather than
leaving you to hunt for them — you confirm rather than hunt.

A stair label carries **position, heading and width**, not just a position. A
circle is enough to stay away from and useless for climbing, and FR-1200 says this
chassis will eventually climb them: he will need an approach heading to line up.
Capture it now or the house gets re-labelled later.

`world_model.py` needs a sixth table for this — it currently has `rooms`,
`doorways`, `landmarks`, `objects` and `routes`, and no concept of a hazard,
keep-out or stair anywhere in the codebase.

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

### 4.7 Shut door — knock and ask to be let in

Owner decision 2026-09-10; this replaces the "re-planning if a door is shut" line
previously in §8.

**Detection.** Only ever at a **labelled doorway waypoint** — never at an arbitrary
blocked path, or a sofa in the hallway gets politely knocked on. The condition is:
the current waypoint is a doorway, Willy is within `NAV_ARRIVAL_RADIUS_M` of it, and
front sonar reads an obstacle inside the stop threshold. That is a heuristic, and it
will also fire for a person standing in the doorway or a box left there. Both cases
degrade acceptably — he knocks and asks, which is a reasonable thing to do at a
blocked doorway regardless of what is blocking it.

**Sequence.** A sub-machine inside LEG_NAVIGATE:

```
DOOR_APPROACH   creep to a sonar-measured standoff (KNOCK_STANDOFF_CM)
DOOR_KNOCK      bounded arm oscillation, non-blocking (see below)
DOOR_ASK        "Can someone let me in? I'm trying to get to the kitchen."
DOOR_WAIT       KNOCK_WAIT_S (~15s), re-checking front sonar each tick
                  cleared  → resume the route at the same waypoint
                  blocked  → repeat, up to KNOCK_MAX_ATTEMPTS (3)
                  exhausted → "I knocked but nobody let me in."  → FAILED
```

**The knock motion is bounded and timed — never "move until contact".**

This is the one motion on this robot with no safety net under it, and the design has
to respect that:

- **The arm rail has no current monitor.** The 6V arm rail has no INA260;
  `scripts/servo_current_test.py` was never run and cannot see the arm regardless. If
  a servo ends up *pressing* against a door rather than tapping it, nothing detects
  the stall — it will sit drawing current until something is damaged.
- **Per-joint limits are uncalibrated.** §1458 of Master Hardware Design records arm
  servo range and per-joint limits as "Not tested"; `arm_jog.py` is the tool and has
  never been run. §11.5/§20.6 warn that cheap-clone units may bind before the
  nominal sweep.

Therefore: the knock is a fixed sequence of pulse offsets with a fixed dwell,
modelled directly on `brain.py::_wave()` (`_WAVE_OFFSETS_US` / `_WAVE_DELAY_S`,
non-blocking, stepped on the tick thread, returns to centre). Willy positions himself
by **sonar** so that the tap lands at the end of the arm's travel rather than
pressing through it. There is no contact detection anywhere in the loop, and the code
must never be written as though there is.

**Prerequisites — both are hardware, both are currently open:**

1. The arm servo connector(s) found disconnected on 2026-08-20 must be reconnected.
   Voice `arm_home` and `wave` currently dispatch correctly in software and produce
   zero physical motion.
2. `arm_jog.py` must be run and real per-joint limits recorded, so the knock's offsets
   are known to be inside the joint's travel.

Until both are done, the knock is implementable and unit-testable but must not be
commanded on hardware.

**New config:** `KNOCK_STANDOFF_CM`, `KNOCK_WAIT_S=15.0`, `KNOCK_MAX_ATTEMPTS=3`,
`KNOCK_OFFSETS_US`, `KNOCK_DWELL_S`.

## 5. Failure handling

Every failure is spoken and distinct. Silent failure is the recurring bug pattern in
this codebase; no path ends in a quiet stop.

| Failure | Leg | Behaviour |
|---|---|---|
| Room name unknown | `start()` | Refuse before moving — *"I don't know where the kitchen is."* |
| No route between rooms | navigate | Direct-waypoint fallback, logged (existing behaviour) |
| Pose not inside any known room | navigate | Direct waypoint, and say so — *"I'm not sure where I am, heading over."* |
| Doorway blocked (door shut) | navigate | Knock + ask, up to 3 attempts (§4.7) — not an immediate failure |
| Knocked 3×, still blocked | navigate | *"I knocked but nobody let me in."* → FAILED |
| Arm unavailable / self-test failed | navigate | Skip the knock, still ask aloud, then apply the same retry rule. A dead arm must not make the door silently impassable |
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
- **Knock sub-machine (§4.7).** Fires only at a doorway waypoint, never at an
  arbitrary obstacle; the door clearing mid-wait resumes the route at the same
  waypoint; three exhausted attempts report and fail; the arm being unavailable
  still asks aloud and still retries. Assert the commanded pulses stay inside the
  recorded joint limits — a test that must fail loudly if the offsets are ever
  widened past what `arm_jog.py` measured.

The labeller page is exercised manually, but the JSON schema it emits is validated
by `import_rooms.py`'s tests — that is the contract between the two.

## 7. Live acceptance

Split by which blocker gates it, so the ungated parts are not held behind the
hardware.

**Available now — no blocker (find leg only):**

1. Stand in front of Willy, off to one side so he is not already facing you. He
   sweeps, finds you, approaches, stops at `PURSUIT_STANDOFF_CM`, says *"Found you."*
   Confirms the sweep (§4.5) and the person-width fix (§4.6) — check he stops at a
   sensible distance, not across the room.
2. Same, with nobody present → a full rotation, then *"I can't see you."*

**Held until the encoders work (blocker A):**

3. Mapping run; label at least three rooms and the doorways between them.
4. From a room that is **not** the kitchen, with a person standing in the kitchen:
   *"Willie, I'm in the kitchen, come to me"* → he routes **through the doorway
   waypoint**, not centroid-to-centroid through the wall, arrives, sweeps,
   approaches, stops at standoff, says *"Found you."*
5. The same command with nobody in the kitchen → he arrives, sweeps, and reports
   *"I'm in the kitchen but I can't see you."*
6. Say "stop" mid-route → immediate halt.

**Held until the arm works (blocker B):**

7. Shut the door on the route. He reaches the doorway, backs to standoff, knocks,
   asks to be let in, and waits. Open the door within the wait window → he resumes
   to the kitchen.
8. Same, but leave the door shut → three attempts, then *"I knocked but nobody let
   me in."* Confirm the arm returns to centre after every knock, and check the
   servos are not warm afterwards — that is the check standing in for the current
   monitor the arm rail does not have.

## 8. Out of scope

Multiple people, and knowing which one is you; audio bearing (a single mono capsule,
no array); SLAM or loop closure; following the person after arrival — `PursuitTask`
already has a `follow` mode, and wiring it to this command is a separate decision.

Also out of scope, and worth stating because they are the obvious next asks after
§4.7: **opening the door himself** (needs a calibrated grasp, force sensing and a
handle model — none of which exist), and **re-planning around a shut door** via an
alternative route through the room graph. The second is genuinely attractive once
more than one path exists between rooms, but it needs a graph with alternate routes
in it before it means anything, so it waits for real labelled data.
