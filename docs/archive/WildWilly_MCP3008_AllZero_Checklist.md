# WildWilly — MCP3008 All-Channels-Zero Checklist
*Execute in order. Spare chip installed, raw SPI probe (bypassing sensors.py) shows CH0–CH7 all reading 0 — this is no longer a CH7-only symptom, so don't re-check CH7 in isolation before ruling out the whole-chip causes below.*

Context: the original CH7 fault (§8.4 master doc) was CH7 wired directly to +12V with no divider — an over-voltage the chip's clamp diodes absorbed, giving a near-full-scale raw reading (1016/1023), not a zero. A 10kΩ/~3.2kΩ divider was added 2026-07-27 to fix that. Today's symptom (flat 0 across all 8 channels, on a fresh chip) is a different failure mode — points at power, bus wiring, or Pi-side SPI, not a channel-specific over-voltage repeat.

## CORRECTION (2026-08-01, this session): chip pin numbering was wrong

Earlier entries in this doc refer to "VDD (chip pin 1)". **That's incorrect.** Per the MCP3008 datasheet (16-pin DIP, pin 1 at the notch, counterclockwise): pin 1 is **CH0**, not VDD. Verified correct pinout:

| Pin | Signal | Pin | Signal |
|---|---|---|---|
| 1 | CH0 | 9 | DGND |
| 2 | CH1 | 10 | CS/SHDN |
| 3 | CH2 | 11 | DIN (MOSI) |
| 4 | CH3 | 12 | DOUT (MISO) |
| 5 | CH4 | 13 | CLK |
| 6 | CH5 | 14 | AGND |
| 7 | CH6 | 15 | VREF |
| 8 | CH7 | 16 | **VDD** |

The SPI pin numbers already used throughout this doc (10/11/12/13 = CS/DIN/DOUT/CLK) are correct and unaffected. But **every prior reference to "VDD = chip pin 1" is wrong — VDD is chip pin 16.** This means the "VDD (chip pin 1) to DGND measured 11.42V, chip destroyed" finding earlier in this doc was almost certainly measuring **CH0**, not VDD — that diagnosis needs to be re-verified against the real VDD pin (16) before being trusted. It's plausible a chip was lost to 12V-on-CH0 rather than 12V-on-VDD, which is a different (though similarly serious) miswire to chase down.

User reports (this session) that chip pin 1 is not connected to anything — consistent with CH0 simply being an unused analog input, and **not evidence of a power problem**. The actual open question is still whether chip pin 16 (VDD) has a clean 3.3V connection.

## Wire color legend (this harness)
- Pin 10 (CS/CE0) — **blue**
- Pin 11 (DIN/MOSI) — **green**
- Pin 12 (DOUT/MISO) — **yellow**
- Pin 13 (CLK) — **orange**
- VDD (pin 16), VREF (pin 15), AGND (pin 14), DGND (pin 9) — not yet assigned colors, refer to by name until confirmed.

## 0. Don't reflexively blame the new chip again
- [ ] Because the last incident's overvoltage was on a line that fed straight back toward the Pi's SPI0 peripheral (GP8/9/10/11 — CE0/MISO/MOSI/SCLK, physical pins 24/21/19/23), rule out Pi-side SPI damage before condemning a second chip. If the Pi's SPI0 controller was stressed, a second known-good chip would also read all zero — which is exactly what's happening.

## 1. Confirm the OS actually sees the bus
- [x] `ls /dev/spidev*` — 2026-08-01: lists `/dev/spidev0.0` and `/dev/spidev0.1`. SPI0 is enabled and visible to the OS — ruled out as the cause.
- [x] `dmesg | grep -i spi` — 2026-08-01: no matches. dmesg itself is readable (confirmed via `dmesg | head`), so the empty result is a genuine clean boot log, not a permissions artifact. No SPI driver errors/warnings — ruled out as the cause.

## 2. Power to the chip, meter in hand
- [ ] VDD pin (chip power) to DGND: should read ~3.3V.
- [ ] VREF pin to AGND: should read ~3.3V. A floating or grounded VREF alone produces exactly this symptom — full-scale-relative-to-zero, i.e. every channel reads 0.
- [ ] AGND and DGND both actually tied to the Pi's ground (control-tray bus per the star-of-stars grounding rule, §5.5) — not floating, not tied only to each other.

## 3. Physical SPI wiring, chip to Pi (§17.1 pin map)
- [ ] CS/CE0 — chip pin 10 → Pi physical pin 24 (GP8).
- [ ] CLK — chip pin 13 → Pi physical pin 23 (GP11).
- [ ] DIN (chip's MOSI in) — chip pin 11 → Pi physical pin 19 (GP10).
- [ ] DOUT (chip's MISO out) — chip pin 12 → Pi physical pin 21 (GP9).
- [ ] Verify DIN/DOUT aren't swapped — this is the single most common MCP3008 wiring mistake and produces exactly "reads but always 0" rather than a bus error.
- [ ] Reseat/verify the new chip is fully socketed and oriented correctly (pin 1 / notch orientation) on the EPLZON.

## 4. Isolate chip vs. bus vs. Pi
- [ ] Probe a channel tied to a **known** voltage — e.g. jumper CH0 directly to the chip's own 3.3V VDD pin. Raw should read ~1023. If it still reads 0, the fault is upstream of the chip (bus/Pi/power), not the chip or any sensor wiring.
- [ ] If CH0-to-VDD reads correctly but CH7 doesn't, the fault is isolated to the CH7 divider (§8.4) — check the 10kΩ/4.7kΩ∥10kΩ divider for a bad joint or a short to ground, since that circuit is unique to CH7 and untouched by this chip swap.
- [ ] If available, swap CE0 for CE1 (`spi.open(0, 1)` + a jumper to physical pin 26 GP7) as a cheap test of whether GP8/CE0 specifically is the dead line on the Pi side.

## 5. If every check above passes and it's still all zero
- [ ] Suspect Pi SPI0 peripheral damage from the original over-voltage event (§0 above). Next step would be testing the MCP3008 on a different Pi (or a USB-SPI bridge) to confirm the chip itself is good — don't keep swapping MCP3008 chips against a possibly-damaged Pi.
- [ ] Log the exact result of each step here (meter readings, which step first failed) back into the master engineering package per the project's standing rule — don't leave this as tribal knowledge for the next session.

## Session log — 2026-08-01

- User reports finding chip-pin-13 (CLK) vs chip-pin-12 (DOUT/MISO) confused during wiring/continuity work — i.e. an earlier "MISO continuity passed" check may have actually probed CLK, not true MISO. **Not independently verified in this session** — no meter readings were logged before this entry, so treat as reported-but-unconfirmed until continuity is re-run and recorded here.
- Wiring was corrected per the user's report; system was repowered.
- Ran `mcp_probe_all.py` (raw 8-channel probe, bypasses `sensors.py`) post-fix: **CH0–CH7 all read 0** — unchanged from the original all-zero symptom. The wiring correction alone did not resolve it (or wasn't the actual/only fault).
- Step 1 (`ls /dev/spidev*`) confirmed PASS this session — `/dev/spidev0.0` and `0.1` both present. Bus enablement ruled out.
- **Not yet done, first steps for next session:**
  - [ ] §2 meter check: VDD pin → DGND (expect ~3.3V), VREF → AGND (expect ~3.3V). A floating/grounded VREF alone reproduces this exact all-zero-on-every-channel symptom, independent of the SPI data lines.
  - [ ] §3 four-line continuity check (CS/CLK/MOSI/MISO, chip pin → Pi physical pin, per the table in §3 above) — confirm each line reads continuity to its correct Pi pin *and* no continuity to any of the other three SPI pins. This is the check that would actually confirm or rule out the reported pin-12/13 mixup.
  - [ ] §4 isolation test: jumper CH0 directly to the chip's own VDD pin, rerun `mcp_probe_all.py`. CH0 should read ~1023. If it's still 0, the fault is upstream of the chip (bus/Pi/power), not the chip or the SPI data-line wiring.

## Session log — 2026-08-01 (cont.)

- Re-ran `dmesg | grep -i spi`: no output. Verified this isn't a permissions issue (dmesg | head returns normal boot log). §1 now fully PASS — bus enablement and driver-level errors both ruled out.
- Re-ran `mcp_probe_all.py`: **CH0–CH7 still all read 0** — unchanged since the last run in this session. Confirms the fault is persistent, not intermittent.
- With §1 fully cleared, the fault surface is now narrowed to §2 (power/VREF), §3 (physical continuity — esp. the reported CLK/MISO pin-12/13 mixup, still unconfirmed), or §4 (chip vs. bus isolation). All three require a multimeter and hands-on wiring access, which is not something that can be done from this session — next session should carry a meter to the rig and work §2 → §3 → §4 in order, logging each reading here.
- Re-ran `mcp_probe_all.py` again (later in session, no wiring/power changes made in between): **CH0–CH7 still all read 0**, third consecutive identical result. Nothing to add beyond confirming persistence — still blocked on §2/§3 meter work.
- Also worked on nailing down §3's Nano HAT Hacker pin labels precisely: the board prints BCM numbers on one side and descriptive labels on the other, but the exact descriptive text (full words like "MISO" vs. 2-letter codes like "MI") could not be confirmed from Pimoroni/Adafruit product pages — user confirmed the board uses 2-letter abbreviations. Best-guess mapping (CE0→CE, MOSI→MO, MISO→MI, SCLK→CK) offered as a hypothesis only, **not yet confirmed against the physical board**. Next session: read or photograph the labels at physical pins 19/21/23/24 and record the actual text here before trusting them for the §3 continuity check.
- **Symptom changed** — next `mcp_probe_all.py` run (same session, no meter checks logged in between — unclear from chat alone whether wiring was touched): **CH0–CH7 all read 1023** (full-scale), a flip from the prior all-0 result. All-channels-max rather than a real per-channel signal points to DOUT/MISO floating high — most consistent with CS/CE0 not actually reaching the chip (chip never selected, never drives the bus, Pi reads the floating line as all-1s) or DOUT physically off chip pin 12. This is a different failure signature from the original all-zero fault and should be chased as such, not folded back into the all-zero theory. **Needs confirmation from the user on what physically changed** before the next diagnostic step is chosen.
- User confirmed all sensor leads are physically connected (rules out the floating-analog-input explanation for all-1023). Also confirmed the new symptom is not a MOSI/MISO reversal: GPIO9/MISO has a default internal pull-DOWN on the Pi, so a swapped/disconnected MISO settles low (matches the *original* all-zero fault) — it does not explain a flip to all-1023, which requires something actively driving/pulling the line high.
- Two real candidates remain, both needing a meter (not yet done):
  - [ ] Continuity check: MISO (physical pin 21 / chip pin 12) to the 3.3V rail — should be open; continuity = a short to VDD.
  - [ ] CS/CE0 (physical pin 24 / chip pin 10) idle voltage, with no probe script running — should sit at 3.3V (deselected). Stuck at 0V means the chip is permanently selected.
- User measured MISO and MOSI voltage at **0.77V each**, believed (not fully certain) to be at idle, i.e. `mcp_probe_all.py` not running. Both lines converging on the same non-zero, non-rail voltage at idle is itself the anomaly — rules out "meter just averaging a toggling signal" (that only applies if the script were actively running) and points to either a direct MISO–MOSI short or both lines leaking to some other partial-voltage source via a bad joint.
- [ ] **Next (power off first):** resistance/continuity check MISO (chip pin 12 / phys. pin 21) directly to MOSI (chip pin 11 / phys. pin 19) — should be open. If not open, check each line separately to GND and 3.3V to localize the leak.
- Re-ran `mcp_probe_all.py`: **CH0–CH7 back to all 0**, flipped again from the all-1023 result logged just above. No meter checks (MISO/MOSI continuity) were logged between the two runs, so it's unclear from chat alone whether wiring was touched in between — **needs confirmation from the user on what physically changed**. The fact that the symptom is toggling between all-0 and all-1023 across runs, with no confirmed intervening change, points toward an intermittent short/open (a loose joint or marginal connection) rather than a fixed fault — this favors physically re-seating and continuity-checking every SPI joint (§3, plus the MISO–MOSI short check above) over further passive voltage measurement.
- **Blue (CS/CE0, chip pin 10) idle voltage measured: 3.3V** — PASS. Chip is properly deselected at idle, not stuck low. Rules out "chip permanently selected" as the explanation for either the all-0 or all-1023 symptom. Still outstanding: yellow(MISO)↔green(MOSI) short check, VDD→DGND, VREF→AGND.
- **Yellow (MISO, chip pin 12): 0.5V to GND, 0.63V to 3.3V rail.** These don't sum to ~3.3V (only ~1.13V total) — power state (on/off, script running?) not confirmed by user. Rules out a hard short to either GND or the 3.3V rail (neither reading is near 0 or matches a clean short); reading is consistent with a floating/undriven line.
- **Green (MOSI, chip pin 11): 0.84V to GND, 0.76V to 3.3V rail.** Same pattern as yellow — sums to only ~1.6V, not ~3.3V. Both data lines floating at indeterminate mid-range voltages rather than cleanly shorted. This points away from a MISO/MOSI wiring short and toward the chip not actively driving either line at all — i.e. the chip may be unpowered, not selected, or not seated, independent of the CS/CE0 idle-voltage pass above.
- **3.3V rail to GND measured directly: 3.3V** — PASS. Rail itself is healthy, ruling out rail sag as the explanation for the yellow/green readings above; the floating mid-range voltages on MISO/MOSI are a real symptom, not a measurement artifact of a weak rail.
- **CRITICAL — VDD (chip pin 1) to DGND measured: 11.42V.** Expected ~3.3V. This is essentially the 12V supply rail, not 3.3V logic — a chip-power miswire, the same failure class as the original CH7-to-+12V incident (§8.4) but on VDD instead of a signal channel. MCP3008 absolute max VDD rating is ~6.5V, so the chip has almost certainly been destroyed by this overvoltage. User instructed to power down immediately, disconnect the VDD wire, and NOT reapply power to this chip. This is very likely the second chip lost to a 12V miswire on this project.
- **Retroactive explanation for earlier symptoms:** a chip destroyed by VDD overvoltage would not drive MISO/MOSI to clean logic levels, consistent with the floating mid-range voltages measured on yellow/green above, and could produce erratic/non-deterministic all-0 vs. all-1023 flips via damaged internal circuitry rather than one consistent fault.
- **Outstanding, next session (power off, chip disconnected):**
  - [ ] Trace the VDD wire (currently reading 11.42V) back to its actual source — confirm whether it lands on the 12V rail (bad crimp/terminal/bus mixup) rather than the Pi's 3.3V pin, and fix the wiring/labeling error before connecting any new chip.
  - [ ] After removing this chip's VDD wire from the Pi's 3.3V pin (if that's what it was landed on), re-verify the Pi's 3.3V rail-to-GND is still a clean 3.3V with no sag, to rule out damage to the Pi's own 3.3V regulator/GPIO from backfeed.
  - [ ] Do not power a chip through this VDD wiring again until the miswire is found and fixed — treat the current chip as dead, replace with a fresh one only after wiring is confirmed correct.

## Session log — 2026-08-01 (cont. 2)

- User reports the VDD miswire has been fixed and a fresh MCP3008 is installed. Ran `mcp_probe_all.py`: **CH0–CH7 all read 0 again**, on the new chip post-fix.
- Note: the "trace VDD back to source" and "re-verify 3.3V rail after removing bad wire" steps from the previous entry were not explicitly confirmed with meter readings in this session — only reported as fixed. Given this project's history of two chips lost to 12V miswires, **do not skip re-confirming VDD-to-DGND reads ~3.3V (not 12V) before further probing**, since an all-zero result on a fresh chip is consistent with either a genuine remaining fault (§2/§3/§4) or a still-bad VDD line about to damage this third chip too.
- Next step: before anything else, meter VDD (chip pin 1) to DGND on the *new* chip and confirm ~3.3V. Only after that reads clean should §2 (VREF) and §3 (continuity) be worked in order.
- **Finding: VDD (chip pin 1) on the new chip is not connected to anything** — fully floating, not tied to 12V, 3.3V, or anything else. This alone fully explains the all-zero read on the new chip (an unpowered chip cannot respond over SPI) — no need to suspect VREF, continuity, or the chip itself yet.
- Likely cause: after the previous chip's VDD wire was disconnected from the 12V miswire per instruction, it was never reconnected to a proper 3.3V source when the new chip was installed.
- **Next step (not yet done):** meter the Pi's 3.3V pin (physical pin 1 or 17) to GND first to confirm a clean 3.3V source, then connect chip pin 1 (VDD) to that pin — explicitly not the 12V rail. After connecting, re-meter VDD (chip pin 1) → DGND in place to confirm ~3.3V before rerunning `mcp_probe_all.py`.

## Session log — 2026-08-02

- Clarification from user: chip pin 1 was **never physically connected to anything**, at any point — the "chip pin 1 (VDD)" wording in the entries above was leftover terminology confusion from a tired session (see the CORRECTION note at the top of this doc), not a real wiring attempt on the wrong pin. No physical miswire occurred here.
- Practical implication: the real VDD (chip pin 16) has still never been wired to 3.3V on the current chip. This alone fully explains every all-zero read logged so far on this chip — nothing else needs to be suspected yet.
- Re-ran `mcp_probe_all.py`: **CH0–CH7 all read 0**, consistent with VDD still unpowered.
- **Next step (not yet done):** meter the Pi's 3.3V pin (physical pin 1 or 17) to GND to confirm a clean 3.3V source, then run a wire from there to **chip pin 16 (VDD)** — the far end from the notch, not pin 1. After connecting, meter chip pin 16 → DGND in place to confirm ~3.3V before rerunning `mcp_probe_all.py`.
- **Chip pin 9 (DGND) to GND: 0V** — PASS. Confirms DGND is genuinely tied to ground, not floating.
- **User confirms both DGND and AGND are tied to the 3.3V ground rail** — closes the §2 checklist item ("AGND and DGND both actually tied to the Pi's ground... not floating, not tied only to each other"). PASS.
- **Chip pin 8 (CH7) reads ~4V** — reference lead and load state (is whatever drives CH7 currently connected?) not yet confirmed; not logging as pass/fail until that's nailed down. Worth revisiting given CH7's history (§8.4 divider added 2026-07-27 for the original +12V-direct miswire) — 4V would be above the ~3.3V VREF ceiling if this is CH7-to-GND with the original source still attached.
- **VREF (chip pin 15) to AGND: 3.29V** — PASS.
- **VDD (chip pin 16) to DGND: 3.29V** — PASS. VDD is now actually wired and powered on the current chip (previously found floating/never connected). §2 is now fully cleared: VDD, VREF, and AGND/DGND ground-tie all pass.
- **Next step:** rerun `mcp_probe_all.py` now that VDD is genuinely powered for the first time on this chip — the prior all-zero reads occurred while VDD was floating, so this is a real test, not a repeat.
- Re-ran `mcp_probe_all.py`: **CH0–CH7 still all read 0**, even with VDD/VREF/ground all now confirmed good. This is a real, meaningful all-zero result (first one with power genuinely present) and **fully rules out §2 (power)** as the cause. Fault surface is now narrowed to §3 (physical SPI wiring continuity — CS/CLK/DIN/DOUT, chip pin → Pi physical pin, including the previously-reported and still-unconfirmed CLK/MISO pin-12/13 mixup) or §4 (chip vs. bus isolation test — jumper CH0 to VDD, expect ~1023).
- **Next step:** work §3's continuity check (each of CS pin10→phys24, CLK pin13→phys23, DIN pin11→phys19, DOUT pin12→phys21 — confirm continuity to the correct Pi pin and no continuity to the other three), then §4's CH0-to-VDD isolation jumper test if §3 passes clean.
- User reports "pins all checked" (§3 continuity) but did not specify per-line pass/fail results or whether the previously-suspected CLK/MISO (pin 13/12) mixup was specifically ruled out — **treat §3 as attempted but not confirmed clean** until per-line results are recorded here.
- Re-ran `mcp_probe_all.py`: **CH0–CH7 still all read 0.**
- With §2 (power) fully cleared and §3 reportedly checked (though not itemized), the next diagnostic step is §4: jumper CH0 (chip pin 1) directly to the chip's own VDD pin (chip pin 16) and rerun the probe — CH0 should read ~1023 if the chip is alive and the bus/CS/CLK/DIN path is working. A continued 0 here would point the fault upstream (bus/Pi-side SPI, possibly the Pi's SPI0 peripheral per §0) rather than at per-channel wiring.

## Session log — 2026-08-02 (cont.)

- Re-ran `mcp_probe_all.py`: **CH0–CH7 still all read 0** — no wiring/power changes reported since the last run above; result unchanged. §4 (CH0-to-VDD isolation jumper test) has still not been performed.
- **Next step (unchanged):** jumper CH0 (chip pin 1) directly to VDD (chip pin 16) and rerun the probe — CH0 should read ~1023 if the chip and bus/CS/CLK/DIN path are alive. Still 0 would point the fault upstream of per-channel wiring.
- Re-ran `mcp_probe_all.py` again: **CH0–CH7 still all read 0**, no wiring changes made since the last run above. Began working §3's per-line continuity check properly this session (previous "pins all checked" report was never itemized) — starting with CS/CE0 (chip pin 10 → phys pin 24 / GP8), but no meter readings have been taken yet.
- **User reports §3 wiring all confirmed** (per-line results still not itemized in chat, same caveat as the earlier "pins all checked" report — take as passed but without a recorded per-line breakdown).
- **Decision: abandon this MCP3008 unit, replace with an ADS1115** — a different ADC chip entirely (I²C, not SPI). User is waiting on the part to arrive; no further MCP3008/SPI diagnostic work (§4 isolation test, etc.) planned. This closes out this checklist as superseded rather than resolved — the root cause (chip vs. Pi SPI0 vs. an unconfirmed wiring fault) was never conclusively isolated.
- **Implication for next session:** the ADS1115 uses I²C, so it joins the existing 9-device I²C bus/pull-up fan-out (§17.2 master doc) via SDA/SCL rather than needing the SPI0 pins (phys 19/21/23/24, currently freed by this swap). Standard 4.7kΩ pull-ups already on that bus should suffice — check ADS1115 address pin (ADDR) strapping against the other 8 devices' addresses to avoid a bus conflict before wiring in. Will need a fresh probe script (I²C-based, not `mcp_probe_all.py`'s raw SPI read) once the part is in hand.
- Re-ran `mcp_probe_all.py` once more after a software update on the Pi: **CH0–CH7 still all read 0**, unchanged. Consistent with the decision above — not chasing this further; final confirmation before the ADS1115 swap. Session ended here (rig shutting down).

## Session log — 2026-08-02 (cont. 2) — CLOSED, superseded by ADS1115

- ADS1115 physically installed and wired to the existing I²C bus. Bench probe (`ads1115_probe.py`, new I²C-based script replacing `mcp_probe_all.py` for this role) confirms the chip enumerates at 0x48 (`i2cdetect -y 1`) — no conflict with the other 9 devices on the bus (0x27, 0x40, 0x42–0x45, 0x4A, 0x60, 0x61, 0x70).
- AIN0 (battery divider) reads a real, stable, proportional value (raw ~26200/32768, 3.28V through the ±4.096V PGA range) — chip and one ADC channel confirmed working. AIN1–3 read a uniform ~1.04–1.05V, consistent with expected floating-pin crosstalk (only AIN0 is wired so far; AIN1–3 intentionally unconnected).
- This fully closes out the MCP3008/SPI0 investigation — no further diagnostic time being spent on it. See `WildWilly_ADS1115_Bringup_Checklist.md` for the new chip's bring-up tracking (calibration, charge-sense wiring).
