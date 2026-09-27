# Drawings

Generated figures and the printable bench sheets. **Each HTML file here is the source
of a published artifact** — edit the file, then republish to the SAME url. Never
publish a second link for the same sheet; the printed copies on the bench carry the
old one.

| File | Artifact | What it is |
|---|---|---|
| `WildWilly_Pico_Carrier_Boards.html` | <https://claude.ai/artifact/8bPyEf8FYqyxdj2pgd9k2M> | §4.7's two Pico 2 W carrier boards — hole-by-hole layout, nets, build order. **This is what the boards were soldered from** (2026-09-27). |
| `WildWilly_Pinout_Card.html` | <https://claude.ai/artifact/A8exZZ4LfAfNEtcXwLKCZk> | Pi 5 + both Picos, every pin, printable harness card. |
| `WildWilly_Hardware_Map.html` | <https://claude.ai/artifact/4fuaSpynW9e6Q79Y3YC1uD> | One-page authoritative map: what owns what, Pi 5 / Pico A / Pico B / controllers / PCA9685s / INA260s / ADS1115. |

## Regenerating the carrier figures

```
cd docs/drawings && python gen_pico_carrier_boards.py
```

Writes `WildWilly_Pico_Carrier_Board_A.svg` and `_B.svg` from **one** mapping, so the
two boards cannot drift apart — that is the whole point of the script, and the pin
assertions at the top fail loudly if the geometry is edited wrongly. Paste the output
into the `<figure>` blocks of `WildWilly_Pico_Carrier_Boards.html`, then republish.

**The geometry that cost the most to get right** (read before editing):

- The Pico sits on **columns 11–30**, pins in rows **C and H**, **USB at the
  column-11 end, pins pointing DOWN**, board seen from above. So the TOP row is pins
  **21–40** (`pin = 51 − column`) and the BOTTOM row is **1–20**
  (`pin = column − 10`). Getting this inverted is what forced both boards to be
  rebuilt on 2026-09-26.
- Rail order reading down the board is **− + … + −**: both `+` rails are the INNER
  ones. That is what lets F1 and R2 stand straight into row A without crossing a rail.
- Column 11 top is **pin 40 VBUS and must stay empty**; D1's body floats over it.
- `WildWilly_Control_Level_Layout.svg` / `gen_control_level_layout.py` are unrelated
  — the chassis control level, not these boards.
