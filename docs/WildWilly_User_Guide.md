# Willy — User Guide

*For the household, not the workbench. For the engineering details behind any of this, see
`WildWilly_Functional_Requirements_v3.1.md`, `WildWilly_Master_Hardware_Design_v2.0.md`, and
`WildWilly_Software_Design_v1.0.md`.*

**Status as of 2026-09-10.** Willy now drives on his own, which is the big change since the
last version of this guide. He asks permission first — see the next section, it's the thing
most worth reading.

Two honest caveats, not fine print:

- **He avoids obstacles using sonar only.** Sonar sees hard, flat, straight-on surfaces well.
  It is poor at chair legs, anything low, anything soft, and anything at an angle. He has a
  camera and it is working, but it is deliberately *not* what stops him — so assume he can and
  will bump into things he can't hear.
- **Don't leave him roaming unattended around anything you care about**, or anywhere a fall
  matters — top of stairs, near pets, near a toddler. He has no drop sensor.

The emergency stop is real and works: it's a physical switch that cuts power to the motors and
arm directly, with no software involved, so it works even if he's frozen or confused.

---

## Willy asking to go exploring

**New on 2026-09-09.** Willy no longer wanders off by himself. When he's been idle a while and
wants to explore, he asks:

> *"I would like to go explore. Is that okay?"*

At the same time, a green **LET ME ROAM** button appears on his screen.

**To say yes:** say *"yes"* (or "sure", "okay", "go ahead"), **or** tap the button. Either
works — useful, because his hearing isn't reliable yet.

**To say no:** say *"no"*, or just ignore him. Both do the same thing — he stays put and asks
again in about ten minutes. Saying no isn't permanent; he assumes "no" means "not right now".

**Once you say yes, it lasts until he's restarted.** He won't ask again that session — he'll
just go when he feels like it. To take permission back, say **"stop"**: that halts him *and*
revokes it, so he has to ask again.

He always starts up with permission switched off, so a reboot never leaves him roaming.

## Waking Willy up

Say **"Hey Willie"**, then your request, the same way you'd talk to any voice assistant. Wait
for a response before your next request — talking over him won't help.

If voice doesn't seem to respond at all, that's a known open item, not something you're doing
wrong. His microphone was replaced on 2026-09-09 to try to improve this; whether it actually
fixed it hasn't been confirmed yet. Check with whoever's maintaining Willy.

## What you can ask him

**Checking in on him:**
- *"How are you?"* / *"Status report"*
- *"How's your battery?"* / *"How much charge do you have left?"*
- *"Where are you?"* / *"What room are you in?"*
- *"What do you see?"* / *"What's in front of you?"*
- *"What time is it?"*
- *"Run diagnostics"* / *"Self test"*

**Driving him yourself:**
- *"Forward"* / *"Back"* / *"Turn left"* / *"Turn right"* — a short, slow nudge in that
  direction, not a continuous drive. Repeat for more.

**Coming to you:**
- *"Come here"* / *"Come over here"* — he approaches and stops a short distance away.
- *"Follow me"* — the same, then he keeps pace with you until you say stop.

  **The catch:** he can only come to you if he can *already see you* when you ask. He doesn't
  yet turn around and look for you, so if you're behind him or in another room, he'll simply
  report that he can't see anyone. Stand where he's facing. He also tends to stop further away
  than he should — both are known and being worked on.

**Mapping:**
- *"Start mapping"* / *"Stop mapping"* — he records what he sees and bumps into while he drives
  around, building up a picture of the place.

**Small gestures:**
- *"Wave hello"* / *"Say hi"*
- *"Stow your arm"* / *"Home your arm"*

  **Note:** the arm currently doesn't physically move — a connector came loose inside and hasn't
  been reconnected yet. He'll acknowledge the command and nothing will happen. That's this
  fault, not you.

**Saying stop:**
- *"Stop"* / *"Halt"* / *"Freeze"* — recognised instantly, without waiting for him to "think".
  This is the one command that skips the queue entirely. It also revokes roaming permission.

**Shutting down:**
- *"Shut down"* / *"Power off"* / *"Go to sleep"* — he'll ask you to confirm first. Say *"yes"*
  to go ahead. If you don't answer within about thirty seconds he cancels it himself.

**Email:** if new mail arrives, Willy reads out who it's from and the subject. He only ever
tells you — he never acts on an email.

**Teaching him something:**
- *"Remember that [something]"* — stores a fact he can recall later.
- *"When I say '[phrase],' do [thing]"* — experimental. He stores what you said and re-works out
  what you meant each time, rather than reliably repeating fixed steps. A more dependable
  version is planned; see `docs/superpowers/specs/2026-08-20-dynamic-command-learning-design.md`.

## What doesn't work yet

- **"Go to the kitchen."** The command exists, but nobody has taught him where any room *is*
  yet, so he'll tell you he doesn't know where it is. Teaching him rooms is designed but not
  built — see `docs/superpowers/specs/2026-09-10-come-to-me-design.md`.
- **Fetching an object.** Switched off, and blocked by the arm fault above.
- **Anything needing the arm.** Same fault — waving, stowing, and fetching all currently do
  nothing physically.
- **Smart home control** ("turn on the lights"). The code exists but needs its own dedicated
  Google account set up first.
- **Knowing how far he's travelled.** His wheel sensors have produced nothing since
  2026-08-25, so he can't tell how far he's gone or where he is. It doesn't affect his driving
  or his ability to stop — it's why he can't yet navigate to a named place.

## If something seems wrong

- Say **"stop"** first. It's the fastest path and the one most carefully checked in code.
- **There's a physical emergency-stop cutoff on the unit.** It kills power to the motors and arm
  outright, with no software involved, so it works even if he's frozen or ignoring you. Ask
  whoever maintains Willy where it is if you don't know — worth knowing *before* you need it.
- **Don't yank the power** if you can avoid it — an abrupt cut can corrupt his storage, the same
  as any small computer. If he needs turning off and voice isn't working, ask the maintainer for
  the safe shutdown steps.
- If he trips over something, gets stuck, or repeatedly stops with a fault, tell the maintainer
  roughly *when* — his logs are easier to read against a time.

## Battery

Ask *"how's your battery?"* any time. If it gets low he'll stop what he's doing and shift to a
low-power state well before it's actually empty, without you doing anything.

He can't yet reliably drive himself somewhere to be plugged in — that needs the wheel sensors
mentioned above. **For now, low battery means "go and find him and plug him in", not "he'll
come and find you".**

---

*This guide describes current, real capability only — deliberately not a wishlist. If Willy's
capabilities change, update this file alongside that work rather than leaving it describing an
older version of him. Last reviewed against the code on 2026-09-10.*
