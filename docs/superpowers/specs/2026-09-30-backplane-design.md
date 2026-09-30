# WildWilly backplane — future design enhancement

**Status: DESIGN ONLY. Nothing here changes Willie in his current form.** He keeps
running on the five hand-built boards, and work continues on them. This is a shelf
design to be built when there is a reason to build it — a second rover, or enough
accumulated wiring faults to justify the rebuild.

Recorded 2026-09-30, owner-directed.

---

## 1. What this is, and what it is not

**It is a backplane.** Every purchased module stays exactly as it is and plugs in.
The board replaces the flying leads *between* boards with copper, and absorbs the
hand-built boards whose only job was to hold passives.

**It is not a redesign of any device.** No module is re-engineered, no chip-level
work, no change to any device's own circuit.

### Absorbed into the board

| Board today | What moves onto the backplane |
|---|---|
| EPLZON signal board rev 15.1 | 3× ECHO dividers, battery divider (R7/R8/R9), FSR pull-down (R10); P1's 1×17 becomes edge connectors |
| EPLZON power boards ×2 | their carrier function only — the ADS1115 and LTC4311 stay as modules |
| Power distribution board | F2, F3, F4, F5, SW-M, SW-A as board-mounted parts |
| MOSFET board | Q1 FQP27P06 + 220 nF |
| GODIY I²C hub | routed copper trunk, LTC4311 inline |
| Pico carrier ×2 | F1, D1, the 2×20 sockets, A's divider, B's R4 |

### Socketed on the board

2× Pico 2 W · 3× INA260 · ADS1115 · LTC4311 · 2× PCA9685 (`0x42` steering,
`0x43` arm) · BNO085 · the FeatherWing stack.

### Off-board, on keyed edge connectors

Raspberry Pi 5 · 6 motors · 6 encoders · 3 HC-SR04 · 6 steering servos · 7 arm
servos · FSR402 · SEN0628 ToF.

⚠ **Motor VIN and the six motor pairs stay on the FeatherWings' own screw
terminals.** Those are not brought out to the Feather headers, so they cannot route
through the socket — and that is the right answer regardless. They carry up to
~1.5 A per channel, and the fix for a high-current path is *fewer* connector hops,
not more. Routing motor current through a backplane socket and out to a second
connector would add two joints per wheel, on a rover where three motor joints worked
loose in a single day (2026-09-30).

---

## 2. Grounding — the reason this board is worth building

This rover is star-grounded by design (§10, single-point star), and **its two worst
failures were ground failures**:

- the GeeekPi breakout's ground fault (§5.3), which let sonar return current flow
  through the TRIG/ECHO lines and the Pi's protection diodes. It floated the sensors'
  reference, held ECHO high, and **destroyed two HC-SR04s** (§16.12).
- a metal standoff under the MOSFET/distribution stack, which **shorted the +12 V
  rail** (2026-09-28) and invalidated every rail reading taken near it — costing two
  sessions of theorising about a buck trimpot and a sonar ground return that turned
  out to be artefacts.

Today the star is a *wiring convention*: it holds only while every person who lands a
ground wire remembers where it goes. On this board it becomes geometry.

### Layer stack

| Layer | Carries |
|---|---|
| 1 — top | signal routing, module footprints, connectors |
| 2 | **signal ground** — solid pour under the I²C trunk, the dividers, the BNO085 |
| 3 | **power return** — solid pour under the FeatherWing stack and the 12 V distribution |
| 4 — bottom | power rails: +12 V, R1 9 V, R2 5 V, R3 6 V, R5 3.3 V |

**Layers 2 and 3 are separate copper.** They meet at exactly one place: a via stitch
at the star point, placed beside Q1 and the battery input.

The consequence is the whole point. Motor return current flows in layer 3 and
**physically cannot share copper** with the BNO085 or the analog dividers. The
mechanism that destroyed two sonars stops being unlikely and becomes impossible.

⚠ **A 2-layer board cannot do this.** Without the two pours, the star has to be built
by routing discipline, which is exactly the thing that has repeatedly failed. The
extra two layers are the cheapest reliability available on this rover.

---

## 3. Floorplan

Placement follows the grounding, and it happens to match the banding §2.2 already
uses, which is a good sign rather than a coincidence.

```
+--------------------------------------------------------------+
|  QUIET END                    TRUNK                 LOUD END  |
|                                                               |
|  BNO085     ADS1115      [ LTC4311 ]        FeatherWing stack |
|  dividers   INA260 x3     I2C trunk         Q1 + 220nF        |
|  FSR/batt                                   F2..F6, SW-M/A    |
|  Pico B     PCA9685 0x43                    Pico A            |
|             PCA9685 0x42                                      |
|                                                               |
|  ^ over layer-2 pour                    ^ over layer-3 pour   |
|                              * star via stitch, beside Q1     |
+--------------------------------------------------------------+
```

Rules that fall out of it:

- **The FeatherWing stack and Q1 sit over the power-return pour**, at the loud end.
- **The BNO085, ADS1115 and every divider sit over the signal-ground pour**, at the
  quiet end. §2 already calls the battery divider and the FSR "the two quietest nets
  on the rover"; this is where they belong.
- **The I²C trunk runs between them with the LTC4311 inline**, satisfying §16.4's
  requirement for the shortest leads of any device on the bus.
- **Pico A sits at the loud end** — it is the encoder counter and its twelve lines
  come from the motors. **Pico B sits at the quiet end** — its sonar ECHO lines are
  divider outputs and it drives the IMU reset.

---

## 4. Protection, and the faults it designs out

| Part | Fixes |
|---|---|
| **F6, new** | **P8 has no fuse today** (§14 item 16) — the only +12 V branch without one, and it feeds Pico A's VSYS. On a backplane it is one more fuse holder rather than a wiring job. |
| **D2 ×2, new** | Reverse-polarity clamp across each Pico's feed: anode to GND, cathode to V+, idle in normal use, conducting into F1 on a reversed feed. Neither carrier has one today, and **Board B survived a reversed J1 on 2026-09-28 on luck alone**. |
| **J1 disappears** | Absorbing the Pico carriers removes the connector that was reversed. A Pico that sockets directly into the backplane has no feed to get backwards. |
| **Plated, placed mounting holes** | Six M3, with designed keep-outs, and **plastic standoffs specified wherever one passes a rail**. The 2026-09-28 short was a metal standoff in a hole nobody had specified. |
| **Q1 on-board** | Reverse-polarity protection at the battery input stops being a stacked daughterboard. |

⚠ **Q1 still protects only the battery input.** Every rail downstream of it remains
unprotected against a reversed connector — which is why D2 is per-Pico and not a
single part. Four reverse-polarity events are on record: the encoder supply
(2026-09-18, LF Phase A destroyed and all six Phase B greens dead since), two sonars
(§16.12), and Pico B (2026-09-28).

---

## 5. The rail boundary — planned, out of scope

R1, R2, R3 and R5 each terminate at a **labelled input with its own fuse and sense
point**. The DROK modules sit behind that boundary as the current source.

That costs nothing now and means a future designed supply replaces only what is on
the far side of four connectors — the backplane does not change.

**It also gives that future board a job worth doing. Both DROK faults on this rover
were trimpot faults:** R2 sat at **6.446 V** on a nominal 5 V rail for eleven days
and is the leading cause of the sonar destroyed in the 2026-09-28 smoke event
(HC-SR04 absolute max is 5.5 V), and it read 6.72 V on 2026-09-17 without being
recognised. Fixed feedback resistors remove "someone turned the pot, or it drifted"
as a failure mode: the rail becomes a property of the board instead of a setting.

---

## 6. Serviceability

- **Every net silkscreened by name**, not by reference designator alone. The wiring
  becomes readable from the board instead of by cross-referencing five documents.
- **Test points on TP1, TP2, each ECHO divider junction, each rail, and the star.**
  §16.12 check 6 (the three ECHO junctions at 3.2–3.4 V) becomes three probe points
  instead of a disassembly.
- **Keyed, distinct connectors per function.** Six encoders with identical 6-way
  housings is how left/right transpositions keep happening — three of them on record,
  including the encoder map corrected on 2026-09-29.
- **A per-wheel encoder-supply LED on the board**, mirroring the one on the motor
  PCBs. That indicator found a fault on 2026-09-30 and is in no document.

---

## 7. Out of scope

- The Pi 5 and its HAT stack.
- Replacing the DROK regulators (§5, planned interface only).
- Any change to a purchased module's own circuit.
- Motor VIN and motor output wiring (§1).
- **Anything touching Willie in his current form.**

---

## 8. Open questions

1. **Board outline and mounting** — dictated by the existing deck, which is not
   dimensioned in any document. Needs measuring before layout.
2. **Connector family.** Partly decided.

   **The Pi is settled: a 2x20 2.54 mm SMD keyed box header, 40-way IDC ribbon.**
   Shrouded and polarised so the ribbon cannot go on backwards, which matters on a
   rover with four reverse-polarity events on record. It also decouples the board
   outline from wherever the Pi is mounted, removing one of the three blockers. And
   its **eight ground pins** replace the two wires (pin 6/9) the rover uses today --
   a much lower-impedance reference tie at exactly the junction the star cares about.

   **The rest is open, and one family will not cover it.** The rail inputs carry up
   to **10 A** (F2, F4, F5), which rules out JST-PH at ~2 A. Expect a power family and
   a signal family. **The deciding input is the available crimp tooling**, not a
   datasheet: three of the six wheel faults found on 2026-09-30 were loose joints at
   the motor end, and a family that cannot be crimped reliably reproduces that fault
   on a new board.
3. **Fuse format.** F2–F5 are ATC/ATO blade today. Blade holders are large for a
   PCB; a switch to a PCB-mount family changes the current ratings available.
4. **Whether the Pi mounts to this board or stays separate.** Currently separate.
5. **Board cost at 4 layers** for the deck-sized outline — unknown until the outline
   is measured.

## 9. Verification, when it is built

Before a single module is fitted:

1. Continuity: signal ground to power return is **open everywhere except the star**.
   One measurement, and it is the whole thesis of the board.
2. Every rail to its own return: open.
3. Divider ratios at each test point, unpowered.
4. Q1 orientation, and each D2 forward one way and open the other.

Then fit modules one at a time, bus scan after each — ten I²C devices expected,
with `0x27` gone.
