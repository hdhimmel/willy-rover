# -*- coding: utf-8 -*-
"""Generate both board figures from one mapping, so the two cannot drift.

Owner-directed 2026-09-26: shift the Pico RIGHT to columns 11-30 and put F1/D1
in columns 1-10, so the VSYS link stops crossing the whole board.

USB at the LEFT end of the Pico (column 11). Pins point DOWN, board seen from
above, so pins 21-40 run along the TOP row and 1-20 along the BOTTOM, with
pin 40 and pin 1 both at the column-11 end.
    top pin    = 51 - column
    bottom pin = column - 10
"""
import io

P = 24
def x(c): return 60 + (c - 1) * P
# Top pair is REVERSED relative to the bottom (owner, 2026-09-26): reading down the
# board the rails are  -  +  ...rows...  +  - , so both + rails are the INNER ones.
# Consequence: F1 and R2 stand from the + rail into row A without crossing anything.
UP_M, UP_P = 60, 84
RA, RB, RC, RD, RE = 120, 144, 168, 192, 216
RF, RG, RH, RI, RJ = 264, 288, 312, 336, 360
LO_P, LO_M = 396, 420

C0 = 11                                  # first Pico column
def top_pin(c): return 40 - (c - C0)     # pins 21-40
def bot_pin(c): return 1 + (c - C0)      # pins 1-20
def col_of_top(p): return C0 + 40 - p
def col_of_bot(p): return C0 + p - 1

NAME = {1:"GP0",2:"GP1",3:"GND",4:"GP2",5:"GP3",6:"GP4",7:"GP5",8:"GND",9:"GP6",
        10:"GP7",11:"GP8",12:"GP9",13:"GND",14:"GP10",15:"GP11",16:"GP12",
        17:"GP13",18:"GND",19:"GP14",20:"GP15",33:"AGND",34:"GP28",38:"GND",
        39:"VSYS",40:"VBUS"}
assert col_of_top(40) == 11 and col_of_top(39) == 12 and col_of_top(38) == 13
assert col_of_top(34) == 17 and col_of_top(33) == 18
assert col_of_bot(1) == 11 and col_of_bot(16) == 26 and col_of_bot(20) == 30
assert top_pin(11) == 40 and bot_pin(30) == 20

C_VSYS, C_GND38, C_NODE, C_AGND = 12, 13, 17, 18
C_TX, C_RX, C_SGND, C_RST = 26, 27, 28, 30

YEL, GRN, GRY, PUR, BLU, AMB = "#e8c033", "#3f8f52", "#9aa3ab", "#7a5ba6", "#2f6fb5", "#d98324"
ENC = [(col_of_bot(p), c) for p, c in
       ((1,YEL),(2,GRN),(4,YEL),(5,GRN),(6,YEL),(7,GRN),
        (9,YEL),(10,GRN),(11,YEL),(12,GRN),(14,YEL),(15,GRN))]
SON = [(col_of_bot(p), c) for p, c in
       ((1,GRY),(2,PUR),(4,GRY),(5,PUR),(6,GRY),(7,PUR))]


# Spare GPIOs, derived from the same mapping. Top side = pins 21-40, so those
# land in rows A/B; bottom side = pins 1-20, rows I/J.
TOP_GPIO = {21:"GP16",22:"GP17",24:"GP18",25:"GP19",26:"GP20",27:"GP21",
            29:"GP22",31:"GP26",32:"GP27",34:"GP28"}
BOT_GPIO = dict((p, "GP%d" % g) for p, g in
                ((1,0),(2,1),(4,2),(5,3),(6,4),(7,5),(9,6),(10,7),(11,8),
                 (12,9),(14,10),(15,11),(16,12),(17,13),(19,14),(20,15)))
USED_A_BOT = set([1,2,4,5,6,7,9,10,11,12,14,15,16,17,18])   # encoders, UART, sig GND
USED_B_BOT = set([1,2,4,5,6,7,16,17,18,20])                 # sonar, UART, pin 18, RST
USED_A_TOP = set([39,38,34,33,40])                          # VSYS, GND, divider, VBUS
USED_B_TOP = set([39,38,40])

def spares(used_top, used_bot):
    top = sorted(((col_of_top(p), g) for p, g in TOP_GPIO.items() if p not in used_top),
                 key=lambda t: t[0])
    bot = sorted(((col_of_bot(p), g) for p, g in BOT_GPIO.items() if p not in used_bot),
                 key=lambda t: t[0])
    return top, bot

SPARE_STROKE = "var(--accent)"

def spare_marks(items, y):
    o = []
    for c, _g in items:
        o.append('  <rect x="%.1f" y="%.1f" width="13" height="13" rx="1.5" fill="none" '
                 'stroke="%s" stroke-width="1.6" stroke-dasharray="3 2"/>'
                 % (x(c)-6.5, y-6.5, SPARE_STROKE))
        o.append('  <circle cx="%d" cy="%d" r="3.1" fill="none" stroke="currentColor" '
                 'stroke-width="1.1" opacity="0.85"/>' % (x(c), y))
    return "\n".join(o)

def spare_line(label, items, y):
    txt = "  ".join("c%d=%s" % (c, g) for c, g in items)
    return ('  <text class="tsm" x="36" y="%d"><tspan fill="%s">SPARE</tspan>  %s: %s</text>'
            % (y, SPARE_STROKE, label, txt))


def frame(sfx):
    o = []; a = o.append
    a('  <defs>')
    for pid, yoff in (("hBus"+sfx, 48), ("hGrid"+sfx, 108)):
        a('    <pattern id="%s" width="24" height="24" patternUnits="userSpaceOnUse" x="48" y="%d">' % (pid, yoff))
        a('      <circle cx="12" cy="12" r="3.1" fill="none" stroke="currentColor" stroke-width="1.1" opacity="0.75"/>')
        a('    </pattern>')
    for pid, yoff in (("sTop"+sfx, 108), ("sBot"+sfx, 252)):
        a('    <pattern id="%s" width="24" height="120" patternUnits="userSpaceOnUse" x="48" y="%d">' % (pid, yoff))
        a('      <rect x="6" y="4" width="12" height="112" rx="6" fill="currentColor" opacity="0.10"/>')
        a('    </pattern>')
    a('  </defs>')
    a('  <rect x="30" y="40" width="756" height="400" rx="4" fill="none" stroke="currentColor" stroke-width="2"/>')
    for yy in (48, 384):
        a('  <rect x="48" y="%d" width="720" height="48" fill="url(#hBus%s)"/>' % (yy, sfx))
    a('  <rect x="48" y="108" width="720" height="120" fill="url(#sTop%s)"/>' % sfx)
    a('  <rect x="48" y="252" width="720" height="120" fill="url(#sBot%s)"/>' % sfx)
    a('  <rect x="48" y="108" width="720" height="120" fill="url(#hGrid%s)"/>' % sfx)
    a('  <rect x="48" y="252" width="720" height="120" fill="url(#hGrid%s)"/>' % sfx)
    for yy, col, op in ((UP_P,"var(--stop)",0.5),(UP_M,"currentColor",0.4),
                        (LO_P,"var(--stop)",0.5),(LO_M,"currentColor",0.4)):
        a('  <line x1="48" y1="%d" x2="768" y2="%d" stroke="%s" stroke-width="2.2" opacity="%s"/>' % (yy,yy,col,op))
    for lab, yy in (("+",UP_P),(u"−",UP_M),("A",RA),("B",RB),("C",RC),("D",RD),("E",RE),
                    ("F",RF),("G",RG),("H",RH),("I",RI),("J",RJ),("+",LO_P),(u"−",LO_M)):
        a('  <text class="tsm" x="22" y="%d" text-anchor="end">%s</text>' % (yy+4, lab))
    for c in range(1, 31, 2):
        a('  <text class="tsm" x="%d" y="104" text-anchor="middle">%d</text>' % (x(c), c))
    # Pico body, columns 11-30, plus the USB shell hanging left of column 11
    px0 = x(C0) - 10
    a('  <rect x="%d" y="158" width="%d" height="164" rx="3" fill="currentColor" opacity="0.07"/>' % (px0, x(C0+19)-px0+10))
    a('  <rect x="%d" y="158" width="%d" height="164" rx="3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-dasharray="6 4"/>' % (px0, x(C0+19)-px0+10))
    a('  <rect x="%d" y="205" width="26" height="70" rx="2" fill="var(--card)" stroke="currentColor" stroke-width="2"/>' % (px0-26))
    a('  <line x1="%d" y1="214" x2="%d" y2="266" stroke="currentColor" stroke-width="1.3" opacity="0.65"/>' % (px0-19, px0-19))
    a('  <line x1="%d" y1="214" x2="%d" y2="266" stroke="currentColor" stroke-width="1.3" opacity="0.4"/>' % (px0-12, px0-12))
    a('  <text class="tsm" x="%d" y="236" text-anchor="end">micro-USB</text>' % (px0-32))
    a('  <text class="tsm" x="%d" y="250" text-anchor="end">plug reaches back</text>' % (px0-32))
    a('  <text class="tsm" x="%d" y="264" text-anchor="end">over cols 5–10, rows D–G</text>' % (px0-32))
    return "\n".join(o)


def pico_key(extra):
    return "\n".join([
      '  <text class="t tbig" x="%d" y="234" text-anchor="middle">PICO 2 W &#8212; columns %d&#8211;%d, pins in rows C and H</text>' % (x(20), C0, C0+19),
      '  <text class="tsm" x="%d" y="252" text-anchor="middle">USB at the column-%d end &#183; pins point DOWN, board seen from above</text>' % (x(20), C0),
      '  <text class="tsm" x="%d" y="270" text-anchor="middle">row C = pins 21&#8211;40, pin = 51 &#8722; column   |   row H = pins 1&#8211;20, pin = column &#8722; 10</text>' % x(20),
      '  <text class="tsm" x="%d" y="288" text-anchor="middle">TOP: col 11 = 40 VBUS &#9888; leave empty &#183; col 12 = 39 VSYS &#183; col 13 = 38 GND &#183; col 17 = 34 GP28 &#183; col 18 = 33 AGND</text>' % x(20),
      '  <text class="tsm" x="%d" y="306" text-anchor="middle">%s</text>' % (x(20), extra)])


def power_chain():
    """No jumpers: F1 stands from the + rail into column 9, D1 spans 9 -> 12 (VSYS).

    With the top pair reversed, + is the inner rail, so F1 stands straight into row A
    crossing nothing. D1's body floats over columns 10 and 11; column 11 is pin 40
    VBUS, which is empty by rule anyway. The pin-38 ground wire is the only thing
    that passes a rail it must not touch -- the + rail at column 13 -- hence the jog.
    """
    o = []; a = o.append
    a('  <line class="wire" x1="%d" y1="%d" x2="%d" y2="%d" stroke-width="2"/>' % (x(9),UP_P,x(9),RA))
    a('  <rect x="%d" y="%d" width="22" height="30" rx="2" fill="var(--card)" stroke="currentColor" stroke-width="2"/>' % (x(9)-11, UP_P+15))
    a('  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="currentColor" stroke-width="1.6"/>' % (x(9)-6,UP_P+38,x(9)+6,UP_P+22))
    a('  <text class="t" x="%d" y="%d">F1 &#183; + rail &#8594; c9a</text>' % (x(9)+16, UP_P+30))
    a('  <line class="wire" x1="%d" y1="%d" x2="%d" y2="%d" stroke-width="2"/>' % (x(9),RB,x(C_VSYS),RB))
    a('  <rect x="%d" y="%d" width="40" height="20" rx="1" fill="var(--card)" stroke="currentColor" stroke-width="2"/>' % (x(9)+16, RB-10))
    a('  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="currentColor" stroke-width="4"/>' % (x(9)+50,RB-10,x(9)+50,RB+10))
    a('  <text class="t" x="%d" y="%d" text-anchor="end">D1 &#183; c9b &#8594; c12b, band at c12 &#183; VSYS, pin 39</text>' % (x(9)-16, RB+4))
    a('  <polyline class="wire" points="%d,%d %d,%d %d,%d %d,%d" stroke-width="3"/>' % (x(C_GND38),RA,x(C_GND38)+10,RA-12,x(C_GND38)+10,UP_M+12,x(C_GND38),UP_M))
    a('  <text class="tsm" x="%d" y="%d">GND &#183; pin 38 &#183; the only wire on the board</text>' % (x(C_GND38)+16, RA-16))
    return "\n".join(o)


DEST = "#c62828"          # hard-coded: must print red, not theme-follow

def dest(xx, yy, big, small, anchor="start"):
    """Big bold-red off-board destination name, with the detail beneath it."""
    o = ['  <text class="dest" x="%d" y="%d" text-anchor="%s">%s</text>'
         % (xx, yy, anchor, big)]
    if small:
        o.append('  <text class="tsm" x="%d" y="%d" text-anchor="%s">%s</text>'
                 % (xx, yy + 15, anchor, small))
    return "\n".join(o)


def lead(*pts):
    """Red leader from a board feature to its destination label."""
    return ('  <polyline points="%s" fill="none" stroke="%s" stroke-width="2"/>'
            % (" ".join("%d,%d" % p for p in pts), DEST))


def rails(top_m, top_p, bot_p, bot_m):
    """The four rail destinations: upper pair right, lower pair left."""
    return "\n".join([
        lead((768, UP_M), (782, UP_M), (782, 50), (795, 50)),
        dest(800, 56, top_m[0], top_m[1]),
        lead((768, UP_P), (782, UP_P), (782, 92), (795, 92)),
        dest(800, 98, top_p[0], top_p[1]),
        lead((48, LO_P), (34, LO_P), (34, 386), (20, 386)),
        dest(14, 392, bot_p[0], bot_p[1], anchor="end"),
        lead((48, LO_M), (34, LO_M), (34, 430), (20, 430)),
        dest(14, 436, bot_m[0], bot_m[1], anchor="end")])


def devgroup(last_col, big, small):
    """Destination of the device-wire group in row I, labelled off the left."""
    return "\n".join([
        lead((x(last_col) + 13, RI), (20, RI)),
        dest(14, 326, big, small, anchor="end")])


def markers(items, y):
    o = []
    for c, fill in items:
        f = 'none' if fill is None else fill
        op = '' if fill is None else ' fill-opacity="0.9"'
        o.append('  <rect x="%.1f" y="%.1f" width="13" height="13" rx="1.5" fill="%s"%s stroke="currentColor" stroke-width="1.2"/>' % (x(c)-6.5, y-6.5, f, op))
        o.append('  <circle cx="%d" cy="%d" r="3.1" fill="none" stroke="currentColor" stroke-width="1.1" opacity="0.85"/>' % (x(c), y))
    return "\n".join(o)


def legend(items, y=454):
    o, xx = [], 36
    for fill, label in items:
        f = 'none' if fill is None else fill
        op = '' if fill is None else ' fill-opacity="0.9"'
        o.append('  <rect x="%d" y="%d" width="12" height="12" rx="1.5" fill="%s"%s stroke="currentColor" stroke-width="1.2"/>' % (xx, y-9, f, op))
        o.append('  <text class="tsm" x="%d" y="%d">%s</text>' % (xx+17, y, label))
        xx += 39 + int(len(label) * 6.6)
    return "\n".join(o)


A = ['<svg viewBox="-330 0 1500 512" role="img" aria-label="Board A hole layout. The Pico sits over columns 11 to 30 with pin rows in C and H, USB at the column-11 end. Row C carries pins 21 to 40, row H carries pins 1 to 20. The power chain occupies the ten free columns to the left: F1 stands from the upper plus rail into column 9 row A, and D1 spans column 9 to column 12 in row B with its band at column 12, landing VSYS directly on pin 39. There are no jumpers. Ground leaves column 13 for the upper minus rail. R2 drops from the upper plus rail into column 17 row A and R3 runs column 17 to column 18 in row B, landing the divider on GP28 and AGND. The twelve encoder wires land in row I of columns 11 to 25. Dashed squares mark the spare GPIOs: nine on the top side in row A and two on the bottom.">']
A.append(frame("A"))
A.append(pico_key("BOTTOM: cols 11&#8211;25 = encoders &#183; 26 = TX &#183; 27 = RX &#183; 28 = GND &#183; 29, 30 free"))
A.append(power_chain())
A.append('  <g class="variant">')
A.append('    <line class="wire" x1="%d" y1="%d" x2="%d" y2="%d" stroke-width="2"/>' % (x(C_NODE),UP_P,x(C_NODE),RA))
A.append('    <rect x="%d" y="%d" width="22" height="28" rx="1" fill="var(--card)" stroke="currentColor" stroke-width="2"/>' % (x(C_NODE)-11, UP_P+16))
A.append('    <line class="wire" x1="%d" y1="%d" x2="%d" y2="%d" stroke-width="2"/>' % (x(C_NODE),RB,x(C_AGND),RB))
A.append('    <rect x="%d" y="%d" width="22" height="18" rx="1" fill="var(--card)" stroke="currentColor" stroke-width="2"/>' % (x(C_NODE)+1, RB-9))
A.append('    <text class="t" x="%d" y="%d">R2 10k 1%%  + rail &#8594; c17a</text>' % (x(C_NODE)+16, UP_P+34))
A.append('    <text class="t" x="%d" y="%d">R3 10k 1%%  c17b &#8211; c18b &#8594; pin 33 AGND</text>' % (x(C_AGND)+14, RB+4))
A.append('  </g>')
A.append('  <text class="t" x="36" y="436">Holes a device wire lands in &#8212; row I (row J is the spare)</text>')
A.append(markers(ENC + [(C_TX,BLU),(C_RX,BLU),(C_SGND,None)], RI))
A.append(rails(("R5 GND", "&#8594; single-point star (&#167;10)"),
               ("R5 3.3 V", "DROK-4 &#8212; NOT the Pi &#183; via F1 + D1"),
               ("UNUSED ON A", "nothing lands on the lower + rail"),
               ("GND", "both &#8722; rails tied at column 30")))
A.append(devgroup(25, "ENCODERS &#215; 6", "12 wires &#183; yellow = Phase A, green = Phase B"))
A.append(lead((x(C_SGND)+13, RI), (795, RI)))
A.append(dest(800, 342, "PI 5",
              "c26 &#8594; pin 33 GP13 &#183; c27 &#8594; pin 32 GP12 &#183; c28 &#8594; pin 6/9 GND"))
A.append('  <text class="tsm" x="800" y="372" fill="%s">'
         'the only three wires between Board A and the Pi</text>' % DEST)
_at, _ab = spares(USED_A_TOP, USED_A_BOT)
A.append(spare_marks(_at, RA))
A.append(spare_marks(_ab, RI))
A.append(legend([(YEL,"Phase A &#183; yellow"),(GRN,"Phase B &#183; green"),(BLU,"UART to the Pi"),(None,"signal GND")], y=454))
A.append(spare_line("top side, row A", _at, 476))
A.append(spare_line("bottom side, row I", _ab, 494))
A.append('</svg>')

B = ['<svg viewBox="-330 0 1500 512" role="img" aria-label="Board B hole layout, same geometry as board A and the same jumperless power chain: F1 from the plus rail into column 9, D1 from column 9 to column 12. Instead of the divider, R4 rises straight from the lower plus rail into column 30 row J, pulling pin 20 GP15 up to 3V3 with no jumper at all. The six sonar wires land in row I of columns 11, 12, 14, 15, 16 and 17, and the reset wire to the IMU in row I of column 30. Dashed squares mark the spare GPIOs: ten on the top side in row A, including the free ADC at column 17, and seven on the bottom.">']
B.append(frame("B"))
B.append(pico_key("BOTTOM: cols 11,12,14,15,16,17 = sonar &#183; 26 = TX &#183; 27 = RX &#183; 28 = EMPTY, no second ground &#183; 30 = GP15 RST"))
B.append(power_chain())
B.append('  <g class="variant">')
B.append('    <line class="wire" x1="%d" y1="%d" x2="%d" y2="%d" stroke-width="2"/>' % (x(C_RST),LO_P,x(C_RST),RJ))
B.append('    <rect x="%d" y="%d" width="22" height="26" rx="1" fill="var(--card)" stroke="currentColor" stroke-width="2"/>' % (x(C_RST)-11, RJ+9))
B.append('    <text class="t" x="%d" y="%d" text-anchor="end">R4 10k  + rail &#8594; c30j &#8594; pin 20 GP15</text>' % (x(C_RST)-16, RJ+30))
B.append('  </g>')
B.append('  <text class="tsm" x="%d" y="%d" text-anchor="middle">c18 = pin 33 AGND, unused on B</text>' % (x(C_AGND)+30, RB+30))
B.append('  <text class="t" x="36" y="436">Holes a device wire lands in &#8212; row I (row J is the spare)</text>')
B.append(markers(SON + [(C_TX,BLU),(C_RX,BLU),(C_RST,AMB)], RI))
B.append(rails(("PI 5  GND", "pin 6 or 9 &#8212; the ONLY ground wire on B"),
               ("PI 5  5 V", "breakout 5 V TERMINAL, not a header pin &#183; via F1 + D1"),
               ("PI 5  3V3", "header pin 1 &#8594; R4, the RST pull-up"),
               ("GND", "tied to the upper &#8722; rail at column 30")))
B.append(devgroup(17, "SONAR &#215; 3", "HC-SR04 &#183; grey = TRIG, purple = ECHO"))
B.append(lead((x(C_RST)+13, RI), (795, RI)))
B.append(dest(800, 342, "BNO085  RST", "open-drain on GP15, held up by R4"))
B.append(lead((x(C_RX)+13, RI), (x(C_RX)+13, 376), (795, 376)))
B.append(dest(800, 390, "PI 5",
              "c26 &#8594; pin 29 GP5 &#183; c27 &#8594; pin 7 GP4 &#183; ground rides the &#8722; rail"))
_bt, _bb = spares(USED_B_TOP, USED_B_BOT)
B.append(spare_marks(_bt, RA))
B.append(spare_marks(_bb, RI))
B.append(legend([(GRY,"TRIG &#183; grey"),(PUR,"ECHO &#183; purple"),(BLU,"UART"),(AMB,"RST to the IMU")], y=454))
B.append(spare_line("top side, row A", _bt, 476))
B.append(spare_line("bottom side, row I", _bb, 494))
B.append('</svg>')

io.open('WildWilly_Pico_Carrier_Board_A.svg','w',encoding='utf-8',newline='\n').write("\n".join(A))
io.open('WildWilly_Pico_Carrier_Board_B.svg','w',encoding='utf-8',newline='\n').write("\n".join(B))
print("generated, all pin assertions passed")
print("encoder columns:", [c for c,_ in ENC])
print("sonar columns:  ", [c for c,_ in SON])
