import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import sensors

# The encoder wheel order lives in three places that cannot import each other:
#
#   firmware/pico_a.py     WHEELS      -- MicroPython, runs on the Pico, decides the
#                                         order the $E frame is BUILT in
#   sensors.py             Encoders._ORDER -- the Pi, decides how it is READ
#   firmware/README.md     the $E line  -- what a human copies from
#
# On 2026-09-29 the first was corrected to the as-built J3 landing of Master Hardware
# Design §16.6 -- lf, lm, rf, rm, lr, rr -- after proving it on hardware one wheel at a
# time on blocks. The README was NOT corrected, and on 2026-09-30
# scripts/encoder_calibration.py copied the stale order straight out of it. A calibration
# run would then have measured one wheel correctly and written the answer against the
# wheel on the OTHER SIDE of the rover.
#
# Nothing caught it. Three transpositions are already on this rover's record; this would
# have been the fourth, in the one script whose entire job is attributing counts to the
# right wheel.
#
# So the three are pinned to each other here. This test is cheap, it needs no hardware,
# and it is the only thing standing between a future edit and a silent left/right swap.

_AS_BUILT = ('lf', 'lm', 'rf', 'rm', 'lr', 'rr')

_FIRMWARE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'firmware', 'pico_a.py')
_README = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'firmware', 'README.md')


def _firmware_order():
    src = open(_FIRMWARE, 'r', encoding='utf-8').read()
    m = re.search(r'^WHEELS\s*=\s*\(([^)]*)\)', src, re.M)
    assert m, 'firmware/pico_a.py has no WHEELS tuple -- has it been renamed?'
    return tuple(re.findall(r'"([a-z]{2})"|\'([a-z]{2})\'', m.group(1))[i][0] or
                 re.findall(r'"([a-z]{2})"|\'([a-z]{2})\'', m.group(1))[i][1]
                 for i in range(len(re.findall(r'"([a-z]{2})"|\'([a-z]{2})\'', m.group(1)))))


def _readme_order():
    src = open(_README, 'r', encoding='utf-8').read()
    m = re.search(r'\$E,<seq>,<ms>,((?:<[a-z0-9]+>,){6})', src)
    assert m, 'firmware/README.md has no $E frame line -- has the protocol section moved?'
    return tuple(re.findall(r'<([a-z]{2})>', m.group(1)))


def _firmware_dict(name):
    src = open(_FIRMWARE, 'r', encoding='utf-8').read()
    m = re.search(r'^' + name + r'\s*=\s*\{([^}]*)\}', src, re.M)
    assert m, f'firmware/pico_a.py has no {name} dict'
    return {k: int(v) for k, v in re.findall(r'"([a-z]{2})":\s*(\d+)', m.group(1))}


def test_each_frame_slot_reads_its_physical_pins():
    """The label tuples agreeing is not enough. On 2026-09-29 WHEELS was reordered and the
    pin dicts were not, so slot "lf" read GP4 -- the right front -- and the two tests above
    still passed. Measured over USB 2026-10-01: lf GP0/1, lm GP2/3, rf GP4/5, rm GP6/7,
    lr GP8/9, rr GP10/11, which is slot i on GP 2i (A) and 2i+1 (B)."""
    a, b = _firmware_dict('PHASE_A'), _firmware_dict('PHASE_B')
    for i, w in enumerate(_firmware_order()):
        assert (a[w], b[w]) == (2 * i, 2 * i + 1), f'{w} in slot {i} reads GP{a[w]}/GP{b[w]}'


def test_the_pi_reads_the_order_the_firmware_writes():
    assert sensors.Encoders._ORDER == _firmware_order()


def test_the_readme_documents_the_order_the_firmware_writes():
    """The README is what a human copies from, and one did. That is how the calibration
    script got the wrong order on 2026-09-30."""
    assert _readme_order() == _firmware_order()


def test_the_order_is_the_as_built_landing():
    """§16.6's as-built J3 table, confirmed on hardware 2026-09-29: driving lf counted on
    GP0/GP1, rf on GP4/GP5, lm on GP2/GP3, rm on GP6/GP7, rr on GP10/GP11. Five for five.

    If this test fails because someone believes the order is wrong, the way to settle it
    is to drive one wheel and watch which channel moves -- not to edit this tuple. No unit
    test can see which wheel actually turned."""
    assert sensors.Encoders._ORDER == _AS_BUILT


def test_the_calibration_script_does_not_keep_its_own_copy():
    """It used to, and the copy was wrong. It now imports sensors.Encoders._ORDER."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'scripts', 'encoder_calibration.py')
    src = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'^_WHEELS\s*=\s*(.+)$', src, re.M)
    assert m, 'encoder_calibration.py has no _WHEELS'
    assert 'sensors.Encoders._ORDER' in m.group(1), (
        'encoder_calibration.py has gone back to a local copy of the wheel order: %r'
        % m.group(1))
