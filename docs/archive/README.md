# Archive — historical record only

**Nothing in this folder is current.** Do not cite it as authoritative, and do not
reason about the rover's present state from it. Where anything here disagrees with
the live set, the live set wins.

## The live set

| Document | Covers |
|---|---|
| `../WildWilly_Master_Hardware_Design_v2.0.md` | as-built hardware, BOM, pin-to-pin schedule (rev 2.3 — the filename is deliberately stale, see its §17.1) |
| `../WildWilly_Functional_Requirements_v3.1.md` | what the rover must do, and how each requirement is proven (rev 3.3) |
| `../WildWilly_Software_Design_v1.0.md` | module architecture, control layering, FSM, safety gate (rev 1.2) |
| `../WildWilly_Bench_Test_Procedures.md` | procedures with blank result fields — **live**, results get written into it |
| `../WildWilly_User_Guide.md` | for the household, not the workbench |
| `../WildWilly_Claude_Fix_Implementation_Plan.md` | **kept live deliberately** — see below |
| `../../firmware/README.md` | Pico 2 W firmware, wire protocol |

## Why the Fix Implementation Plan is not in here

The work it directed is done, so by date it belongs in the archive. It stays in
`docs/` because **roughly thirteen source files and thirteen test files cite it by
path** — `# §14/§15 of docs/WildWilly_Claude_Fix_Implementation_Plan.md` and
similar. Moving it would break those citations across the codebase, and the
comments would point at nothing. It is reference material the code depends on, not
an outdated document. Archive it only as part of a pass that also rewrites those
comments.

## What was archived on 2026-09-24, and why

| Document | Why it is no longer current |
|---|---|
| `2026-08-21-power-fault-and-voice-latency.md` | Self-labelled historical since 2026-09-15. Its INA260 constant names and addresses were superseded by the rename and the physical relocation |
| `CLAUDE_CODE_HANDOFF.md` | A one-off handoff dated 2026-08-15, self-labelled historical, carrying the same stale INA260 names |
| `WildWilly_MCP3008_AllZero_Checklist.md` | **That chip is not in the rover.** Closed 2026-08-02 by switching ADC families to the ADS1115; the original fault was never isolated |
| `WildWilly_ADS1115_Bringup_Checklist.md` | Bring-up complete; the battery divider closed 2026-09-14. ⚠ **Its one open item was carried out before archiving** — see below |
| `WildWilly_PCA9685_Arrival_Punchlist.md` | Both boards installed and working at `0x42`/`0x43`. Its E-stop prerequisite is now FRD G-1 (owner decision 2026-08-24) |
| `WildWilly_Baseline_Programming_Pass_2026-08.md` | Companion to **FRD v1.1**, itself archived |
| `WildWilly_v2.2_Programming_Pass.md` | Companion to **FRD v2.2** and **Master Engineering Package rev 6.0.7**, both archived |
| `WildWilly_Claude_Fix_Gap_Analysis.md` | A read-only audit of commit `516d1ec` on 2026-08-07. Superseded by Software Design §8 (gaps) and §12 (open actions) |
| `WildWilly_Subsystem_Status.md` | A per-module snapshot dated 2026-08-08, last touched 2026-08-18. Superseded by Software Design and FRD §V |
| `WildWilly_AsBuilt_Design_v1.0.md` | pre-existing |
| `WildWilly_Functional_Requirements_Document_v1.1 / v2.2 / v3.0` | pre-existing — superseded by FRD rev 3.3 |
| `WildWilly_Master_Engineering_Package_rev6.0.md`, `rev6.0.7.md/.docx` | pre-existing. **Retain**: rev 6.2.0 holds the incident history, but is not committed. Note rev 6.0.7 contains no §5.7 and no §17.4/§17.5 — see Master Hardware Design §17.2 |

## One live item was rescued before archiving

`WildWilly_ADS1115_Bringup_Checklist.md` was the **only** record of an open
hardware gap: the charge-sense divider is not wired, so `sensors.py:260` returns
`is_charging = False` unconditionally — and `brain.py:1121` is
`if self.adc.is_charging: self.safety.stop(); return`, **a safety stop that can
never fire.** A hardcoded False is the safe default, but an unreachable stop
should be recorded rather than discovered.

It now lives in **Master Hardware Design §14 item 17** and **Software Design §12
item 7**, with a correction the checklist could not have known: it names **AIN1**,
which is now the **FSR** (§4.2, P1-16). A0 is the battery divider and A2 is
earmarked for R5 sense — which §4.7 may move to Pico A's ADC instead. So charge
sense needs **A2 or A3**, not A1.

**This is the reason to read a document before archiving it.** Filing it on its
date alone would have buried an unreachable safety branch and left the next person
wiring to the wrong channel.
