# Combined EPLZON Board — rev 3.2

**Date:** 2026-08-28
**Supersedes:** rev 3.1, rev 3, `Bus_Node_Board_Layout_2026-08-09`,
`EPLZON_Sonar_Board_Layout_2026-08-09`, `Combined_EPLZON_Board_Layout_2026-08-09`

**Function:** I²C bus distribution (direct, no isolator) + 3.3V regulation +
sonar ECHO dividers. Replaces the AMS1117-3.3 that failed twice
(CLAUDE.md "Power", 2026-08-21 root cause).

## Changes from rev 3.1

| # | Change | Why |
|---|--------|-----|
| 1 | **C6 relocated** to the bottom section of cols 25/26 | Blocker: at c25d/c26d a 6.3mm electrolytic can overlapped both C1 (row c) and P2 (row e), 2.54mm away on each side. Rev 3.1's build note was circular — it proposed moving P2 into C6's own holes. |
| 2 | **LTC4311 moved cols 5–8 to cols 1–4** | At 5–8 the `c8e→SCL8` down-run passed directly over `c8j`, now J1's GND pin under a 3-pin JST body. Cols 1–4 are free top *and* bottom. |
| 3 | **Fuse 1A fast-blow to 1A slow-blow** | C6 (47µF) + C1 (10µF) inrush will nuisance-trip a fast-blow. |
| 4 | **J3 relabelled REAR to RIGHT** | `config.py:67` = `SONAR_RIGHT_TRIG/ECHO`; `config.py:262` bearing +90°. Master Hardware Design §8.1: *"There is no rear sonar."* The board doc was the only source calling it REAR. |
| 5 | **Pi low-Z return G13 to G12** | G12 was released by the rev 3.1 header fix and is a straight vertical run in column 12. |
| 6 | **220Ω TRIG resistors — dropped** | Not placeable: every TRIG column is flanked by its own GND and ECHO strips. The only route splits Pi GPIO pins across both board edges. TRIG is an HC-SR04 *input* and never back-drives; the protection is not worth the relayout. |
| 7 | **0.1µF HF decoupler added at V26/G26** | Last free +3.3V/GND rail pair in the circuit zone. Four DROK buck converters switch at 150–180kHz; C4/C5 are bulk and will not catch it. |
| 8 | **C2/C3 specified as 1210 SMD** | Through-hole 47µF ceramic at 2.54mm lead pitch is essentially unobtainable. |

## Board structure

EPLZON 3.5"×2.05" (88.9×52.1mm) gold-plated solderable breadboard.
30 columns × 0.1" pitch, 1.2mm holes, M3 corner mounts.

```
TOP RAILS      row 1: +3.3V   row 2: GND      (30 holes each, column-aligned)
rows a-e       5-hole tie-strips per column
CENTER GAP     breaks the column strips  (e / f)
rows f-j       5-hole tie-strips per column
BOTTOM RAILS   row 1: SDA     row 2: SCL      (30 holes each, column-aligned)
```

Within a column, `a-e` is one net and `f-j` is a separate net. Adjacent columns
are not connected. Rails are continuous across all 30 holes.

**Rules:** one lead per hole · components mount horizontally across strips ·
vertical runs are rail connections only.

**Zones:** rail cols **1–20** = bus (external device + Pi connections, all taps
interchangeable) · cols **21–30** = board circuitry.
*Exception: the LTC4311 (cols 1–4) is board-mounted inside the bus zone by
design — it is a bus accelerator and must sit on the bus, not on a drop cable.*

## Power block — TPSM84203EAB @ cols 25–28

Input 12V main bus via 1A slow-blow fuse. Datasheet: 4.5–28V in, 3.3V/1.5A
fixed, ~95% efficiency, 3-pin TO-220 (VIN/GND/VOUT). Independently corroborated
in CLAUDE.md — owner-confirmed as a direct drop-in for the AMS1117.

| Item | Holes | Notes |
|------|-------|-------|
| P2 PWR IN (JST-PH 2-pin) | GND `c25e` · 12V `c26e` | 2.0mm pitch — splay pins into 2.54mm holes |
| C1 Cin 10µF **50V** ceramic | `c25c` / `c26c` | 50V for DC-bias margin; a 25V part derates to ~4-5µF at 12V |
| TPSM84203EAB | VIN `c26b` · GND `c27b` · VOUT `c28b` | |
| C2 Cout1 47µF | `c27c` / `c28c` | 1210 SMD across the pads |
| C3 Cout2 47µF | `c27e` / `c28e` | 1210 SMD; 5.08mm clear of C2 |
| **C6 bulk 47µF/35V electrolytic** | **`c25g`(−) / `c26g`(+)** | **relocated — bottom section** |
| GND bridge (for C6) | `c25b` / `c25f` | carries GND across the gap |
| 12V bridge (for C6) | `c26d` / `c26f` | carries 12V across the gap |
| Rail jumpers | `c25a→G25` · `c27a→G27` · `c28a→V27` | |

Cout must be at least 94µF ceramic (2×47µF, TI spec). A single 10µF here will
oscillate. **Check the datasheet for Cout MAX before adding bulk directly on
VOUT** — C4/C5 are downstream on the rail and do not count against it.

`TPSM→V27` and `R1→V28` are each shifted one column left so the two diagonals
run parallel and never cross.

**DC-bias derating:** 2×47µF ceramic at 3.3V bias is roughly 50-65µF effective.
Use 16V or 25V parts rather than 6.3V to keep margin.

## Pull-ups + rail caps — cols 29–30

| Item | Holes |
|------|-------|
| R1 4.7k (SDA) | `c29b` / `c30b` · `c29a→V28` · `c30e→SDA30` |
| 3.3V bridge | `c29d` / `c29f` |
| R2 4.7k (SCL) | `c29h` / `c30h` · `c30j→SCL30` |
| C4 10µF/25V | `V29` / `G29` (vertical across rail rows) |
| C5 10µF/25V | `V30` / `G30` |
| **C7 0.1µF HF** | **`V26` / `G26`** |

col29 top and bottom form one 3.3V node via the bridge · col30 **top** = SDA ·
col30 **bottom** = SCL. The centre gap is what keeps SDA and SCL apart — see
Verification step 1.

**Bus loading:** 4.7k static pull-ups at 400kHz support only ~75pF; ten devices
on drop cables is 300-400pF. The LTC4311 is what makes this bus work.

## LTC4311 bus accelerator — cols 1–4 (top)

4-pin female header at `c1a · c2a · c3a · c4a`.

| Pin | Header hole | Rail connection |
|-----|-------------|-----------------|
| VCC | `c1a` | `c1b→V1` (straight up) |
| GND | `c2a` | `c2b→G2` (straight up) |
| SDA | `c3a` | `c3e→SDA3` (insulated run down col 3) |
| SCL | `c4a` | `c4e→SCL4` (insulated run down col 4) |

Cols 1–4 bottom strips are entirely free, so both down-runs have clear paths.
The LTC4311 was already one of the ten counted bus devices — its rail taps
simply move from flying wires to these jumpers.

> **Verify before building:** confirm the breakout is a **4-pin parallel tap**
> (VCC/GND/SDA/SCL) and not an in-line part needing SDAIN/SDAOUT/SCLIN/SCLOUT.
> Confirm the **EN pin is tied high** on the breakout — a broken-out floating EN
> means the accelerator silently does nothing and the bus quietly stays slow.

## Pi connection — column 12

True vertical 0.1" 3-pin header at the bottom edge:

| Pin | Hole | Net path |
|-----|------|----------|
| PI GND | `c12j` | col12 bottom strip → `c12f→G22` and `c12g→G12` (low-Z return) |
| PI SDA | SDA rail, col 12 | direct |
| PI SCL | SCL rail, col 12 | direct |

`c12j` is one pitch above SDA12; all three are vertically adjacent at 0.1".
col12 bottom usage: `f`=G22 · `g`=G12 · `h`=R4 · `j`=PI GND (`i` free).

No Pi 3.3V needed — bus 3.3V comes from the TPSM, and the pull-ups are at
Pi-compatible 3.3V.

**Pi bus GPIOs:** Raspberry Pi 5, BCM numbering. I²C = **GPIO2 (SDA) / GPIO3
(SCL)** (I2C1) — untouched by anything else on the rover.

## Sonar section — signals + local ground reference

The divider bottoms reference *this board's* GND rail, so the sonar grounds must
bond here too. Otherwise the ECHO reference loops through the 12V harness and
star ground, and amps of servo IR drop shift the divider output. J1–J3 are
therefore **3-pin: GND · TRIG · ECHO** — the sonar ground returns on the same
cable and lands on the same rail as its divider.

| | J1 FRONT | J2 LEFT | J3 **RIGHT** |
|---|---|---|---|
| Header (3-pin, row j) | `c8j·c9j·c10j` | `c14j·c15j·c16j` | `c20j·c21j·c22j` |
| GND strip to rail | `c8f→G8` | `c14f→G14` | `c20f→G20` |
| TRIG GPIO pin | GPIO5 `c9h` | GPIO13 `c15h` | GPIO4 `c21h` |
| 1k | `c10g` / `c11g` | `c16g` / `c17g` | `c22g` / `c23g` |
| Junction GPIO pin | GPIO26 `c11i` | GPIO14 `c17i` | GPIO21 `c23i` |
| 2k | `c11h` / `c12h` | `c17h` / `c18h` | `c23h` / `c24h` |
| 2k ground | `c12f→G22` | `c18f→G23` | `c24f→G24` |

Matches `config.py:65-67` exactly.

**Divider:** 5V × 2k/(1k+2k) = **3.33V**. Sonar VCC (5V) still arrives off-board
from the servo rail.

**Servo-rail excursion is covered.** The 5V now comes from an adjustable DROK on
a rail servos can sag *and* spike (a buck cannot sink current, so back-driven
servos push it up). Worst case at 6V with the Pi clamping the junction to 3.6V:
in through R3 = (6−3.6)/1k = 2.4mA, out through R4 = 3.6/2k = 1.8mA, so the
clamp sinks only **0.6mA**. Even at 7V it is 1.6mA. The 1kΩ series element does
this protective work — do not shrink it.

> **GPIO14 is UART0 TXD on a Pi 5.** LEFT ECHO sits there. If the serial console
> is enabled the UART drives that pin against the divider. Confirm the console
> is disabled, or move LEFT ECHO.

## 3.3V power LED — cols 21–23 (top)

Diagnoses the documented "devices dark on USB-C-only" state at a glance.

- LED anode `c21b` / cathode `c22b`
- R9 1k `c22c` / `c23c` (about 1.3mA red; 470Ω if brighter wanted)
- `c21a→V21` · `c23a→G21`

## Rail budget

| Rail | Used | Open (bus zone) |
|------|------|-----------------|
| +3.3V | 10 devices (LTC4311 = V1) · V21 LED · V26 C7 · V27/V28 · V29/V30 | **10** |
| GND | 10 devices (LTC4311 = G2) · star bond · G8/G14/G20 sonar · G12 Pi return · G21 LED · G22-G25 · G26 C7 · G27 · G29/G30 | **5** |
| SDA | 10 devices (LTC4311 = SDA3) · PI @ col 12 · SDA30 | **9** |
| SCL | 10 devices (LTC4311 = SCL4) · PI @ col 12 · SCL30 | **9** |

The LTC4311 is one of the ten devices, not an eleventh.

**Expansion is GND-limited: 5 more devices maximum.** A device needs all four
rails.

The "11th GND wire" from earlier revisions is the **star-ground bond** (board GND
rail to system star point). It is required and now explicit.

## Free space

- **Top strips:** `c1-c4` partial (LTC4311) · `c5-c8` whole · `c9-c20` whole ·
  `c21-c23` partial (LED) · `c24` whole
- **Bottom strips:** `c1-c7` whole · `c13` whole · `c19` whole · `c27-c28` whole ·
  everything else partial
- Cols 12–24 tops are *crossed by* the three insulated divider-ground runs —
  under a wire, not occupied. Those holes remain usable.

## Verification — BEFORE soldering

1. **Meter the bare board.** `c30e` to `c30f` **must be OPEN** — the entire
   SDA/SCL separation rests on the gap breaking the column. Repeat on 2-3 random
   columns. Confirm the 4 rails are 4 independent nets, each continuous across
   all 30 holes. *Highest-consequence assumption on the board.*
2. Confirm the TPSM pinout against the physical part (VIN/GND/VOUT left-to-right,
   TO-220 face-on) and that the body does not overhang the row-c caps.
   **Solder the `c27a`/`c28a` rail jumpers before mounting the module.**
3. Confirm cap lead pitch and body size for C1/C4/C5/C6 (2.54 vs 5mm).
4. Confirm the LTC4311 breakout pinout and EN state (see above).

## Verification — after soldering, before connecting anything

- 12V at P2, polarity correct, 1A **slow-blow** fuse in line
- No 12V-to-GND short at P2 (check before applying power)
- 3.3V ±0.1V at V27 **and** at rail col 1 (far end)
- LED lights with 12V applied
- Divider junctions **3.2-3.4V** with 5V on each ECHO pin —
  **re-check any time the DROK 5V trimpot is touched**
- `c12j` to GND rail continuity (Pi GND path)
- No +3.3V-to-GND continuity (caps charge, then open)
- SDA to SCL still open *after* assembly
- SDA/SCL idle at ~3.3V before the first `i2cdetect`

## BOM

| Item | Qty | Notes |
|------|-----|-------|
| TPSM84203EAB | 1 | TI, TO-220, 3.3V/1.5A |
| 10µF 50V ceramic | 1 | C1 Cin |
| 10µF 25V ceramic | 2 | C4/C5 rail caps (the two originals) |
| 47µF ceramic, 1210 SMD, 16V/25V | 2 | C2/C3 Cout pair |
| 47µF/35V aluminium electrolytic | 1 | C6 input bulk |
| 0.1µF ceramic | 1 | C7 HF decoupler |
| 4.7kΩ | 2 | R1/R2 pull-ups |
| 1kΩ | 4 | R3/R5/R7 dividers + R9 LED |
| 2kΩ | 3 | R4/R6/R8 dividers |
| LED, red 3mm | 1 | power indicator |
| JST-PH 3-pin | 3 | J1-J3 (2.0mm pitch — splay pins) |
| JST-PH 2-pin | 1 | P2 (same caveat) |
| 4-pin female header | 1 | LTC4311 breakout socket |
| 0.1" male pin | 9 | 6 sonar GPIO + 3 Pi |
| 1A slow-blow fuse | 1 | 12V line to P2 |
| 22-26 AWG wire | — | jumpers + insulated over-board runs |

## System context

- **TPSM on the 12V main, not the 5V servo rail** — keeps the I²C rail
  independent of the UBEC and up with base power. Known behaviour: I²C devices
  are dark when the Pi runs on USB-C only without 12V. The LED above makes that
  state visible.
- **Four DROK buck converters** share the 12V main alongside the TPSM. Fuse each
  branch to its own draw; a fault in one must not drop the I²C bus. The main fuse
  must survive five converters' input caps charging together — slow-blow.
- **Grounding.** Bond the board GND rail to the system star point directly and
  short, not via the 12V return path. Five switching converters make ground
  offset a live concern, and the sonar dividers reference this rail.
- **Switching noise.** DROK modules switch at 150-180kHz. Keep I²C drops short,
  twist SDA/SCL with a ground return, cross the power harness perpendicular.
  The INA260 at 0x44 now sits at the 12V input next to the highest-current
  wiring — its drop cable is the most noise-exposed on the bus.
- Device breakouts carry their own 0.1µF decoupling — none needed on this board.
- **No ISO1540.** Removed by decision 2026-08-28; Pi SDA/SCL land directly on the
  rails. The galvanic isolation caveat is documented in prior revisions.
