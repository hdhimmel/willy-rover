# Bluetooth Phone Companion — Design

**Status:** Approved by owner (Howard Himmel), 2026-08-20. Ready for implementation planning.
**Owner:** Howard Himmel
**Companion docs:** `docs/WildWilly_Functional_Requirements_v3.1.md`,
`docs/WildWilly_Software_Design_v1.0.md`, `CLAUDE.md`.

## 1. Purpose

Willy has no Bluetooth code or hardware documentation today — this is greenfield. The Pi 5 has
onboard Bluetooth 5.0/BLE hardware (per its published spec; **not yet confirmed working on this
specific unit** — first implementation step is a live check, not an assumption to build past).
The owner wants two things, both narrowed during design to what a single BLE radio can honestly
support:

1. **Off-network status alerts** — Willy pushes short alerts (battery low, stuck, task done) to
   the owner's phone over a direct Bluetooth link, independent of the home network/internet.
2. **Rough proximity, reframed as "last seen near you"** — a single radio's signal strength gives
   presence/absence and closer/farther, not a bearing. Rather than overclaim navigation
   assistance the hardware can't deliver, this ships as: Willy logs its own position whenever
   the phone is in strong-signal range, so "where did you last see me?" has a real answer.

**Explicitly one-directional and command-free**, per the owner's own scoping: no commands travel
phone→Willy in this design. That removes the whole "how do we safety-gate an inbound BLE
command" question — there isn't one to answer, because there's no inbound command path at all.

## 2. Why one connection serves both halves

Both capabilities ride the same BLE link: once the owner's phone (via a bookmarked webpage using
Chrome's Web Bluetooth API — no app-store install, same style as the existing Cockpit terminal
workflow) connects to Willy's BLE peripheral service, that connection is both the notification
channel (§3) *and* the thing whose signal strength Willy reads for proximity (§4). No separate
scanning step, no second radio role.

**Android only, by design.** Web Bluetooth doesn't exist on iOS Safari at all. This is a real
platform constraint, not an oversight — if the owner's phone situation changes, this whole
component would need a different phone-side approach (a native app), which is out of scope here.

## 3. Component A — BLE peripheral + status alerts

### 3.1 Rover side

A new `bluetooth_beacon.py`, gated behind a new `config.ENABLE_BLUETOOTH` flag (same
`ENABLE_*` convention as `ENABLE_SMART_HOME`/`ENABLE_VOICE` — off until explicitly confirmed by
the owner at deploy time, matching the precedent set for `ENABLE_CLOUD_AI`/`ENABLE_EMAIL`). Runs
BlueZ in peripheral/GATT-server role via `bluezero` (a maintained Python wrapper over BlueZ's
D-Bus API) — this specific library choice is an implementation detail, not a design commitment;
confirm it's still the right pick when implementation starts.

One custom GATT service, one characteristic:
- **Status characteristic** — supports both `READ` (current status on demand) and `NOTIFY`
  (pushed the moment status changes). Payload is short JSON: `{"event": "...", "text": "...",
  "at": "<timestamp>"}`.

### 3.2 What triggers an alert

Reuses existing signals — no new detection logic, matching how every other cross-cutting feature
in this codebase has been built:

| Trigger | Existing source |
|---|---|
| Battery tier change (warn/RTH/safe/shutdown) | `brain.py::_update_bat_tier()` / `LOW_BATTERY` log event |
| Entering `STUCK` | existing FSM state transition |
| Entering `TILT_FAULT`/`SENSOR_FAULT`/`STALL_FAULT` | existing fault states (the last two added 2026-08-18/19) |
| Fault cleared, waiting for a screen tap | the touchscreen reset-gate added 2026-08-18 (`_await_reset_or_resume()`) — this is a genuinely useful new pairing: today only someone looking at the physical screen knows a fault is waiting on a tap; a BLE alert tells the owner remotely |
| Retrieval task `DONE`/`FAILED` | `retrieval_task.py`'s existing states |

### 3.3 Phone side

A single static HTML/JS page (Web Bluetooth `navigator.bluetooth.requestDevice()` +
`startNotifications()`), bookmarked once. Because it's a small static page with no server
round-trip needed for the actual Bluetooth traffic, it keeps working from cache without network
once bookmarked — matching the "off-network" motivation. Where the page itself is first served
from (the rover's own web server when on the same network, or hosted once elsewhere) is an
implementation detail, not a design question.

## 4. Component B — proximity → "last seen near you"

### 4.1 Reading signal strength

While a phone is connected, the rover periodically reads that connection's RSSI (via BlueZ, not a
GATT characteristic — this is connection metadata, not application data transmitted to the
phone). This is presence/absence and closer/farther only. **It is not a bearing and cannot drive
navigation** — restated here because that limit shaped this whole component's scope (§1.2) and
must not get silently reinterpreted as more than it is during implementation.

### 4.2 Logging position

`world_model.py` already has an `Observation(kind, x, y, payload=...)` mechanism (used today for
sonar-detected obstacles). Reuse it: while the phone's RSSI is above a "nearby" threshold,
periodically (throttled — matching the existing sonar-observation cadence, not every tick) log an
`Observation('phone_nearby', x, y, payload={'rssi': ...})` at the rover's current odometry pose.

### 4.3 Answering "where did you last see me?"

A new voice intent (name TBD at implementation time — not `where_are_you`, which already means
Willy's *own* position) queries the most recent `phone_nearby` observation and answers primarily
with **elapsed time** ("I last had your phone nearby about 4 minutes ago"), not a room name (no
room-identification exists anywhere in this codebase — that's an explicit, separate, still-open
gap) and not a precise position claim (odometry drifts — `WHEEL_DIAMETER_M`/`TRACK_WIDTH_M` are
still unconfirmed placeholders per `config.py`'s own comments). A rough relative distance/heading
*may* be included as a secondary, explicitly-hedged detail, not the headline of the answer.

## 5. Privacy and scope boundaries

- This is **not** a general BLE scanner. Willy never scans for or logs any device besides the one
  phone actively connected to his peripheral service — no passive tracking of other people's
  devices, ever. Worth stating explicitly since "Bluetooth" and "scanning for nearby devices"
  are easy to conflate.
- No commands travel phone→Willy (§1). No motion is ever triggered by this feature.
- `ENABLE_BLUETOOTH` defaults off; needs explicit owner confirmation before shipping enabled,
  same precedent as the other `ENABLE_*` flags that default to a live capability.
- Coexistence with the Pi 5's WiFi (shared RF front-end on most combo chips) should be checked
  live, not assumed neutral — flagged for the implementation/verification pass, not resolved here.

## 6. What this design deliberately does not include (YAGNI)

- No inbound commands over BLE (§1) — the owner explicitly scoped this to alerts-out only.
- No native iOS app — out of scope; this is an Android-only feature as designed (§2).
- No directional/bearing localization — a single radio can't do it; §1.2 reframes "locating" to
  what's actually deliverable instead of building toward a claim the hardware can't support.
- No room-naming in the "last seen" answer (§4.3) — room-identification doesn't exist yet
  anywhere in this codebase; this feature answers with time elapsed, not a place name.

## 7. Open items for the implementation plan

- Confirm the Pi 5's Bluetooth radio is actually present/working on this unit (`bluetoothctl`,
  `hciconfig`) before writing any code against it.
- Confirm `bluezero` (or pick an alternative) once implementation starts.
- Exact "nearby" RSSI threshold and the observation-logging throttle interval — needs live
  tuning on the real hardware, not a number picked in the abstract.
- The new voice intent's exact name and phrasing examples for `voice.py`'s prompt.
- Where the phone-side static page is hosted/first served from.
