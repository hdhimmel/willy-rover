#!/usr/bin/env python3
"""Generate docs/drawings/WildWilly_Control_Level_Layout.svg.

The layout is data, not hand-drawn: edit BOARDS below and re-run. Every
placement is validated against the deck outline, the harness notch and the four
M3 keep-outs before anything is written, so a bad edit fails loudly instead of
producing a drawing that looks fine and cannot be built.

    python docs/drawings/gen_control_level_layout.py
"""
import os

# ---------------------------------------------------------------- deck
DECK_W, DECK_H = 200.0, 140.0          # mm
NOTCH = (185.0, 0.0, 15.0, 60.0)       # right edge, lower — the single harness exit
CORNER_R = 5.0
KEEPOUT = [(53, 8), (147, 8), (53, 132), (147, 132)]
KO_R = 4.5                             # Oe9 keep-out
MOUNT_R = 1.8                          # Oe3.6 M3 clearance

SCALE = 3.6                            # px per mm
OX, OY = 58.0, 594.0                   # svg origin of deck (0,0), y inverted

PALETTE = {
    "quiet": ("#E6F3EA", "#3E7A52"),
    "logic": ("#E4F0F7", "#2F6B8F"),
    "drive": ("#FAF0DC", "#8A5A1E"),
    "power": ("#FBE9E2", "#B4462A"),
}

# name: (x, y, w, h, height_mm, zone, stacked, role)
BOARDS = [
    ("EPLZON signal rev 15.1", 4, 86, 50, 40, 14, "quiet", False,
     "3x ECHO div, battery div, FSR div - P1 1x17"),
    ("Pico B", 4, 31, 21, 51, 9.5, "quiet", False,
     "Pico 2 W - 3x HC-SR04 + BNO085 RST, VSYS from Pi 5V"),
    ("ADS1115 0x48", 58, 86, 25.4, 17.78, 9, "quiet", False,
     "A0 battery div, A1 FSR - A2 spare for R5 sense"),
    ("I2C hub", 58, 108, 60, 25, 12, "logic", False,
     "GODIYMODULES 10 ports + 1 input - 8 drops, 2 spare"),
    ("LTC4311", 120, 108, 25.4, 17.78, 9, "logic", False,
     "I2C accelerator - inline on the trunk, shortest leads"),
    ("BNO085 0x4A", 150, 85, 25.4, 22.86, 4.6, "logic", False,
     "9-DoF IMU - X/Y axes parallel to chassis, rigid mount"),
    ("FeatherWing x2", 60, 4, 50.8, 22.9, 32, "drive", True,
     "0x60 RIGHT / 0x61 LEFT - 12V VIN via F2 and SW-M"),
    ("PCA9685 0x42", 58, 30, 62.5, 25.4, 20, "drive", False,
     "Steering CH0-5 - V+ = 5V (R2), 1000uF on C2"),
    ("PCA9685 0x43", 122, 14, 62.5, 25.4, 26, "drive", False,
     "Arm - V+ = 6V (R3), 2200uF Rubycon on C2"),
    ("Pico A", 26, 4, 21, 51, 9.5, "drive", False,
     "Pico 2 W - 6x quadrature encoders, VSYS from R5 3V3"),
    ("EPLZON power stack", 128, 42, 50, 40, 30, "power", True,
     "LOWER battery in + Q1 FET + 12V out / UPPER regulated out"),
    ("Fuse block", 88, 56, 38, 50, 35, "power", False,
     "F2-F5 branch fuses"),
]

NOTES = [
    "Dashed outline = 2nd board stacked above on standoffs.",
    "Quiet block top-left: analog nets never leave that corner.",
    "ADS1115 30.6 mm from the drive block, was 2.1 mm.",
    "LTC4311 2.0 mm from the hub - it needs the shortest leads of anything.",
    "Drive block lowest: H-bridges furthest from the analog corner.",
    "Power against the notch - battery enters there.",
    "Pico A by the FeatherWings: encoder and motor wires share one harness.",
    "Pico B under the signal board: 6 sonar lines stay on one carrier.",
    "Hub holes UNKNOWN, 60x25 DERIVED from 44 pins @ 2.54 - MEASURE.",
    "ADS1115 and LTC4311 hole patterns - MEASURE.",
]


def mmx(x):
    return OX + x * SCALE


def mmy(y):
    return OY - y * SCALE


def rect(x, y, w, h, **kw):
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return (f'<rect x="{mmx(x):.1f}" y="{mmy(y + h):.1f}" '
            f'width="{w * SCALE:.1f}" height="{h * SCALE:.1f}" {attrs}/>')


def text(x, y, s, size=10, weight=400, fill="#1A1A1A", anchor="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{s}</text>')


# ---------------------------------------------------------------- validate
def validate():
    errs = []

    def overlap(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    def hits_circle(r, cx, cy, rad):
        x, y, w, h = r
        nx = max(x, min(cx, x + w))
        ny = max(y, min(cy, y + h))
        return (nx - cx) ** 2 + (ny - cy) ** 2 < rad ** 2

    rs = [(b[0], (b[1], b[2], b[3], b[4])) for b in BOARDS]
    for name, r in rs:
        x, y, w, h = r
        if x < 0 or y < 0 or x + w > DECK_W or y + h > DECK_H:
            errs.append(f"{name}: off deck")
        if overlap(r, NOTCH):
            errs.append(f"{name}: intrudes into the harness notch")
        for cx, cy in KEEPOUT:
            if hits_circle(r, cx, cy, KO_R):
                errs.append(f"{name}: fouls M3 keep-out at ({cx},{cy})")
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            if overlap(rs[i][1], rs[j][1]):
                errs.append(f"OVERLAP {rs[i][0]} <-> {rs[j][0]}")
    if errs:
        raise SystemExit("LAYOUT INVALID:\n  " + "\n  ".join(errs))
    return sum(b[3] * b[4] for b in BOARDS)


# ---------------------------------------------------------------- draw
def build():
    area = validate()
    usable = DECK_W * DECK_H - NOTCH[2] * NOTCH[3]
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="1162" height="834" '
         'viewBox="0 0 1162 834" font-family="Inter,Helvetica,Arial,sans-serif">',
         '<rect width="1162" height="834" fill="#FCFBF8"/>']

    o.append(text(58, 34, "WildWilly &#8212; control level board layout", 20, 700))
    o.append(text(58, 55, f"Deck {DECK_W:.0f} &#215; {DECK_H:.0f} &#215; 4.4 mm, 2.4 mm floor, "
                          f"3 mm lip, R5 corners, {NOTCH[2]:.0f} &#215; {NOTCH[3]:.0f} notch.",
                  12, 400, "#555"))
    o.append(text(58, 73, "Plan view, origin lower-left, mm. Placement validated against deck, "
                          "notch and keep-outs. MCP23017 removed (§4.7).", 12, 400, "#555"))

    # deck outline with notch
    nx, ny, nw, nh = NOTCH
    d = (f"M {mmx(CORNER_R):.1f} {mmy(0):.1f} "
         f"L {mmx(nx):.1f} {mmy(0):.1f} "
         f"L {mmx(nx):.1f} {mmy(nh):.1f} "
         f"L {mmx(DECK_W):.1f} {mmy(nh):.1f} "
         f"L {mmx(DECK_W):.1f} {mmy(DECK_H - CORNER_R):.1f} "
         f"A {CORNER_R * SCALE:.1f} {CORNER_R * SCALE:.1f} 0 0 1 "
         f"{mmx(DECK_W - CORNER_R):.1f} {mmy(DECK_H):.1f} "
         f"L {mmx(CORNER_R):.1f} {mmy(DECK_H):.1f} "
         f"A {CORNER_R * SCALE:.1f} {CORNER_R * SCALE:.1f} 0 0 1 "
         f"{mmx(0):.1f} {mmy(DECK_H - CORNER_R):.1f} "
         f"L {mmx(0):.1f} {mmy(CORNER_R):.1f} "
         f"A {CORNER_R * SCALE:.1f} {CORNER_R * SCALE:.1f} 0 0 1 "
         f"{mmx(CORNER_R):.1f} {mmy(0):.1f} Z")
    o.append(f'<clipPath id="deck"><path d="{d}"/></clipPath>')
    o.append(f'<path d="{d}" fill="#F2EFE6" stroke="#9A927F" stroke-width="2"/>')

    # lattice hint
    o.append('<g clip-path="url(#deck)" fill="#DAD5C9">')
    yy = 3.0
    while yy < DECK_H:
        xx = 2.0
        while xx < DECK_W:
            o.append(rect(xx, yy, 2.9, 7.8, fill="#DAD5C9", opacity="0.55"))
            xx += 4.25
        yy += 10.0
    o.append("</g>")

    # notch label
    o.append(text(mmx(nx + nw / 2), mmy(nh + 4), "NOTCH &#8212; main harness", 9, 700,
                  "#8A5A1E", "middle"))

    # boards
    for name, x, y, w, h, hz, zone, stacked, role in BOARDS:
        fill, stroke = PALETTE[zone]
        if stacked:
            o.append(rect(x + 1.25, y + 1.25, w, h, fill="none", stroke=stroke,
                          stroke_width="1.3", stroke_dasharray="3 2.5", rx="2.5",
                          opacity="0.75"))
        o.append(rect(x, y, w, h, fill=fill, stroke=stroke, stroke_width="1.9", rx="2.5"))
        cx = mmx(x + w / 2)
        cy = mmy(y + h / 2)
        o.append(text(cx, cy - 4, name, 10, 700, "#1A1A1A", "middle"))
        o.append(text(cx, cy + 8, f"{w:g} &#215; {h:g}" + ("  ·  ×2 stacked" if stacked else ""),
                      8.5, 400, "#555", "middle"))
        o.append(text(cx, cy + 19, f"h≈{hz:g} mm", 8.5, 400, "#777", "middle"))

    # mounts
    for cx, cy in KEEPOUT:
        o.append(f'<circle cx="{mmx(cx):.1f}" cy="{mmy(cy):.1f}" r="{KO_R * SCALE:.1f}" '
                 f'fill="none" stroke="#C0392B" stroke-width="1" stroke-dasharray="2 2"/>')
        o.append(f'<circle cx="{mmx(cx):.1f}" cy="{mmy(cy):.1f}" r="{MOUNT_R * SCALE:.1f}" '
                 f'fill="#FFF" stroke="#C0392B" stroke-width="1.4"/>')
    o.append(text(58, mmy(DECK_H) - 12,
                  "&#216;3.6 M3 chassis mount &#215;4 &#8212; 94.0 &#215; 124.0 pattern, keep-out &#216;9",
                  9, 400, "#C0392B"))

    # dimensions
    o.append(text(mmx(DECK_W / 2), mmy(0) + 24, f"{DECK_W:.1f}", 10, 700, "#555", "middle"))
    o.append(text(mmx(0) - 26, mmy(DECK_H / 2), f"{DECK_H:.1f}", 10, 700, "#555", "middle"))

    # side panel
    px, py = 792, 56
    o.append(f'<rect x="{px}" y="{py}" width="350" height="712" fill="#FFF" '
             f'stroke="#DDD8CC" rx="5"/>')
    ty = py + 26
    o.append(text(px + 16, ty, "Placement &#183; zone &#183; role", 12, 700))
    ty += 10
    zone_titles = {"quiet": "QUIET — analog, far from the drive block",
                   "logic": "LOGIC — bus trunk and IMU",
                   "drive": "DRIVE — motor and servo, bottom band",
                   "power": "POWER — against the notch"}
    seen = set()
    for name, x, y, w, h, hz, zone, stacked, role in BOARDS:
        if zone not in seen:
            seen.add(zone)
            ty += 16
            o.append(text(px + 16, ty, zone_titles[zone], 9.5, 700, PALETTE[zone][1]))
            ty += 4
        ty += 15
        o.append(text(px + 16, ty, f"{name} @ ({x:g}, {y:g})", 9.5, 700, "#1A1A1A"))
        ty += 12
        o.append(text(px + 24, ty, "• " + role, 9, 400, "#555"))
    ty += 22
    o.append(text(px + 16, ty, "Notes", 11, 700))
    for n in NOTES:
        ty += 13
        o.append(text(px + 16, ty, n, 8.8, 400, "#555"))
    ty += 20
    o.append(text(px + 16, ty,
                  f"{area / usable * 100:.0f}% fill &#183; {usable:,.0f} mm&#178; usable",
                  9.5, 700, "#3E7A52"))

    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "WildWilly_Control_Level_Layout.svg")
    svg = build()
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {out}  ({len(svg):,} bytes)")
