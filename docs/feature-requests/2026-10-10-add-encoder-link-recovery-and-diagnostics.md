---
proposed:  2026-10-09T13:57Z
approved:  2026-10-10T09:27Z
channel:   owner in a Claude Code session 2026-10-10 (narrowed: fault context only, no link watchdog), code 2938
evidence:  23 x ENCODERS_FAULT on encoders, 2026-10-07 to 2026-10-09
status:    approved
---

# Add encoder link recovery and diagnostics

## Problem

Between 2026-10-07 and 2026-10-09, I logged 23 ENCODERS_FAULT events on the encoders subsystem. Each one reported no fresh $E frame from Pico A, where I expect $E frames within 0.2s. Without wheel encoder data, I can't reliably track my movement.

## Suggested direction

Please consider adding a watchdog that detects a stalled Pico A link and automatically retries or resets the serial connection. It could also record more detail when a fault happens, such as the time since the last good frame, link status, and power state, so the root cause (cable, power, or firmware) can be found. While the encoders are faulted, I should slow down or stop and tell you, instead of continuing to move without feedback.

## Evidence

- `EVENT=ENCODERS_FAULT subsystem=encoders status=fault value=no fresh $E frame from Pico A expected=$E frames within 0.2s`

*Machine-proposed by Willie from his own logs and approved by the owner by email. Approval is not a specification: anything non-trivial goes through design before implementation.*
