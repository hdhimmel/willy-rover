import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from voice import answer_is_yes

# 2026-10-15: "yes" to "I would like to go explore. Is that okay?" kept being logged as declined.

@pytest.mark.parametrize('t',['Yes.','Yeah!','Yep','Sure.','Okay.','OK','Go ahead.','Go for it.','Of course.',
                              'Alright','All right.','Yes please.','Go.','You can.','Absolutely','Yup.'])
def test_yes(t): assert answer_is_yes(t)

@pytest.mark.parametrize('t',['No.','Nope','Not now.',"No, don't go.","Don't go",'Maybe later.','Wait.',
                              'Stop.','Thank you.','','What?'])
def test_no(t): assert not answer_is_yes(t)

def test_roam_intent_is_yes(): assert answer_is_yes('Go explore!','roam')
