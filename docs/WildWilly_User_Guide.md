# Willie — User Guide

*For the household, not the workbench. For the engineering details behind any of this, see
`WildWilly_Functional_Requirements_v3.1.md`, `WildWilly_Master_Hardware_Design_v2.0.md`, and
`WildWilly_Software_Design_v1.0.md`.*

**Status as of 2026-10-07.** Since the last version of this guide (2026-09-10): his arm moves,
his wheel sensors count, he can turn on the spot properly, he can learn rooms, routes and faces,
and he looks around for you when you call him. Everything below was checked against the code on
that date. Things built but not yet tried on the real rover are marked *(not yet tried for real)*.

Honest caveats, not fine print:

- **He can still bump into things.** He watches ahead with sonar plus a close-range depth
  sensor, and to the sides with sonar. Sonar is poor at soft furniture, chair legs and anything
  at an angle. **Nothing watches behind him**, which matters most when he turns on the spot.
  His cameras help him choose which way to turn, but they never decide whether to stop.
- **Don't leave him roaming unattended** around anything you care about, near pets or a
  toddler, or near the top of stairs. His depth sensor can now see a drop just in front of him,
  but only close up, and it has not been tested at a real edge.
- **The emergency stop is the main power switch.** It cuts everything, Willie's computer
  included, with no software involved, so it works even if he's frozen. It is not gentle — see
  "If something seems wrong".

---

## Willie asking to go exploring

When he's been idle a while and wants to explore, he asks:

> *"I would like to go explore. Is that okay?"*

and a green **LET ME ROAM** button appears on his screen.

**To say yes:** say *"yes"* (or "sure", "okay", "go ahead"), **or** tap the button.

**To say no:** say *"no"*, or ignore him. He stays put and asks again in about ten minutes.

**Yes lasts until he's restarted.** To take it back, say **"stop"** — that halts him *and*
revokes permission. He always starts up without permission, so a reboot never leaves him roaming.

## Waking Willie up

Say **"Hey Willie"**, then your request. Wait for him to answer before the next one.

Common commands (the ones listed in **bold** below) are recognised instantly. Anything else he
has to think about, which takes several seconds — and **if he is driving when he starts thinking,
he stops first** and carries on afterwards. That pause is deliberate: while he thinks, nothing
else in him runs, so he brakes rather than drive blind.

## What you can ask him

**Anything, really.** Questions and conversation that aren't one of the commands below are
answered by his on-board model, or — with internet — a cloud model. He can't *do* anything
through conversation that the commands below don't allow; talking is just talking.

**His personality:** in casual conversation he sometimes answers playfully, and he goes a bit
shy if you compliment him or ask him personal questions. Anything about safety or faults is
always said plainly. When he talks, his mouth moves with the words. *(New, not yet seen for real.)*

**Checking in on him:**
- **"How are you?"** / **"Status report"**
- **"How's your battery?"**
- **"Where are you?"** / **"What room is this?"**
- **"What are you doing?"** / **"What are you up to?"** — one short sentence: exploring,
  turning, on his way somewhere, waiting, or stopped and why. Works even while he's moving.
- **"What do you see?"** / **"What are you looking at?"** — up to three things he recognises.
- **"What time is it?"** / **"What's the date?"**
- **"Run diagnostics"** / **"Self test"**

**Driving him yourself:**
- **"Forward"** / **"Back up"** / **"Turn left"** / **"Turn right"** — a short, slow nudge, not
  a continuous drive. Repeat for more.

**Pointing his wheels (parked only):**
- **"Steer left"** / **"Steer right 20 degrees"**: the front wheels point that way and the
  back wheels the other way. He doesn't drive. With no angle given it's 15 degrees, and the
  most is 37.
- **"Wheels straight"**: back to straight.

  He holds them there until you say "wheels straight" or "stop", or until he moves off. When
  he moves off he straightens them first. He refuses while his wheels are turning.

**Turning on the spot:**
- **"Turn around"** — a half turn.
- **"Turn left 90 degrees"** / **"Turn right 45 degrees"** — any angle you name.

  He angles his corner wheels first, then spins, and stops on his compass. **He needs room:**
  if anything is closer than about 20 cm in front or to either side he refuses and tells you
  which side. He can't see behind, so give him space there too; if something stops him turning,
  he notices within about a second and stops.

**Coming to you:**
- *"Come here"* — he looks around for you if you're not in view, approaches, and stops a short
  distance away. *(The looking-around is not yet tried for real.)*
- *"Follow me"* — the same, then he keeps pace with you until you say stop.
- **"I'm in the kitchen, come to me"** / **"Come to me in the kitchen"** — he drives to that
  room, through the doorways he knows, then looks for you. *(Not yet tried for real.)* He has to
  have been taught the room first (next section); if a doorway is shut he asks to be let in,
  up to three times. *(He can also knock with his arm first, but that stays off until his
  knocking position has been measured.)*

**Teaching him your home:**
- **"This is the kitchen"** — with him standing in a room, names it. Do each room you want him
  to know. Until you do, he'll say he doesn't know where the kitchen is.
- **"The stairs are here"** — with him facing a staircase, marks it so he keeps back from it.
- **"Learn the way to the kitchen"** — then lead him (or drive him) there and say **"That's
  it"**. Later, **"Show me the way to the kitchen"** follows that route. From where you
  started teaching it, he does the whole way. From somewhere else along it, he joins it at
  the nearest point, within about a metre, and follows the rest. Farther away than that, he
  tells you he's too far from it.

  Where he thinks he is comes from counting wheel turns, which drifts over distance and has not
  been checked on the floor yet. Expect labelled places to be approximate.

**People:**
- **"This is Carolyn"** — with that person in front of him, he learns their face and greets
  them by name afterwards. New faces need Howard's approval by email.
- **Someone he doesn't know:** if he's confident he has never seen a person, he asks who they
  are. If he's only unsure (bad light, a turned head) he stays quiet rather than treat a family
  member as a stranger.
- **"Forget everyone"** — deletes every face he has learned.

**Remembering things:**
- *"Remember that [something]"* — stores a fact.
- **"What do you remember?"** / **"What do you know about [something]?"**
- **"Forget [something]"**
- **"What do I usually ask?"** — the routines he has noticed.
- *"When I say '[phrase]', do [thing]"* — experimental; he re-works out what you meant each time.

**Mapping:**
- **"Start mapping"** / **"Stop mapping"** — he records what he sees and bumps into as he drives.

**His arm:**
- **"Wave hello"** / **"Say hi"** — raises the arm and waves.
- **"Stow your arm"** / **"Put your arm away"** — moves it to the rest position, opening the
  elbow first so it doesn't hit him. If the arm strains, he lets it go limp and says so.

**Saying stop:**
- **"Stop"** / **"Halt"** / **"Freeze"** / **"Whoa"** — recognised instantly and handled before
  anything else. It also revokes roaming permission.

**After a fault — "reset":**
- If he stops with a fault (a stuck wheel, a tilt, a sensor dropping out), he **stays stopped
  even after the cause clears** and ignores driving commands until you reset him. Say **"Reset"**
  or **"All clear"**, or **tap his screen**. This is on purpose: he never restarts moving by
  himself after something went wrong.

**Shutting down:**
- **"Shut down"** / **"Power off"** / **"Go to sleep"** — he asks you to confirm. Say
  **"confirm"** or **"yes"** within **15 seconds**, or he cancels.

**Email:** when new mail arrives, he reads out who it's from and the subject.

**He also acts on email from Howard — including driving.** Nobody else's mail can make him do
anything, and he checks the message really came from Howard's account (DKIM), not just that it
claims to. He says out loud what he's about to do first. Email can't answer his questions for
you — it can't confirm a shutdown or give him permission to roam.

**From Home Assistant / Google Home:** four commands work remotely — **status**, **battery**,
**stop** and **come here** — and nothing else. They go through exactly the same safety checks
as speaking to him. (Google Home needs linking to Home Assistant first.)

**He may email Howard asking for a feature**, usually when something has failed several times.
Howard approves by replying with the subject line **"Willie: approve <code>"** from the email;
a plain reply doesn't count. Approval files the request — nothing changes until someone builds it.

## What doesn't work yet

- **Fetching an object.** Switched off on purpose: the grasp moves need re-doing with measured
  positions before the arm is trusted to reach for things.
- **Smart home control** ("turn on the lights"). Needs its own Google account set up first.
- **Knowing his position accurately.** He counts wheel turns, which drifts, and one front wheel's
  sensor has been unreliable (if he stops with a "wheel stall" fault for no reason, that's likely
  it — reset him and tell the maintainer).
- **Driving himself to his charger.** Not built.

## If something seems wrong

- Say **"stop"** first. It's the fastest path and the most carefully checked one.
- If he's stopped and won't drive, he's probably **waiting for a reset** — say **"reset"** or tap
  the screen. His screen shows why he stopped.
- **The STOP SVC button on his screen** (tap it, then tap again to confirm) brakes him and stops
  his software altogether. Use it if voice isn't working. He stays inert afterwards, screen and
  all, until he's restarted — the maintainer, or switching him off and on.
- **The emergency stop (main power switch)** kills everything at once, his computer included.
  Use it if he's doing something dangerous and won't stop. Otherwise prefer **"shut down"**: a
  sudden power cut can corrupt his storage like any small computer.
- If he trips over something, gets stuck, or keeps stopping with a fault, tell the maintainer
  roughly *when* — his logs are easier to read against a time.

## Privacy

- **To switch his microphone and camera off:** say **"Privacy mode"**, **"Stop listening"** or
  **"Turn off your microphone and camera"**. He says so, then both go off. His screen shows
  **"PRIVACY: microphone and camera OFF"**. It stays off, even across restarts, until you turn
  it back on.
- **To turn them back on:** tap **RESUME LISTENING** on his screen **twice** (the first tap
  arms it, the second confirms — so a brush against the screen can't do it). Howard can also
  send the email command **"privacy off"**. You can't do it by voice — he can't hear you.
- **While it's on:** he can't hear "Hey Willie" or **"stop"**, can't see you or recognise faces.
  To stop him, use the **STOP SVC** button on his screen or the power switch.

## Battery

Ask **"how's your battery?"** any time. He reads it from the motor supply monitor, which is
accurate while the motor switch is on. Below 11.4 V he warns. From 10.8 V down he stops moving,
and if it stays low he shuts himself down cleanly, well before the battery is damaged.

**Known problem (2026-10-07):** his second battery sensor is wired wrong and reads too low. While
the motor switch is **on** this doesn't matter. With the motor switch **off**, he can't tell if
the battery is low, so don't leave him running for long with the motors switched off until the
maintainer fixes it.

**Low battery means "go and find him and plug him in"** — he can't drive himself to a charger.

---

*This guide describes current, real capability only — not a wishlist. When Willie's
capabilities change, update this file alongside that work. Last reviewed against the code on
2026-10-07.*
