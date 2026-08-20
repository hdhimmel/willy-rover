# Willy — User Guide

*For the household, not the workbench. For the engineering details behind any of this, see
`WildWilly_Functional_Requirements_v3.1.md`, `WildWilly_Master_Hardware_Design_v2.0.md`, and
`WildWilly_Software_Design_v1.0.md`.*

**Status as of 2026-08-20: Willy is still in hardware bring-up and testing.** Everything below
describes what's actually built and wired up — but safety checks (including the emergency stop)
and driving itself have not yet been confirmed safe on the real robot. Until that testing is
done, **don't expect Willy to drive around on his own**, and don't rely on him to stop reliably
if something goes wrong. This guide will get an update once that testing is complete.

---

## Waking Willy up

Say **"Hey Willie"**, then your request, the same way you'd talk to any voice assistant. Wait for
a response before your next request — talking over him won't help.

If voice doesn't seem to be responding at all, that's a known open item, not something you're
doing wrong — check with whoever's maintaining Willy.

## What you can ask him right now

**Checking in on him:**
- *"How are you?"* / *"Status report"* — a quick status check.
- *"How's your battery?"* / *"How much charge do you have left?"*
- *"Where are you?"* / *"What room are you in?"*
- *"What time is it?"*
- *"Run diagnostics"* / *"Self test"*

**Small physical gestures (arm only, not driving):**
- *"Wave hello"* / *"Say hi"* — a friendly wave.
- *"Stow your arm"* / *"Home your arm"* — tucks the arm to a safe resting position.

**Saying stop:**
- *"Stop"* / *"Halt"* / *"Freeze"* — Willy recognizes this instantly (it doesn't have to wait
  for him to "think" about it) and stops whatever he's doing.

**Shutting down:**
- *"Shut down"* / *"Power off"* / *"Go to sleep"* — Willy will ask you to confirm before actually
  powering off.

**Teaching him something (works today, but read the caveat below):**
- *"Remember that [something]"* — stores a fact he can recall later.
- *"When I say '[phrase],' do [thing]"* — this exists today, but it's an early, rough version:
  Willy stores what you said and tries to re-figure-out what you meant every time you say the
  phrase again, rather than reliably repeating a fixed set of steps. Treat it as experimental —
  a more dependable version of this (which won't need to "re-guess" each time) is planned. See
  `docs/superpowers/specs/2026-08-20-dynamic-command-learning-design.md` if you're curious about
  what's coming.

## What's built but not yet safe to rely on

These are implemented in software and will work once hardware testing is complete — they're not
missing, just not yet confirmed safe:

- **Driving anywhere** — forward/back/turning, navigating to a named room. Written and tested
  off the physical robot, but the emergency stop hasn't been confirmed working on the real unit
  yet, and nothing should drive before that's done.
- **Mapping a room** — works the same way driving does; same caveat.

## What's not turned on at all yet

- **Smart home control** ("turn on the lights," etc.) — the code exists but needs its own
  dedicated Google account set up first; not available yet.
- **Coming when called, following you, and fetching an object** — all three need Willy's camera
  to actually *see* what it's looking for, and that part (object detection) isn't switched on
  yet, so saying "come here" or "follow me" right now will just get you "my camera isn't
  available." Fetching has the added step of needing the arm calibrated to the real robot's reach
  once vision is on, too.

## If something seems wrong

- If Willy is stuck, unresponsive, or doing something you don't like: say **"stop"** first — it's
  the fastest path, and it's the one that gets checked most carefully in code.
- There's a physical emergency-stop cutoff on the unit itself for when a voice command isn't fast
  enough or he's not listening. Ask whoever's maintaining Willy where it is if you don't know.
- Don't just flip the power switch or yank power if you can avoid it — an abrupt cut can corrupt
  the storage the same way pulling power on any small computer can. If Willy needs to be turned
  off and voice isn't responding, ask the maintainer for the safe shutdown steps.

## Battery

Willy will tell you his charge level if you ask ("how's your battery?"). If it gets low, he'll
automatically stop what he's doing and shift into a lower-power/safe state well before the
battery is actually empty — that part doesn't need you to do anything. The plan is for him to
also drive himself back to somewhere easy to plug in when this happens, but that depends on the
same driving capability flagged above as not yet confirmed safe, so for now, low battery means
"come find him and plug him in," not "he'll come find you."

---

*This guide describes current, real capability only — deliberately not a wishlist. If Willy's
capabilities change (voice gets fully verified, driving gets cleared, smart home comes online),
this file should be updated alongside that work, not left describing an older version of him.*
