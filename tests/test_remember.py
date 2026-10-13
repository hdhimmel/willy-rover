import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest

# 2026-10-13: "Remember, my name is Howard" went to the local model (5 s) and was lost.

class FakeMemory:
    def __init__(self): self.facts={}; self.ins=[]
    def add_fact(self,k,v): self.facts[k]=v
    def all_facts(self): return dict(self.facts)
    def all_instructions(self): return list(self.ins)
    def add_instruction(self,t,a): self.ins.append({'id':len(self.ins),'trigger_phrase':t,'action_text':a})

def _voice(person=None):
    import voice
    v=object.__new__(voice.VoicePipeline)
    v.memory=FakeMemory(); v.said=[]; v.speak=lambda t,**k: v.said.append(t)
    v.current_person=lambda: person
    return v

@pytest.mark.parametrize('said',['Remember, my name is Howard.','remember my name is Howard',
                                 'My name is Howard','call me Howard','I want you to remember that my name is Howard'])
def test_name_is_stored(said):
    v=_voice()
    assert v._maybe_learn(said)
    assert v.memory.facts['my name']=='Howard' and 'Howard' in v.said[-1]

def test_whats_my_name_from_memory_or_face():
    v=_voice(); assert v._maybe_learn("what's my name") and "don't know" in v.said[-1]
    v._maybe_learn('my name is Howard'); v._maybe_learn('what is my name')
    assert 'Howard' in v.said[-1]
    v=_voice(person='Carolyn'); v._maybe_learn('who am i')
    assert v.said[-1]=="You're Carolyn."

@pytest.mark.parametrize('said,key',[('remember the spare batteries are in the blue bin','the spare batteries are in the blue bin'),
                                     ('Remember that the keys are on the hook','the keys are on the hook'),
                                     ('please remember: dinner is at six','dinner is at six')])
def test_other_facts_are_stored(said,key):
    v=_voice(); assert v._maybe_learn(said)
    assert key in v.memory.facts

def test_remember_my_name_alone_asks_and_pose_save_is_not_a_fact():
    v=_voice(); assert v._maybe_learn('I want you to remember my name.')
    assert v.memory.facts=={} and 'my name is' in v.said[-1]
    assert not v._maybe_learn('remember this as knock') and v.memory.facts=={}
