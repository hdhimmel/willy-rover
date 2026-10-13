import os,sys,types,queue,threading
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import pytest
import config,teach

# Teaching by voice (2026-10-13): arm poses (jog / save / go) and multi-step routines.

class Clock:
    def __init__(self,t=1000.0): self.t=t
    def __call__(self): return self.t

@pytest.fixture(autouse=True)
def _mem(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WILLY_MEMORY_ROOT',str(tmp_path))
    monkeypatch.setattr(config,'ARM_JOINT_LIMITS_US',{})
    monkeypatch.setattr(config,'SIMULATE_HARDWARE',True)   # another test may leave it off

# ---------------------------------------------------------------- ArmTeacher

def test_first_jog_of_an_undriven_joint_starts_it_instead_of_stepping_a_placeholder():
    t=teach.ArmTeacher(); t.start()
    assert t.jog('shoulder','up',None)==('shoulder',config.ARM_TEACH_START_US['shoulder'])
    assert t.jog('shoulder','up',1500)==('shoulder',1500+config.ARM_TEACH_STEP_US)
    assert t.jog('shoulder','down',1500)==('shoulder',1500-config.ARM_TEACH_STEP_US)

def test_more_repeats_the_last_jog_and_step_size_changes():
    t=teach.ArmTeacher(); t.start()
    assert t.again(lambda j:1500)[0] is None                 # nothing to repeat yet
    t.jog('wrist_pitch','up',1500)
    t.set_step('big')
    assert t.again(lambda j:1500)==('wrist_pitch',1500-config.ARM_TEACH_STEP_SIZES_US['big'])

def test_limits_and_unknown_directions_are_refused(monkeypatch):
    monkeypatch.setattr(config,'ARM_JOINT_LIMITS_US',{'elbow':(1000,2000)})
    t=teach.ArmTeacher(); t.start()
    j,why=t.jog('elbow','up',2000)
    assert j is None and 'further' in why
    j,why=t.jog('shoulder','left',1500)
    assert j is None and "can't move" in why

def test_teach_mode_times_out():
    clk=Clock(); t=teach.ArmTeacher(clock=clk); t.start()
    clk.t+=config.ARM_TEACH_IDLE_S+1
    assert t.timed_out()

# ---------------------------------------------------------------- poses

def test_pose_round_trip_and_epoch_refusal(monkeypatch):
    teach.save_pose('knock',{'shoulder':1600,'elbow':1800})
    pulses,why=teach.get_pose('knock')
    assert why is None and pulses=={'shoulder':1600,'elbow':1800}
    monkeypatch.setattr(config,'ARM_POSE_EPOCH','later')
    pulses,why=teach.get_pose('knock')
    assert pulses is None and 'changed' in why             # servo/horn changed since: refused
    assert teach.get_pose('nope')[0] is None
    assert teach.forget_pose('knock') and not teach.forget_pose('knock')

def test_pose_plan_moves_elbow_first_in_steps_and_sends_unknown_joints_straight():
    plan=teach.pose_plan({'shoulder':1600,'elbow':1700,'gripper':1150},
                         {'shoulder':1500,'elbow':1500,'gripper':None})
    joints=[p[0] for p in plan]
    assert joints.index('elbow')<joints.index('shoulder')<joints.index('gripper')
    el=[u for j,u,_ in plan if j=='elbow']
    assert el[-1]==1700 and all(abs(b-a)<=config.ARM_WAVE_APPROACH_STEP_US for a,b in zip([1500]+el,el))
    assert [p for p in plan if p[0]=='gripper']==[('gripper',1150,0.4)]
    assert teach.pose_plan({'shoulder':1500},{'shoulder':1500})==[]

# ---------------------------------------------------------------- routines

def test_split_steps():
    assert teach.split_steps('stow your arm, then go home, and then wave')==['stow your arm','go home','wave']
    assert teach.split_steps('wave')==['wave']

def test_runner_waits_for_free_then_steps_and_finishes():
    clk=Clock(); r=teach.RoutineRunner(clock=clk)
    r.start('goodnight',['a','b'])
    assert r.tick(True) is None                              # free just now: wait the gap
    clk.t+=config.ROUTINE_STEP_GAP_S
    assert r.tick(True)=='a'
    assert r.tick(False) is None                             # step running
    assert r.tick(True) is None; clk.t+=config.ROUTINE_STEP_GAP_S
    assert r.tick(True)=='b'
    assert r.tick(True) is None; clk.t+=config.ROUTINE_STEP_GAP_S
    assert r.tick(True) is None and not r.active             # finished

def test_runner_abandons_a_step_that_never_finishes():
    clk=Clock(); r=teach.RoutineRunner(clock=clk)
    r.start('x',['a','b']); clk.t+=config.ROUTINE_STEP_GAP_S
    r.tick(True); r.tick(True)
    clk.t+=config.ROUTINE_STEP_TIMEOUT_S+1
    assert r.tick(False) is None and not r.active

# ---------------------------------------------------------------- voice

class FakeMemory:
    def __init__(self): self.ins=[]
    def add_instruction(self,t,a): self.ins.append({'id':len(self.ins),'trigger_phrase':t,'action_text':a})
    def all_instructions(self): return list(self.ins)

def _voice():
    import voice
    v=object.__new__(voice.VoicePipeline)
    v.memory=FakeMemory(); v.said=[]; v.speak=lambda t,**k: v.said.append(t)
    return v

@pytest.mark.parametrize('said,intent,args',[
    ('teach your arm','arm_teach',{}),('done teaching','arm_teach_done',{}),
    ('shoulder up','arm_jog',{'joint':'shoulder','dir':'up'}),('wrist left','arm_jog',{'joint':'wrist_rot','dir':'left'}),
    ('arm right','arm_jog',{'joint':'base','dir':'right'}),('close your hand','arm_jog',{'joint':'gripper','dir':'close'}),
    ('a bit more','arm_more',{}),('smaller steps','arm_step',{'size':'small'}),
    ('remember this as knock','pose_save',{'name':'knock'}),('show me pose knock','pose_go',{'name':'knock'}),
    ('forget the pose knock','pose_forget',{'name':'knock'}),('what poses do you know','pose_list',{})])
def test_phrases(said,intent,args):
    r=_voice()._fast_path(said)
    assert r['intent']==intent and r['args']==args

def test_existing_arm_and_stop_phrases_unchanged():
    v=_voice()
    assert v._fast_path('stow your arm')['intent']=='arm_stow'
    assert v._fast_path('arm home')['intent']=='arm_home'
    assert v._fast_path('stop')['intent']=='stop'

def test_routine_is_validated_when_taught():
    v=_voice()
    assert v._maybe_learn('when I say goodnight, do stow your arm, then fly to the moon')
    assert v.memory.ins==[] and "don't know how to" in v.said[-1]
    assert v._maybe_learn('when I say goodnight, do stow your arm, then wave')
    assert v.memory.ins[0]['action_text']=='stow your arm, then wave'

def test_a_multi_step_trigger_becomes_one_routine_intent_and_single_step_is_unchanged():
    v=_voice()
    v.memory.add_instruction('goodnight','stow your arm, then wave')
    v.memory.add_instruction('hi there','wave')
    r=v._routine_intent(v.memory.all_instructions()[0])
    assert r['intent']=='routine' and [s['intent'] for s in r['args']['steps']]==['arm_stow','wave']
    assert v._routine_intent(v.memory.all_instructions()[1]) is None
    assert v.interpret_text('goodnight')['intent']=='routine'

# ---------------------------------------------------------------- brain

class FakeArm:
    def __init__(self): self.p={}; self.released=False; self.log=[]; self.alive=0
    def set_pulse(self,j,us): self.p[j]=us; self.log.append((j,us))
    def pulse(self,j): return self.p.get(j,1500)
    def was_driven(self,j): return j in self.p
    @property
    def joints(self): return ['base','shoulder','elbow','wrist_rot','wrist_pitch','gripper']
    def keep_alive(self): self.alive+=1

def _brain():
    from brain import RoverBrain
    b=types.SimpleNamespace(arm=FakeArm(),teacher=teach.ArmTeacher(),routine=teach.RoutineRunner(),
                            _state='IDLE',said=[],started=[])
    b._say=b.said.append
    b.voice=types.SimpleNamespace(pending_commands=queue.Queue(),_speaking=threading.Event())
    b._start_arm_sequence=b.started.append
    for m in ('_teach_cmd','_arm_now','_teach_tick','_routine_step'):
        setattr(b,m,types.MethodType(getattr(RoverBrain,m),b))
    return b

def test_brain_jog_needs_teach_mode_then_moves_one_joint():
    b=_brain()
    b._teach_cmd({'intent':'arm_jog','args':{'joint':'shoulder','dir':'up'}})
    assert b.arm.log==[] and 'teach your arm' in b.said[-1]
    b._teach_cmd({'intent':'arm_teach','args':{}})
    b._teach_cmd({'intent':'arm_jog','args':{'joint':'shoulder','dir':'up'}})
    b._teach_cmd({'intent':'arm_more','args':{}})
    assert [x for x in b.arm.log if x[0]!='shoulder_pair']==[('shoulder',1500),('shoulder',1500+config.ARM_TEACH_STEP_US)]
    assert ('shoulder_pair',1) in b.arm.log                    # both servos while teaching the shoulder
    b._teach_tick(); assert b.arm.alive==1                   # no idle release while teaching

def test_brain_saves_only_known_joints_and_refuses_after_release():
    b=_brain()
    b._teach_cmd({'intent':'pose_save','args':{'name':'knock'}})
    assert "don't know where" in b.said[-1]
    b.arm.p={'shoulder':1600,'elbow':1800}
    b._teach_cmd({'intent':'pose_save','args':{'name':'knock'}})
    assert teach.get_pose('knock')[0]=={'shoulder':1600,'elbow':1800}
    b.arm.released=True                                       # it fell: pulses no longer true
    b._teach_cmd({'intent':'pose_save','args':{'name':'other'}})
    assert teach.get_pose('other')[0]=={'elbow':1800}         # ...except the elbow, which holds unpowered

def test_brain_goes_to_a_pose_with_a_stepped_sequence():
    b=_brain(); teach.save_pose('knock',{'shoulder':1600})
    b.arm.p={'shoulder':1500}
    b._teach_cmd({'intent':'pose_go','args':{'name':'knock'}})
    assert b.started and b.started[0][-1]==('shoulder',1600,0.3)

def test_brain_routine_steps_are_queued_through_the_normal_path():
    b=_brain()
    b.routine.start('goodnight',[{'intent':'arm_stow','args':{},'text':'stow your arm','reply':''},
                                 {'intent':'time','args':{},'text':'what time is it','reply':"It's noon."}])
    b.routine._free_since=0.0
    b._teach_tick()
    cmd=b.voice.pending_commands.get_nowait()
    assert cmd['intent']=='arm_stow' and cmd['source']=='routine'
    b.routine._free_since=0.0
    b._teach_tick()
    assert b.said[-1]=="It's noon." and b.voice.pending_commands.empty()
