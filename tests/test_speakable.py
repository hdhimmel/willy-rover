import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest

# 2026-10-10 (owner): he said "asterisk" -- cloud replies carry markdown and Piper reads it.

@pytest.mark.parametrize('raw,said',[
    ('Grass is green because of *chlorophyll*.','Grass is green because of chlorophyll.'),
    ('**Short answer:** it reflects green light.','Short answer: it reflects green light.'),
    ('# Why\n- it absorbs red\n- and blue','Why it absorbs red and blue'),
    ('See [the article](https://example.com) for more.','See the article for more.'),
    ('Use `python` here','Use python here'),
    ("I'm at 11.4 volts, about 50 percent.","I'm at 11.4 volts, about 50 percent."),   # ordinary text untouched
])
def test_markup_is_not_spoken(raw,said):
    import voice
    assert voice.speakable(raw)==said
