import os,sys,types
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import config

# FR-600-004 manual steering override: takes effect in the same control cycle, clamped to the
# travel limits, parked only, held in IDLE, ended on leaving IDLE (centred) or a fault (released).

class _Steer:
    def __init__(self): self.pulses={}; self.log=[]
    def set_pulse(self,c,us): self.pulses[c]=us; self.log.append(('pulse',c,us))
    def center_all(self): self.log.append('centre')
    def release(self): self.log.append('release')

def test_pulses_front_one_way_rear_the_other_and_clamped():
    from steer_override import override_pulses
    from rotate import corner_us
    p,d=override_pulses(20)
    assert d==20 and p['lf']==corner_us('lf',20) and p['rr']==corner_us('rr',-20)
    assert p['lm']==config.STEER_CENTER_US['lm']
    p,d=override_pulses(90)
    assert d==config.STEER_OVERRIDE_MAX_DEG
    assert all(config.SERVO_MIN_US<=us<=config.SERVO_MAX_US for us in p.values())

def test_apply_writes_at_once_and_holds_in_idle():
    from steer_override import SteerOverride
    s=_Steer(); o=SteerOverride(s)
    o.apply(-15,now=0.0)
    assert len(s.log)==6                       # written in the same call: one control cycle
    o.tick('IDLE',now=0.1); assert len(s.log)==6
    o.tick('IDLE',now=config.ROTATE_RESTEER_S+0.01); assert len(s.log)==12   # re-asserted
    assert o.active

def test_leaving_idle_centres_and_a_fault_releases():
    from steer_override import SteerOverride
    s=_Steer(); o=SteerOverride(s); o.apply(10,now=0.0)
    o.tick('MANUAL',now=0.1)
    assert not o.active and s.log[-1]=='centre'
    s=_Steer(); o=SteerOverride(s); o.apply(10,now=0.0)
    o.tick('TILT_FAULT',now=0.1)
    assert not o.active and s.log[-1]=='release'

def test_safety_refuses_while_wheels_turn_or_motion_disabled():
    from safety import approve_steer,Rejected,ApprovedMotion
    assert isinstance(approve_steer(10,wheels_moving=True),Rejected)
    assert isinstance(approve_steer(10,wheels_moving=False,motion_enabled=False),Rejected)
    assert isinstance(approve_steer(10,wheels_moving=False,tilt_deg=config.IMU_TILT_LIMIT+1),Rejected)
    r=approve_steer(-80,wheels_moving=False,front_cm=0.0)
    assert isinstance(r,ApprovedMotion) and r.speed==-config.STEER_OVERRIDE_MAX_DEG

def test_voice_phrases():
    from voice import VoicePipeline
    v=object.__new__(VoicePipeline)
    fp=v._fast_path
    assert fp('steer left')['args']=={'degrees':-config.STEER_OVERRIDE_DEFAULT_DEG}
    assert fp('Willie, steer right 20 degrees')=={'intent':'steer','args':{'degrees':20.0},'reply':''}
    assert fp('wheels straight')['args']=={'degrees':0}
    assert fp('straighten your wheels')['intent']=='steer'
    assert fp('turn left')['intent']!='steer'
