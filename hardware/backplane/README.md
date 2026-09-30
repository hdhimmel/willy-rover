# Backplane — CAD working directory

Design artifacts for the future backplane. **Nothing here is built.** See
`docs/superpowers/specs/2026-09-30-backplane-design.md` for the design and
`docs/drawings/WildWilly_Backplane.html` for the drawings.

Target tool: **KiCad** (free, offline, and the only free option that handles the
split copper pours this design depends on).

---

## ⚠ Designator collision — read before naming anything

**This rover already uses `R1`, `R2`, `R3` and `R5` to mean POWER RAILS**, and
separately uses `R1`–`R10` to mean RESISTORS on the signal board, and *again*
`R2`/`R3`/`R4` on the Pico carriers.

| Name | Means, today | Where |
|---|---|---|
| R1 | the 9 V rail to the Witty Pi | §2.1 |
| R2 | the 5 V rail — sonar + steering servos | §2.1 |
| R3 | the 6 V arm rail | §2.1 |
| R5 | the 3.3 V encoder rail (DROK-4) | §2.1 |
| R1–R6 | the three sonar ECHO divider resistors | §4.4 |
| R7, R8, R9 | the battery divider | §4.4 |
| R10 | the FSR pull-down | §4.4 |
| R2, R3 | Pico A's rail-sense divider | §4.8 |
| R4 | Pico B's BNO085 reset pull-up | §4.8 |

On five separate boards each scheme is local and survivable. **On one board they
collide three ways**, and a schematic where `R2` means a 5 V rail in one document
and a 10 k resistor in another is how a wrong part gets fitted.

### The scheme

Rails keep their `R1/R2/R3/R5` names **in prose only** — they never appear as a
designator. Board designators are prefixed by function:

| Prefix | For | Example |
|---|---|---|
| `RE` | ECHO divider resistors | `RE1H` high side, `RE1L` low side, per channel F/L/R |
| `RB` | battery divider | `RB1` 10 k, `RB2` 4.7 k, `RB3` 10 k |
| `RF` | FSR pull-down | `RF1` 10 k |
| `RP` | Pico rail-sense divider | `RPA1`, `RPA2` (A only) |
| `RR` | reset pull-up | `RRB1` (B only) |
| `F` | fuses | `F2`–`F6`, keeping the rover's existing numbering |
| `D` | diodes | `DA1`/`DB1` series, `DA2`/`DB2` reverse clamp |
| `Q` | MOSFET | `Q1`, as today |
| `SW` | switches | `SWM`, `SWA` |
| `J` | connectors | `JPI`, `JENC1`..`JENC6`, `JSON1`..`JSON3`, ... |
| `XU` | module sockets | `XPICOA`, `XINA40`, `XADS`, ... |

`X`-prefixed parts are **sockets**, not the modules. That distinction matters for
the assembly BOM below.

---

## Two BOMs, because the fab only builds one of them

An assembly service places parts **on** the board. The plug-in modules are fitted
by hand afterwards, and the fuses are inserted afterwards.

- **`BOM-fab.csv`** — what the assembly house places: passives, Q1, the diodes,
  fuse holders, switches, headers, sockets and connectors.
- **`BOM-owner.csv`** — what you fit afterwards: every module, and the fuses.

Sending the wrong one is how you get quoted for parts nobody asked them to buy, or
receive a board with no sockets on it.

---

## Order of work

1. **Measure the deck.** No document dimensions it, and the board outline cannot be
   drawn without it. Blender is the right tool and a mock-up script can come first.
2. **Choose the connector family.** Keyed per function — six identical 6-way encoder
   housings is how left/right transpositions keep happening, three on record.

   **Decided 2026-09-30 — the Pi.** A **2×20 2.54 mm SMD keyed box header**, with a
   40-way IDC ribbon to the Pi's GPIO header. Shrouded and polarised, so the ribbon
   cannot go on backwards. It decouples the board outline from wherever the Pi is
   mounted, and its **eight ground pins** give a far better reference tie than the
   two wires the rover uses today.

   **Still undecided: everything else.** And one family will not cover it — the rail
   inputs carry **up to 10 A** (F2, F4, F5), which rules out JST-PH at ~2 A. Expect a
   power family and a signal family.

   **The deciding input is your crimp tooling**, not a datasheet. Three of the six
   wheel faults found on 2026-09-30 were loose joints at the motor end; a family you
   cannot crimp reliably reproduces that fault on a new board.
3. **Choose the fuse format.** F2–F5 are ATC/ATO blade today, which is large for a
   PCB; a PCB-mount family changes the ratings available.
4. Netlist → schematic → layout → pours → DRC → plot.

Steps 1–3 are unanswered and block step 4.
