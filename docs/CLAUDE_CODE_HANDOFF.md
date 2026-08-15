# Handoff to Claude Code on Willie — 2026-08-15

Paste this into a Claude Code session on the Pi. It contains a code review
finding, a design concern, and instructions for committing updated
documentation.

---

## 1. Bug to fix now — `diagnostics.py`

`diagnostics.py` line 13 includes `0x70` in `_EXPECTED_I2C`. `brain.py`
line 40 correctly excludes it, and explains why in its own comment:
`PCA9685.reset()` clears MODE1's ALLCALL bit during `motors.py` / `arm.py`
construction, which runs before the self-test, so `0x70` legitimately stops
answering by scan time.

Consequence: `diagnostics.py` reports `0x70` as MISSING — a false failure —
whenever it runs after the PCA9685s have been initialised. The two modules
disagree about the same fact.

Fix: remove `,0x70` from the set in `diagnostics.py` so both modules expect
the same ten real devices. Consider adding a short comment pointing at
`brain.py`'s explanation so it does not get re-added.

Verified correct on the bench 2026-08-13 — `i2cdetect -y 1` returns
`0x27 0x40 0x42 0x43 0x44 0x45 0x48 0x4A 0x60 0x61` plus `0x70` All-Call.
Ten real devices. `0x70` answers only while a PCA9685 still has ALLCALL set.

---

## 2. Design concern — encoder sample rate vs pulse rate

`config.py` sets `ENCODER_COUNTS_PER_REV=3292` (823.1 PPR × 4). At the
620 RPM no-load figure that is roughly **8.5 kHz per channel**.
`sensors.py` polls the MCP23017 over I²C at what its own comment calls a
~1 kHz practical ceiling.

That under-samples by about an order of magnitude. Consequences: odometry
distance reads low, and stall detection becomes unreliable at speed —
which matters because stall detection is FR-000 Directive 5.

Both `ENCODER_COUNTS_PER_REV` and the 620 RPM figure are marked unconfirmed
in `config.py`, taken from the motor listing rather than the bench. **Confirm
the real counts/rev first** — rotate a wheel a known number of turns and read
the raw count — before deciding on any of:

- interrupt-driven decode
- a dedicated hardware counter
- accepting encoders as stall-detection only and deriving distance elsewhere

Also unconfirmed and feeding odometry: `WHEEL_DIAMETER_M=0.065` and
`TRACK_WIDTH_M=0.28`.

---

## 3. Confirmed correct — no action needed

Checked against the as-built hardware and matching:

- `INA260_PI_ADDR=0x44` — confirmed by scan; `0x46` does not answer
- `MOTOR_PORT` — lf/lm/lr on `0x60`, rf/rm/rr on `0x61`, one board per side
- `ARM_SHOULDER_A=1`, `ARM_SHOULDER_B=2` — CH1/CH2 correct
- Sonar pins — front 5/26, left 13/14, right 4/21
- `ENCODER_PINS` — lf A0/1, lm A2/3, lr B0/1, rf A4/5, rm A6/7, rr B2/3
- Steering channels — LF 0, RF 1, LM 2, RM 3, LR 4, RR 5

Where the engineering documents disagreed with the code on motor mapping or
shoulder channels, **the code was right** and the documents have been
corrected.

---

## 4. Documentation to commit

Two documents have been rewritten and should replace what is in `docs/`:

- **WildWilly As-Built Design v1.0** — current configuration only. Includes
  the BOM (§15) and the complete per-device pin-to-pin schedule (§16).
- **WildWilly Functional Requirements Document v3.0** — all 113 requirement
  IDs retained unchanged; every Acceptance Criteria section now filled; new
  verification status register.

Also worth adding at the repo root: a `CLAUDE.md` carrying the hardware facts
and standing constraints, so future sessions start with them.

Suggested commit message:

```
docs: as-built design v1.0 and FRD v3.0

Replaces the rev 6.x engineering package as the working reference.
As-built carries current configuration only, with BOM and full
pin-to-pin schedule. FRD v3.0 fills every acceptance criteria
section; no requirement text changed.
```

Older documents in `docs/` (rev 6.0, rev 6.0.7, the MCP3008 checklist, the
PCA9685 punchlist) describe superseded states. Leave them if they are useful
history, but they should not be treated as current.

---

## 5. Hardware state as of 2026-08-15

- Build complete. All ten I²C devices enumerate through the isolator.
- Pi boots from battery: 5.144V, `vcgencmd get_throttled` = 0x0.
- Serial console disabled; GP14 and GP15 free for left sonar ECHO and
  BNO085 INT.
- Sonars connected but not yet range-tested. Encoders and IMU not yet
  live-verified. No motion testing has been done.
- Five of six motor crimps unverified against the colour scheme. Meter
  before first motion.
