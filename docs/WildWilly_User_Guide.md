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
  at an angle. Behind him there is a second depth sensor (the rear sonar is not working at the
  moment). While exploring, his **front camera also brakes** for chairs, tables, couches, beds and
  people in his path (since 2026-10-14) -- table tops and seats stick out further than his
  sonar sees. If he starts exploring with something close in front, he turns away first, and
  while exploring he starts curving away from things about a metre ahead instead of driving
  straight at them. If he is boxed in on one side and has tried twice, he turns all his wheels
  hard toward the open side and side-steps.
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

After asking, he **beeps and listens for your answer** — no need to say "Hey Willie" first.

**To say yes:** say *"yes"* (or "yeah", "sure", "okay", "alright", "go ahead", "go for it", "of course",
"go explore"), **or** tap the button. Anything with "no", "not", "don't", "later" or "wait" in it is a no.
Say it after the beep, while the green circle is on.

**To say no:** say *"no"*, or ignore him. He stays put and asks again in about ten minutes.

**You don't have to wait for him to ask.** Say **"Hey Willie, go explore"** (or "explore",
"roam", "go wander", "start exploring") and he sets off straight away — that counts as your yes.

The same beep-and-listen happens for any question he asks, for example "Are you sure you want
me to shut down?".

**Yes lasts until he's restarted.** To take it back, say **"stop"** — that halts him *and*
revokes permission. He always starts up without permission, so a reboot never leaves him roaming.

## Willie starts conversations

When he is idle or exploring, Willie now speaks first. He stops, turns toward you or the thing he
means, says one short sentence, and (for a question) beeps and listens.

**What he says:**
- **A greeting** when he sees someone he knows: *"Hi Carolyn!"* (or *"…I last saw you yesterday
  morning"*, if that was over 2 hours ago). Once per visit; a visit ends after 30 minutes of not
  seeing you. A restart does not make him greet you again.
- **A stranger:** *"Hi, I'm Willie! What's your name?"* Once per visit (a guest who stays all
  evening is asked once). He remembers the name only until the visit ends and does not learn the face.
- **Questions:** *"What room is this?"*, *"Whose ball is that?"* (once per kind of thing), and
  later *"How's your day going?"*.
- **Remarks:** things he remembers (*"There's Storm's ball. I last saw it this morning."*, or
  something you told him at least 2 hours earlier, once a day at most) and
  changes (*"I haven't seen a ball in the kitchen before."*).

At most one remark or question every 5 minutes (a greeting also starts that wait), and never the
same question or remark twice in a day. He needs someone in view for anything but a greeting. He stays quiet
while he is doing a job, listening or talking, in privacy mode, or on a low battery.

**To answer:** wait for the **beep**, then speak while the **green circle** is on. No "Hey Willie"
needed. If you don't answer he drops it. Say **"stop"** to end it.

**Answers are remembered:** room names, who owns what (*"it's Storm's"*) and what you tell him about
your day, notes about people are kept 30 days; labels for things and room names stay. Say **"forget everyone"** to wipe faces.

**To turn it off:** set `ENABLE_ENGAGEMENT=False` in `config.py` and restart him.

---

## Waking Willie up

Say **"Hey Willie"**, then your request. Wait for him to answer before the next one.
A **solid green circle** (top left of his screen) stays on for as long as he is recording you;
when it goes off he has stopped listening and is thinking. A green tick after that means he
understood words.

Common commands (the ones listed in **bold** below) are recognised instantly. Anything else he
has to think about, which takes a few seconds. Thinking no longer stops him: his on-board model
runs separately from his driving and sensors (since 2026-10-10), so he keeps watching where
he's going while he thinks.

## What you can ask him

**Anything, really.** A plain question — *"Why is the grass green?"*, *"Who wrote Hamlet?"*,
*"Tell me a joke"* — goes straight to a fast cloud model (with internet) and he answers in a
sentence or two. While it's being looked up he says something like *"Hmm, that's a tough
question"* or *"Give me a minute to think about that"*, and the screen shows "Sending … to cloud
AI". He can't *do* anything through conversation that the commands below don't allow; talking
is just talking.

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
- **"Do you see a red ball?"** / **"Is there a cup in front of you?"** — he checks his camera and
  says yes and where (left, right, in front), or no and what he does see.
- **"What time is it?"** / **"What's the date?"**
- **"Where are you?"** — the room he's in, and with GPS (outdoors only — it needs sky) how far
  and which way from home. By email he replies with a map link.
- **"This is home"** (outdoors, with GPS) — he learns where home is over about a minute.
- **"What's your address?"** / **"Where do you live?"** — his home address.
- **"Who are your owners?"** / **"Who are your parents?"** — Carolyn and Howard Himmel.
- **"Go home"** — not yet: he says why.
- If he wanders more than 50 m from home outdoors, he emails his position every few minutes,
  and once more when he's back.
- **"Check your logs"** / **"Any errors today?"** — he sums up the last 24 hours of his log in one
  sentence (the top three problems, and how many other kinds). If there were problems he asks
  **"Do you want me to ask for a fix?"** and listens for your answer; **yes** emails you a fix
  request with an approval code (the usual feature-request process).
- **"Run diagnostics"** / **"Self test"**

**Driving him yourself:**
- **"Forward"** / **"Back up"** / **"Turn left"** / **"Turn right"** — a short, slow nudge, not
  a continuous drive. Repeat for more.

**Pointing his wheels (parked only):**
- **"Steer left"** / **"Steer right 20 degrees"**: the front wheels point that way and the
  back wheels the other way. He doesn't drive. With no angle given it's 15 degrees, and the
  most is 37.
- **"Wheels straight"** or **"Straighten your wheels"** (with or without "please"): back to straight.

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
- **Someone he doesn't know:** if he's confident he has never seen a person, he says hello and
  asks their name (see "Willie starts conversations"). If he's only unsure (bad light, a turned
  head) he stays quiet rather than treat a family member as a stranger.
- **"Forget everyone"** — deletes every face he has learned.

**Remembering things:**
- **Find Storm:** *"Hey Willie, find Storm"* -- he explores until he sees her, says so, goes over and
  stops about a metre away. *"Tidy up the toys"* -- he explores, tells you each toy he finds and
  sums up at the end (picking them up and putting them in the toy box comes once his arm is
  calibrated). *"This is the toy box"* -- tells him where the box is. *"Stop"* ends either.
- **Memory:** he keeps what you tell him ("remember that ...", "... remember that", "my name is
  Howard") and, by himself, when he saw people and Storm, toys he found and places he learned.
  Ask *"When did you last see Storm?"* or *"What did you do today?"*. If he only half-heard, he
  asks you to say it again instead of saving it.
- **Names:** *"That dog's name is Storm"* -- he remembers it and says "I can see Storm" from then on.
- **Start-up check:** about 12 seconds after he starts, he checks every sensor is actually giving
  readings and tells you any that are not ("Start-up check: my rear sonar is not working").
- **Battery log:** every 2 hours while he is on, he records his battery voltage, estimated %, and how many hours he has been running since his last charge (counted minute by minute; restarting him no longer adds a row), and pushes it to the `battery-log` branch on GitHub (https://github.com/hdhimmel/willy-rover/blob/battery-log/battery_log.csv). Readings taken offline go up with the next one.
- *"Remember that [something]"* — stores a fact "Remember, …", "remember …" and "I want you to remember …" work too.
- *"My name is Howard"* (or *"call me Howard"*, *"remember, my name is Howard"*) — he remembers it; *"what's my name?"* answers from that, or from your face if he recognises you.
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
  If the arm switch (SW-A) is off, he says "My arm power is switched off" instead of moving it.
- **Teaching him an arm position:** say **"teach your arm"**, then move one joint at a time:
  **"shoulder up/down"**, **"elbow up/down"**, **"wrist up/down"**, **"wrist left/right"**,
  **"arm left/right"** (turns the base), **"open/close your hand"**. **"More"** repeats the last
  move; **"bigger steps"** / **"smaller steps"** change how far. When it looks right, say
  **"remember this as"** and a name, e.g. *"remember this as knock"*. **"Done teaching"** ends it.
  Later, **"pose knock"** (or *"show me pose knock"*) moves the arm back there. **"What poses do
  you know"** lists them; **"forget the pose knock"** deletes one. Moving his arm by hand teaches
  him nothing — he only knows where he moved it himself.
- **Picking things up:** *"Pick up the red ball"* — he finds it (by colour if he can't name it),
  lines it up on his left side, reaches down, grips and lifts it, and holds it until you say
  **"let go"** (opens his hand where it is) or **"put it down"** (sets it gently back on the floor).
  If nobody takes it within a minute, he puts it back down by himself. After the lift he looks with his camera: if the ball is still on the floor he says
  he missed and tries again (twice), so "Got the ball" now means it left the floor.
  *(2026-10-14: the reach still misses until his arm angles are measured; a camera-guided reach
  is built and switches on once they are.)*
- **Teaching him to reach things:** put a cup, bottle or ball (he can't recognise a tape roll) on
  the floor in front of him with his arm put away and say **"learn this spot"**. He looks, reaches
  out, and starts arm teaching: move it with "shoulder down", "elbow up" and so on until the hand
  touches the object, then say **"remember this reach"**. Do it at several spots (6 to 9 across the
  floor in front of him). Then **"touch the cup"** makes him work out the arm position for wherever
  the cup is, from the spots he learned. **"Forget your reach spots"** clears them.
- **Routines:** *"When I say goodnight, do stow your arm, then go home, then wave."* Each step
  must be something he already understands, or he tells you which one he doesn't. Saying
  **"goodnight"** then runs the steps in order, each one after the last has finished.
  **"Stop"** cancels the rest. **"Forget goodnight"** deletes it.
- **Arm positions are being re-measured** after the shoulder rebuild (servos replaced
  2026-10-15). Wave, stow and pick-up run, but watch the arm the first few times.

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

## His screen

His face fills the top of the screen. The line underneath shows his state (IDLE, ROAM, …) and
what each sensor sees: **F** front, **L** left, **R** right, **B** behind — green is clear,
amber is close, red is too close (under 20 cm). **B --** means nothing is reading behind him.
Below that is what he's doing or saying. Top right: the red **STOP SVC** button (two taps)
and his network.

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
