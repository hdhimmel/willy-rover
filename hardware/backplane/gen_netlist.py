#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the backplane netlist from the Master Hardware Design, not by hand.

WHY THIS IS GENERATED. Section 16.1 is the rover's device I/O index -- 111 rows of
"this pin goes to that pin", maintained and corrected over months. Retyping it into a
schematic is how transpositions happen, and this rover has three on record. So the
netlist is DERIVED from the document, and re-deriving it after a doc change is one
command. If the netlist and the document disagree, the document wins and this script
is wrong.

WHAT IT CHANGES ON THE WAY THROUGH, because the backplane is not the current rover:

  1. The MCP23017 is GONE. Its twelve encoder lines move to Pico A GP0-GP11 and its
     GPB4 reset line moves to Pico B GP15. Section 4.7.
  2. The GODIY hub is GONE. Every drop on it becomes a node on one routed I2C trunk.
  3. The signal board is GONE. Its P1-n labels resolve to the divider passives, which
     are now on this board.
  4. The Pi becomes an EDGE CONNECTOR, not a device on the board.
  5. Ground splits in two. Every ref/return pin is classified as signal ground or
     power return, and they meet only at the star.

Output:
  nets.csv         every net and every pin on it -- the checkable artifact
  backplane.net    KiCad netlist, importable into pcbnew
  unresolved.txt   rows this script could not classify -- READ THIS FILE
"""
import csv, io, os, re, sys, datetime

DOC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', '..', 'docs', 'WildWilly_Master_Hardware_Design_v2.0.md')
OUT = os.path.dirname(os.path.abspath(__file__))

# --- the encoder landing, as-built. MHD 16.6, PROVEN ON HARDWARE 2026-09-29 --------
# Pico A GP pairs in order are lf, lm, rf, rm, lr, rr -- NOT the order config.py used.
# Five wheels confirmed this one at a time on blocks. Do not "correct" it.
ENCODER_ORDER = ('lf', 'lm', 'rf', 'rm', 'lr', 'rr')

# --- ground classification --------------------------------------------------------
# The whole point of the board. A pin lands in exactly one pour.
POWER_RETURN = ('featherwing', 'motor', 'q1', 'drok', 'battery', 'fuse', 'switch')
SIGNAL_GROUND = ('bno085', 'ads1115', 'ina260', 'ltc4311', 'pca9685', 'pico',
                 'sonar', 'hc-sr04', 'fsr', 'sen0628', 'divider',
                 'signal board', 'raspberry pi', 'j_pi')

# ⚠ THE SONAR GROUND IS A DELIBERATE CHANGE FROM AS-BUILT, and it is the one
# decision on this board most worth arguing about.
#
# Today the three HC-SR04s return to the COMMON RAIL GND (owner-stated 2026-09-30),
# not to the Pi. That puts the sensor's reference in one pour and its ECHO divider's
# reference in another, so any IR drop in the power return under motor current lands
# straight on the divider output -- which is the only thing the Pico ever reads.
# That is the section 5.3 mechanism in one sentence, and it destroyed two sensors.
#
# Here they go on the SIGNAL pour. Three sonars draw about 45 mA total: it is one of
# the quietest nets on the board, and it is called a "rail" ground only because that
# is where the wire happens to go today, not because it carries rail current.
#
# The Pi's pin 6/9 is 'star ground' -- it IS the reference the signal side is built
# around, so it anchors the signal pour and meets the power return at the stitch.


def norm(s):
    s = re.sub(r'\*\*|`|\s+', ' ', s or '').strip()
    return re.sub(r'\s*\(.*?\)\s*$', '', s).strip()


def load_rows():
    raw = open(DOC, 'rb').read().decode('utf-8').replace('\r\n', '\n').split('\n')
    try:
        start = next(i for i, l in enumerate(raw) if l.startswith('### 16.1'))
    except StopIteration:
        sys.exit('16.1 not found -- has the document been renumbered?')
    end = next(i for i in range(start + 1, len(raw)) if raw[i].startswith('### 16.2'))
    rows, device = [], None
    for line in raw[start:end]:
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        # NB: set('') <= set('-: ') is True, so testing cells[0] alone silently ate
        # every continuation row -- 90 of the 111. Match the whole separator line.
        if len(cells) < 6 or re.match(r'^[\s:|-]+$', line.strip()):
            continue
        if cells[0].lower().startswith('device'):
            continue
        if norm(cells[0]):
            device = norm(cells[0])
        if device is None:
            continue
        rows.append({'dev': device, 'pin': norm(cells[1]), 'dir': norm(cells[2]),
                     'sig': norm(cells[3]), 'dst': norm(cells[4]), 'dstpin': norm(cells[5])})
    return rows


# Devices that are not on this board. They reach it through an edge connector, and
# the netlist must say so -- a Pi pin that looks like a board node is how someone ends
# up trying to route to a device that is 200 mm away on its own standoffs.
EDGE = {'raspberry pi 5': 'J_PI', 'witty pi 5': 'J_PI', 'sen0628 tof': 'J_TOF',
        'hc-sr04 × 3': 'J_SONAR', 'motor × 6': 'J_MOTOR', 'fsr402': 'J_FSR',
        'drok-5v': 'J_R2', 'drok-6v': 'J_R3', 'drok-pi': 'J_R1', 'drok-4': 'J_R5'}


def edge(name):
    return EDGE.get((name or '').strip().lower(), name)


# --- footprints ------------------------------------------------------------------
# THROUGH-HOLE, owner-directed 2026-09-30. The board stays hand-assemblable, which
# matters because the person fixing it is the person who built it. Only parts whose
# form factor is actually decided get a footprint here; everything else stays TBD
# rather than being guessed, because a fab BOM with invented footprints is worse than
# one with honest blanks.
#
# ⚠ The Pi header was specified SMD. On an otherwise through-hole board a THT
#   shrouded box header is far easier to hand-solder and is equally keyed; both
#   options are left here for the choice to be made deliberately.
FOOTPRINT = {
    'J_PI':    'Connector_IDC:IDC-Header_2x20_P2.54mm_Vertical',   # or _SMD_ if kept SMD
    'PICO_A':  'Connector_PinHeader_2.54mm:PinSocket_2x20_P2.54mm_Vertical',
    'PICO_B':  'Connector_PinHeader_2.54mm:PinSocket_2x20_P2.54mm_Vertical',
}
FOOTPRINT_BY_PREFIX = (
    ('RE',  'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'),
    ('RB',  'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'),
    ('RF',  'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'),
    ('RPA', 'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'),
    ('RRB', 'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'),
    ('DA',  'Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal'),
    ('DB',  'Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal'),
    ('Q1',  'Package_TO_SOT_THT:TO-220-3_Vertical'),
    ('CQ',  'Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm'),
    ('MH',  'MountingHole:MountingHole_3.2mm_M3'),
)


def footprint_for(ref):
    if ref in FOOTPRINT:
        return FOOTPRINT[ref]
    for pfx, fp in FOOTPRINT_BY_PREFIX:
        if ref.startswith(pfx):
            return fp
    return 'TBD:TBD'


def pour_of(name):
    n = (name or '').lower()
    for k in POWER_RETURN:
        if k in n:
            return 'GNDP'
    for k in SIGNAL_GROUND:
        if k in n:
            return 'GNDS'
    return None


def main():
    rows = load_rows()
    nets, unresolved, superseded = {}, [], []

    def add(net, pin):
        nets.setdefault(net, [])
        if pin not in nets[net]:
            nets[net].append(pin)

    for r in rows:
        if not r['pin'] or not r['dst']:
            unresolved.append('no pin or no destination: %r' % r)
            continue
        # The Pi is OFF-BOARD. Every one of its pins is an external connection that
        # arrives through the edge connector, so it appears as J_PI, never as a device
        # sitting on the board -- including pin 6/9 GND, which is how the Pi's ground
        # reaches the signal pour. One defined tie, at one connector.
        src = '%s:%s' % (edge(r['dev']), r['pin'])
        dst = '%s:%s' % (edge(r['dst']), r['dstpin'] or '?')

        # grounds do not form point-to-point nets; they land in a pour
        if r['dir'] == 'ref' or 'GND' in r['pin'].upper() or 'ground' in r['sig'].lower():
            p = pour_of(edge(r["dev"]) if edge(r["dev"]).startswith("J_") else r["dev"])
            if p is None:
                unresolved.append('UNCLASSIFIED GROUND -- which pour? %s | %s' % (src, r['sig']))
            else:
                add(p, src)
            continue

        # the removed devices
        low = (r['dev'] + ' ' + r['dst']).lower()
        if 'mcp23017' in low:
            # THE MCP23017 IS GONE. Owner-confirmed 2026-09-30: the Picos replace it
            # fully, and it is not a historical note. Its twelve encoder lines are
            # synthesised below onto Pico A GP0-GP11 in the as-built order, and its
            # GPB4 reset onto Pico B GP15. Everything else about it -- VDD, the address
            # straps, RESET, GPB5-GPB7 -- has no successor and ceases to exist.
            # These rows are SUPERSEDED. They are not decisions waiting for a human.
            superseded.append('%s -> %s' % (src, dst))
            continue
        if 'hub' in low:
            add('I2C_SDA' if 'SDA' in r['sig'].upper() else
                'I2C_SCL' if 'SCL' in r['sig'].upper() else 'I2C_OTHER', src)
            continue

        net = re.sub(r'[^A-Za-z0-9]+', '_', (r['sig'] or 'N_%s' % src)).strip('_').upper()
        add(net, src)
        add(net, dst)

    # --- one ENCODER connector per wheel, four ways -------------------------------
    # Owner-directed 2026-09-30: NO MOTOR CONNECTORS ON THE BOARD. The motor pairs
    # stay on the FeatherWings' own screw terminals and never touch this PCB, so no
    # motor current crosses it and there is no high-current copper to size. Each
    # wheel's six-wire harness splits at the chassis: two thick to the FeatherWing,
    # four thin to its connector here.
    #
    # ⚠ ALL SIX MUST BE KEYED DIFFERENTLY. Six identical 4-way housings on six wheels
    #   is how the fourth transposition happens -- three are already on record, and
    #   the most recent was only untangled on 2026-09-29.
    for i, w in enumerate(ENCODER_ORDER):
        W, J = w.upper(), 'J_ENC_%s' % w.upper()
        add('ENC_%s_A' % W, 'PICO_A:GP%d' % (i * 2)); add('ENC_%s_A' % W, '%s:yellow' % J)
        add('ENC_%s_B' % W, 'PICO_A:GP%d' % (i * 2 + 1)); add('ENC_%s_B' % W, '%s:green' % J)
        add('ENC_3V3', '%s:blue' % J)          # encoder supply, R5 via the rail input
        add('GNDS', '%s:black' % J)            # encoder return -- signal pour

    # --- sonars and ToF: one board-mounted connector each -------------------------
    for s_ in ('F', 'L', 'R'):
        J = 'J_SONAR_%s' % s_
        add('N_5V', '%s:VCC' % J); add('GNDS', '%s:GND' % J)
        add('SONAR_%s_TRIG' % s_, '%s:TRIG' % J); add('SONAR_%s_TRIG' % s_, 'PICO_B:TRIG_%s' % s_)
        add('SONAR_%s_ECHO_RAW' % s_, '%s:ECHO' % J)   # into the divider, not the Pico
    add('N_3V3', 'J_TOF:VCC'); add('GNDS', 'J_TOF:GND')
    add('TOF_TX', 'J_TOF:TX'); add('TOF_TX', 'J_PI:pin 21 GP9')
    add('TOF_RX', 'J_TOF:RX'); add('TOF_RX', 'J_PI:pin 24 GP8')

    # --- the two UART links, 4.7 --------------------------------------------------
    for pico, a, b in (('PICO_A', 'GP12', 'GP13'), ('PICO_B', 'GP12', 'GP13')):
        add('%s_TX' % pico, '%s:%s' % (pico, a)); add('%s_TX' % pico, 'J_PI:%s_RX' % pico)
        add('%s_RX' % pico, '%s:%s' % (pico, b)); add('%s_RX' % pico, 'J_PI:%s_TX' % pico)

    # --- the Pi link: 2x20 SMD KEYED BOX HEADER, 40-way IDC ribbon ----------------
    # Owner-directed 2026-09-30. A shrouded, polarised header, so the ribbon cannot go
    # on backwards -- which matters on a rover with four reverse-polarity events on
    # record. It also decouples the board outline from wherever the Pi is mounted,
    # which is one of the three things blocking layout.
    #
    # THE EIGHT GROUND PINS ARE A REAL GAIN. Today the Pi's reference reaches the
    # boards through pin 6/9 -- two wires. Eight pins in parallel give a far lower
    # impedance tie between the Pi's ground and the signal pour, at exactly the
    # junction the star cares about.
    for gpin in (6, 9, 14, 20, 25, 30, 34, 39):
        add('GNDS', 'J_PI:pin %d GND' % gpin)

    # --- the BNO085 reset: 4.7 consequence 1, open-drain on Pico B GP15 -----------
    add('IMU_RST', 'PICO_B:GP15')
    add('IMU_RST', 'RRB1:2')
    add('IMU_RST', 'BNO085:RST')
    add('N_3V3', 'RRB1:1')

    with open(os.path.join(OUT, 'nets.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['net', 'pins', 'pin_list'])
        for n in sorted(nets):
            w.writerow([n, len(nets[n]), ' ; '.join(nets[n])])

    with open(os.path.join(OUT, 'unresolved.txt'), 'w', encoding='utf-8') as f:
        f.write('Rows this script could not place. Each one needs a human decision.\n')
        f.write('Generated %s\n\n' % datetime.date.today())
        for u in unresolved:
            f.write(u + '\n')
        f.write('\n\n--- SUPERSEDED, no decision needed ---\n')
        f.write('The MCP23017 is fully removed from the design; the Picos replace it.\n')
        f.write('Its encoder lines are synthesised onto Pico A GP0-GP11 in the as-built\n')
        f.write('order, its reset onto Pico B GP15. These document rows have no successor\n')
        f.write('on this board:\n\n')
        for u in superseded:
            f.write('  ' + u + '\n')

    # --- KiCad netlist ------------------------------------------------------------
    comps = sorted({p.split(':')[0] for pins in nets.values() for p in pins})
    with open(os.path.join(OUT, 'backplane.net'), 'w', encoding='utf-8') as f:
        f.write('(export (version "E")\n  (design (source "MHD 16.1") (date "%s")'
                ' (tool "gen_netlist.py"))\n' % datetime.date.today())
        f.write('  (components\n')
        for c in comps:
            ref = re.sub(r'[^A-Za-z0-9_]', '_', c)
            f.write('    (comp (ref "%s") (value "%s") (footprint "%s"))\n'
                    % (ref, c, footprint_for(ref)))
        f.write('  )\n  (nets\n')
        for i, n in enumerate(sorted(nets), 1):
            f.write('    (net (code "%d") (name "%s")\n' % (i, n))
            for p in nets[n]:
                d, _, pin = p.partition(':')
                f.write('      (node (ref "%s") (pin "%s"))\n'
                        % (re.sub(r'[^A-Za-z0-9_]', '_', d), pin or '1'))
            f.write('    )\n')
        f.write('  )\n)\n')

    print('%d rows read from 16.1' % len(rows))
    print('%d nets, %d components' % (len(nets), len(comps)))
    print('%d unresolved -- READ unresolved.txt' % len(unresolved))
    print('%d superseded MCP23017 rows -- no decision needed' % len(superseded))
    for n in ('GNDS', 'GNDP'):
        print('  %-5s %d pins' % (n, len(nets.get(n, []))))


if __name__ == '__main__':
    main()
