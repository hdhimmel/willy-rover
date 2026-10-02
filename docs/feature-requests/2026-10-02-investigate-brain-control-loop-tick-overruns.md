---
proposed:  2026-10-02T17:01Z
approved:  2026-10-02T18:17Z
channel:   email, DKIM verified, code 54f3
evidence:  288 x control-loop tick overruns, 2026-10-01 to 2026-10-02
status:    done
---

# Investigate brain control-loop tick overruns

## Problem

Between 2026-10-01 and 2026-10-02, I logged 288 control-loop tick overruns in the brain subsystem. Example ticks took 617 ms, 557 ms, and 554 ms against a 150 ms threshold, meaning they ran roughly 3.5 to 4 times over budget. This could delay my responses and make my movements less reliable.

## Suggested direction

Please add finer-grained timing inside the brain tick so I can report which step is consuming the time. It would also help to let me shed or defer lower-priority work when a tick runs long, and to record what else was running during each overrun. If you can share any recent changes to my software or workload around 2026-10-01, that would help narrow down the cause.

## Evidence

- `EVENT=TICK_OVERRUN subsystem=brain duration_ms=617 threshold_ms=150`
- `EVENT=TICK_OVERRUN subsystem=brain duration_ms=557 threshold_ms=150`
- `EVENT=TICK_OVERRUN subsystem=brain duration_ms=554 threshold_ms=150`

*Machine-proposed by Willie from his own logs and approved by the owner by email. Approval is not a specification: anything non-trivial goes through design before implementation.*

## Resolution (2026-10-02)

The evidence pointed straight at it: the overruns cluster at 501-506 ms, which is the
`time.sleep(0.5)` in `brain._self_test()`, re-run on the tick thread every `SELFTEST_RETRY_S`
(30 s) while the self-test was failing with the base off. The sleep now runs once, at startup.
