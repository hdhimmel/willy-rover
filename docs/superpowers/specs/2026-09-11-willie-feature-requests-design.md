# Willie proposes features, the owner approves by email — design

**Date:** 2026-09-11
**Status:** design approved in chat; not implemented.
**Owner decision:** Willie emails the owner with new feature requests; the owner approves
by email; a later development session implements the approved ones.

---

## 1. The problem this actually solves

The loop does not close on email alone. **The person who writes the code cannot read the
owner's inbox.** An approval sitting in Gmail is invisible to a development session, so
"approve by email so it can be coded" needs somewhere durable for the approved request to
land.

So the design is a **queue in the repo**, with email as the approval channel in front of
it:

```
Willie observes something failing repeatedly
  → composes a request, emails the owner + one-time code
  → owner replies "APPROVE <code>"      (FR-2000-013 DKIM check applies)
  → Willie writes docs/feature-requests/YYYY-MM-DD-<slug>.md   status: approved
  → Willie commits THAT FILE ONLY and pushes it
  → next development session reads the queue
```

Every piece of that except the queue directory and the composer already exists.

### 1.1 Willie commits it himself — and never with `git add -A`

The approval comes back to Willie, and Willie is what puts it in GitHub. He does not
wait for `scripts/auto_backup.sh`.

**He must stage exactly the one file**, commit it with a real message, and push:

```
git add docs/feature-requests/<file>.md
git commit -m "Feature request approved by owner: <title>"
git push origin main
```

**Never `git add -A`.** The hourly backup cron does exactly that, and on 2026-09-09 it
swept a session's in-progress, still-untested work into a commit titled "Automated
backup: <timestamp>". It only failed to reach GitHub because the rover happened to be
behind and the push was rejected. A targeted `git add <path>` cannot do that, and the
narrower command is the safer one.

If the push fails — offline, or the rover is behind — the file stays committed locally
and is retried. It must not be left uncommitted for the backup cron to find, because
that reintroduces exactly the sweep this avoids. If the rover is behind origin, rebase
before retrying rather than force-pushing.

### 1.2 The file carries its own provenance

The request file is the audit trail, so it records how it got there — not just what was
asked for:

```markdown
---
proposed:  2026-09-11T14:02Z
approved:  2026-09-11T18:40Z
channel:   email, DKIM verified, code a3f1
evidence:  17 STALL_FAULT events, left-middle wheel, 2026-09-04 to 2026-09-11
status:    approved
---
```

Without this, a queue entry is indistinguishable from something a person typed, and
"the owner agreed to this" becomes an unverifiable claim months later. With it, anyone
picking the queue up can see it was machine-proposed, human-approved, and on what
evidence.

## 2. What Willie may and may not do

**He writes text. He never writes code.** This is the hard line. A feature request is a
`.md` file describing a problem and a proposed direction. Nothing in this subsystem
generates, edits or executes Python, and nothing in it changes `config.py`. Implementation
is a separate, human-initiated session.

**Requests must be grounded in observed data, not invented.** This is what makes the
feature worth having rather than a novelty. Willie has operational history nobody else
looks at systematically:

- repeated `STALL_FAULT`s, with which wheel and how often
- voice commands that parsed to no intent, and what was actually said
- tasks that started and failed — retrieval, navigation, pursuit — with the failure reason
- faults that recur across boots
- `TICK_OVERRUN` counts

A request cites the evidence: event counts, dates, log references. A request that cannot
cite anything is not sent. "Here is what keeps failing and a suggested direction" is
useful; "here is a cool idea" is noise, and the second kind is what will make the owner
stop reading them.

**Rate-limited to `FEATURE_REQUEST_MAX_PER_DAY` (default 1).** The failure mode of this
feature is an inbox nobody reads any more.

## 3. Which model composes it

**Claude, not the on-device LLM.** FRD G-6 records the Hailo LLM scoring 0% on a 32-case
intent batch, and it has not been re-benchmarked. Composing a coherent feature request is
harder than parsing an intent, not easier.

This is the right task for the cloud path: it is asynchronous, off the tick thread, not
latency-sensitive, and quality matters more than speed — the opposite of the profile that
made on-device primary for STUCK reasoning. It also runs at most once a day.

If `ENABLE_CLOUD_AI` is off or the network is down, the request is deferred, not composed
locally.

## 4. Approval, and what an unapproved request does

Approval rides on the FR-2000-012/013 machinery: one-time code, allowlisted sender, and
the `Authentication-Results` DKIM check. A reply that fails any of those is surfaced but
does not approve.

**Unapproved requests never reach the repo.** They live in a local pending file and expire.
This matters: the repo queue is a list of things the owner has actually agreed to, so a
development session can treat it as intent rather than as suggestions to be triaged. An
expired or ignored request leaves no trace in git.

**Approval is not a specification.** An approved request is a starting point for a design
conversation, not an instruction to start typing. Anything non-trivial still goes through
the normal brainstorm → spec → plan route. The queue records *what the owner agreed was
worth doing*, not *how*.

## 5. Injection boundary

The observations feeding a request can originate outside the rover — email bodies, spoken
input, text seen by the camera. So a request is **untrusted content that the owner reads**,
and it must be treated as such:

- FR-2000-006's rule stands: email bodies reaching any model go through
  `build_summary_prompt()`'s untrusted-data wrapper. Feature-request composition is not an
  exemption.
- The request email states plainly that it was machine-generated from observed events, so
  the owner reads it as a proposal rather than as a message from a person.
- The owner's approval, and a human implementation session, are the two gates. Neither is
  optional, and the second is what makes the first safe: an approved-but-bad request
  produces a conversation, not a commit.

## 6. Files

| Path | Purpose |
|---|---|
| `docs/feature-requests/` | The queue. One `.md` per approved request |
| `feature_requests.py` | Observes, composes, emails, writes the approved file |
| `secrets/pending_feature_request.json` | Local pending state and one-time code. Not in git |

`feature_requests.py` runs on its own low-frequency timer, never on the tick thread. It
touches no hardware and is fully unit-testable off-rover — the observation source is the
existing event log, so the tests feed it synthetic history and assert on what it proposes.

## 7. Out of scope

Willie writing code, editing config, opening pull requests, or committing anything other
than a request file. Self-modification of any kind. Requests to anyone but the owner —
FR-2000-009's single hard-coded outbound recipient already prevents it.
