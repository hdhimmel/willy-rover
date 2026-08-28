# Combined EPLZON Board — rev 3.4

**Date:** 2026-08-28
**Supersedes:** rev 3.2, rev 3.1, rev 3, and all 2026-08-09 layout docs.

Clean consolidated build document. Netlist verified hole-by-hole — no hole is
used twice and every net resolves correctly (independent sweep, 2026-08-28).

**Board:** EPLZON 3.5"×2.05" (88.9×52.1mm) gold-plated solderable breadboard.
30 columns × 0.1" · top rails **+3.3V / GND** · rows **a–e** · center gap ·
rows **f–j** · bottom rails **SDA / SCL** (30 holes each, column-aligned).

Per column, `a–e` is one net and `f–j` is a separate net; the gap breaks them.
Adjacent columns are not connected. Rails run continuously across all 30 holes.

**RULES**
1. One lead or wire per hole — never reuse a hole.
2. Components mount horizontally across columns. Vertical runs are rail
   connections only.
3. **Device zone = rail cols 1–20:** I²C device connections only (10 devices,
   ISO side-2, LTC4311, star-ground bond). All 20 taps per rail are
   interchangeable.
4. **Circuit zone = rail cols 21–30:** every board-internal jumper lands here.

## Changes from rev 3.2

Rev 3.4 reverses three rev 3.2 decisions. All three are owner calls, recorded
here so the reasoning is not lost:

| Change | Effect |
|---|---|
| ISO1540 reinstated, off-board inline | Pi no longer lands on this board; col 12 now carries ISO **side-2** (GND2/SDA2/SCL2), plus a 4th VCC2 wire |
| LTC4311 back off-board | Must be mounted adjacent to this board with the shortest leads of any device |
| Sonar headers 3-pin → 2-pin | Sonar GND returns to star ground off-board again, not to this rail. See the commissioning check below. |

Corrections applied to the rev 3.4 draft:

- **J3 relabelled REAR → RIGHT.** `config.py:67` names it `SONAR_RIGHT_TRIG/ECHO`;
  `config.py:262` gives bearing +90°. Master Hardware Design §8.1: *"There is no
  rear sonar; the only rear-facing device is the rear USB camera."*
- **220Ω TRIG resistors — exact holes supplied** (they *are* placeable now that
  the headers are 2-pin again; they were not in rev 3.2's 3-pin layout).
- **`c14` added to the free-space list** — it was omitted and is fully free.
- **Isolation claim qualified** — see System Topology.

## System topology

```
RASPBERRY PI 5 --(3V3/GND/SDA/SCL = GPIO2/GPIO3)--> ISO1540 (off-board, inline)
                                                       | side 2: VCC2 GND2 SDA2 SCL2
                                                       v
  12V bus -[1A SLOW-BLOW]-> P2 -> THIS BOARD <-- LTC4311 (off-board, SHORTEST leads)
                                   ^      ^
             10 I2C devices -------+      +------- 3x HC-SR04 (TRIG/ECHO only;
             (V/G/SDA/SCL taps)                    VCC+GND at 5V servo rail)
                                                   + 6 GPIO wires direct to Pi
```

- Pi I²C is GPIO2/GPIO3 (BCM, Pi 5 — not RP2040).
- Sonar GPIOs (GP5/GP13/GP4 TRIG out, GP26/GP14/GP21 ECHO in) wire directly
  Pi ↔ board, bypassing the ISO.
- Known behaviour: bus devices are dark when the Pi runs on USB-C only
  without 12V.

> **The bus is not galvanically isolated.** The ISO1540 isolates the I²C lines
> and nothing else. The six sonar GPIO wires are a direct path between the Pi's
> ground domain and this board's, and the ECHO divider bottoms tie this board's
> GND rail to the dividers the Pi reads. The two domains also meet at the
> battery star point. Treat the ISO1540 as **noise rejection on I²C**, which it
> genuinely provides — never as a safety barrier.

## Power block — TPSM84203EAB @ cols 25–28 (top rows)

TI datasheet: 1.5A · 3.3V fixed · VIN 4.5–28V · TO-220 pinout ·
**Cout minimum 94µF ceramic (2×47µF).**

| Item | Holes | Notes |
|---|---|---|
| P2 power pins | GND `c25e` · 12V `c26e` | JST-PH 2.0mm pitch — splay pins into 2.54mm holes |
| Fuse | inline holder off-board, 12V line | **1A SLOW-BLOW** — inrush into C6 + 94µF trips a fast-blow |
| C6 bulk 47µF/35V electrolytic | + leg `c26a` ↔ − leg `G26` | vertical. **POLARITY: stripe (−) UP into G26** |
| C1 Cin 10µF ceramic **50V** | `c25c` ↔ `c26c` | 50V rating — a 25V part derates to ~4µF at 12V bias |
| TPSM | VIN `c26b` · GND `c27b` · VOUT `c28b` | verify pin order face-on before soldering |
| C2 Cout 47µF ceramic | `c27c` ↔ `c28c` | ≥1210 size / higher voltage to limit DC-bias derating |
| C3 Cout 47µF ceramic | `c27e` ↔ `c28e` | row e — 5.08mm from C2 for body clearance |
| Rail jumpers | `c25a→G25` · `c27a→G27` · `c28a→V27` | |

Uncrossed 3.3V runs: the TPSM feeds **V27**, R1 taps **V28** — parallel
one-column diagonals.

> **Measure `c26a`→`G26` before ordering C6.** The rev 3.4 draft asserts 0.2"
> (5mm radial pitch). If the row-a-to-rail gap is actually 0.1", you need a
> 2.5mm-pitch part. Both exist for 47µF/35V — measure, then buy.

> **Solder the row-a jumpers (`c25a`, `c27a`, `c28a`) BEFORE C6 and the TPSM.**
> A 6.3mm can at `c26a` has a 3.15mm radius and its neighbours are 2.54mm away —
> it will sit over both jumper holes. Same consideration for TO-220 body
> overhang.

## Pull-ups + rail caps — cols 29–30

| Item | Holes |
|---|---|
| R1 4.7k (SDA) | legs `c29b` ↔ `c30b` |
| R1 supply | `c29a` → `V28` |
| R1 output | `c30e` → SDA rail col 30 (insulated wire over the gap) |
| 3.3V bridge | `c29d` ↕ `c29f` (across the gap, feeds R2) |
| R2 4.7k (SCL) | legs `c29h` ↔ `c30h` |
| R2 output | `c30j` → SCL rail col 30 |
| C4 10µF (106) | vertical `V29` ↔ `G29` |
| C5 10µF (106) | vertical `V30` ↔ `G30` |

**Node map.** c29 top + bridge + c29 bottom = the shared 3.3V node (one tap,
V28, serves both resistors). c30 **top** = SDA only; c30 **bottom** = SCL only.
R2 lives below the gap precisely because c30-top already belongs to SDA — both
pull-ups in the top section would short SDA to SCL.

**Bus loading.** 4.7k at 400kHz supports ~75pF; ten devices on drop cables is
300–400pF. **The LTC4311 is what makes this bus work — mount it with the
shortest leads of any device, adjacent to this board.**

**HF decoupling (optional, recommended).** C6 now occupies G26, so no vertical
rail pair remains free — `G28` is the only open circuit-zone GND hole. A 0.1µF
still fits diagonally as `V26 ↔ G28` (0.2" span, easy with bent leads). With
four DROK converters switching at 150–180kHz, worth fitting.

## LED indicator — cols 24–26 (bottom rows)

Diagnoses "devices dark on USB-C-only" at a glance (~1.3mA red; 470Ω if
brighter wanted).

| Item | Holes |
|---|---|
| 3.3V feed | `c25f` → `V25` (wire) |
| LED | anode (+) `c25g` ↔ cathode (−) `c26g` |
| R9 1k | `c26i` ↔ `c24i` (0.2" span over `c25i` — keep that hole clear) |
| Ground | via c24 bottom strip, already tied to `G24` by the RIGHT divider return |

Sharing the divider's ground node is fine — 1.3mA adds nothing measurable to it.

## Sonar section — cols 9–24 (bottom rows)

Sonar **VCC and GND connect off-board at the 5V servo rail / star ground**
(owner decision). The board carries signals only. HC-SR04: TRIG is
3.3V-compatible (direct); ECHO is 5V, so the divider is mandatory.
5V × 2k/3k = **3.33V**.

| | FRONT | LEFT | **RIGHT** |
|---|---|---|---|
| Header (JST-PH 2-pin, row j) | TRIG `c9j` · ECHO `c10j` | TRIG `c15j` · ECHO `c16j` | TRIG `c21j` · ECHO `c22j` |
| TRIG pin → Pi | GP5 = `c9h` | GP13 = `c15h` | GP4 = `c21h` |
| 1k (ECHO side) | R3 `c10g`↔`c11g` | R5 `c16g`↔`c17g` | R7 `c22g`↔`c23g` |
| Junction pin → Pi | GP26 = `c11i` | GP14 = `c17i` | GP21 = `c23i` |
| 2k (ground side) | R4 `c11h`↔`c12h` | R6 `c17h`↔`c18h` | R8 `c23h`↔`c24h` |
| Divider ground | `c12f` → `G22` | `c18f` → `G23` | `c24f` → `G24` |

Matches `config.py:65-67`. The third sonar is **RIGHT** (bearing +90°), not rear.

**Accepted trade-off.** The divider bottoms reference this board's rail while
the sonars reference star ground.

> **Commissioning check — run it under worst-case servo load, not idle.** That
> is when the star-ground IR drop peaks, and it is the entire reason the check
> exists. ECHO junctions must hold **3.2–3.4V**. If they wander more than 0.2V,
> add one bond wire from sonar ground to any open device-zone GND tap.
> Re-check any time the DROK 5V trimpot is touched.

**Servo-rail excursion is covered.** Worst case at 6V with the Pi clamping the
junction to 3.6V: in through the 1k = (6−3.6)/1k = 2.4mA, out through the 2k =
3.6/2k = 1.8mA, so the clamp sinks only 0.6mA. Even at 7V it is 1.6mA. The 1kΩ
series element does this protective work — **do not shrink it**.

> **GPIO14 is UART0 TXD on a Pi 5**, and LEFT ECHO sits there. If the serial
> console is enabled the UART drives that pin against the divider. Confirm the
> console is disabled, or move LEFT ECHO.

### Optional — 220Ω series TRIG protection

Placeable as drawn (the 2-pin headers free the flanking columns; rev 3.2's
3-pin layout did not allow this):

| | Resistor | TRIG GPIO pin moves to |
|---|---|---|
| FRONT | `c9g` ↔ `c8g` | GP5 → `c8h` |
| LEFT | `c15g` ↔ `c14g` | GP13 → `c14h` |
| RIGHT | `c21g` ↔ `c20g` | GP4 → `c20h` |

All three neighbour strips are free. TRIG is an HC-SR04 *input* and never
back-drives, so this is insurance against a miswire, not a functional need.

## ISO1540 side-2 drop — col 12

| Wire from ISO module | Lands at |
|---|---|
| GND2 | `c12j` → strip → `c12f→G22` **and** `c12g→G21` (second low-Z return) |
| SDA2 | SDA rail hole, col 12 |
| SCL2 | SCL rail hole, col 12 |
| VCC2 | one open +3.3V device-zone tap — **pick a specific one and record it here** |

`c12j` / SDA12 / SCL12 are vertically adjacent at 0.1" — one 3-pin drop.
c12 bottom strip: `f`=G22 wire · `g`=G21 wire · `h`=R4 leg · `j`=GND2 pin
(`i` free).

Pi side, at the module and off-board: Pi 3V3→VCC1 · Pi GND→GND1 ·
GPIO2→SDA1 · GPIO3→SCL1.

**Confirm the breakout carries its own decoupling** — prior revisions called for
2× 0.1µF, one per side. Add it if the module does not have it.

## Rail map (circuit zone)

- **+3.3V:** `V25` LED · `V27` TPSM feed · `V28` R1 · `V29`/`V30` C4/C5.
  Free: V21–V24, V26.
- **GND:** `G21` ISO 2nd return · `G22`/`G23`/`G24` divider grounds ·
  `G25`/`G27` power block · `G26` C6 (−) · `G29`/`G30` C4/C5.
  **Free: G28 only.**
- **SDA:** col 30 = R1 · **SCL:** col 30 = R2
- Device zone: taps interchangeable, roughly 10–12 per rail used.
  **Expansion is GND-limited.**

## Free space

- **Top strips:** `c1–c24` entirely free. `c25–c28` used by the power block;
  `c29`/`c30` partial.
- **Bottom strips:** `c1–c8`, `c13`, **`c14`**, `c19`, `c20`, `c27–c28` (freed
  by the C6 move). Everything else partial.
- Diagonal ground wires cross cols 12–24 tops *over* the board — under a wire,
  not occupied. Those holes remain usable.

## Build order

1. **Bare-board meter checks.** `c30e`↔`c30f` = **OPEN** — the SDA/SCL
   separation depends entirely on the gap breaking the column. Repeat on 2–3
   random columns. Confirm 4 rails = 4 independent nets, each continuous across
   30 holes.
2. Confirm TPSM pin order face-on. Confirm cap lead pitch (2.54 vs 5mm — span
   two columns or bend leads if 5mm). Measure `c26a`→`G26` for C6.
3. Solder the power block: row-a jumpers **first**, then P2, C1, TPSM, C2, C3,
   C6 last. Power up on a bench supply with the current limit set to ~200mA →
   3.3V ±0.1V at `V27` **and** at rail col 1; LED lights.
4. Solder pull-ups, C4/C5, the bridge, and the optional `V26↔G28` 0.1µF.
   SDA/SCL idle ~3.3V.
5. Solder the sonar section — headers, dividers, GPIO pins, ground wires.
   5V on ECHO pins → 3.2–3.4V at junctions.
6. Solder the ISO drop pins. Continuity `c12j`↔GND rail. No +3.3V↔GND
   continuity (caps charge, then open).
7. Connect the ISO module, LTC4311 (shortest leads), and devices →
   `i2cdetect` roll-call.

## BOM

| # | Part | Qty | Location |
|---|---|---|---|
| 1 | EPLZON 3.5"×2.05" board | 1 | — |
| 2 | TPSM84203EAB | 1 | `c26b`/`c27b`/`c28b` |
| 3 | 10µF ceramic 106, **50V** | 1 | C1 `c25c`↔`c26c` |
| 4 | 10µF ceramic 106, 25V | 2 | C4/C5 rails cols 29/30 (the two originals) |
| 5 | 47µF ceramic 476, ≥1210 / higher-V | 2 | C2/C3 |
| 6 | 47µF/35V radial electrolytic | 1 | C6 `c26a`↔`G26`, stripe up |
| 7 | 4.7kΩ 1/4W | 2 | R1/R2 |
| 8 | 1kΩ 1/4W | 4 | R3/R5/R7 + R9 |
| 9 | 2kΩ 1/4W | 3 | R4/R6/R8 |
| 10 | Red LED 3mm | 1 | `c25g`/`c26g` |
| 11 | JST-PH 2-pin | 4 | J1–J3 + P2 (2.0mm pitch — splay) |
| 12 | 0.1" male pins | 9 | 6 GPIO + 3 ISO drop |
| 13 | 1A SLOW-BLOW fuse + inline holder | 1 | 12V line, off-board |
| 14 | 22–26 AWG wire | ~1m | 12 jumpers/wires below |
| opt | 0.1µF ceramic | 1 | HF decoupler `V26`↔`G28` |
| opt | 220Ω 1/4W | 3 | TRIG protection — holes above |

**Wire list (12):** `c25a→G25` · `c27a→G27` · `c28a→V27` · `c29a→V28` ·
`c29d↕c29f` · `c30e→SDA30` · `c30j→SCL30` · `c25f→V25` · `c12f→G22` ·
`c12g→G21` · `c18f→G23` · `c24f→G24`

Plus the ISO **VCC2** wire to whichever +3.3V device-zone tap you choose.

**Off-board (system, not this BOM):** ISO1540 breakout · LTC4311 breakout ·
star-ground bond wire · sonar VCC/GND at the 5V rail · Pi harness
(6 GPIO + ISO side-1 four-wire).

**Sources:** [TI TPSM84203](https://www.ti.com/product/TPSM84203) ·
[datasheet PDF](https://www.ti.com/lit/ds/symlink/tpsm84203.pdf)
