import time,config,logsetup
log=logsetup.setup('knock')

# FR-1000-006 knock at a shut door (2026-10-08). The design (FRD FR-1000-006, §4.7): "a bounded,
# timed arm oscillation from a sonar-measured standoff -- never 'move until contact'". So this is
# a FIXED list of (joint, us, delay) steps, played open-loop: approach, ARM_KNOCK_TAPS taps of
# ARM_KNOCK_TAP_US, back to rest. Nothing here waits for or senses contact; the arm rail monitor
# is a protection limit (brain._check_arm_current releases the arm), not a contact detector.
#
# ARM_POSE_KNOCK is NOT MEASURED (None), like ARM_POSE_REACH: until it is jogged with the owner
# watching, knock_plan() returns None and the navigator keeps its ask-only behaviour -- the
# spec's own rule for a missing arm. No guessed pose, ever.
#
# Same owner rule as every arm move: OPEN THE ELBOW before the shoulder moves (or the arm strikes
# the top of Willy), shoulder in ARM_WAVE_APPROACH_STEP_US steps.

def _ramp(a,b):
    step=config.ARM_WAVE_APPROACH_STEP_US; d=step if b>a else -step
    return [('shoulder',v,config.ARM_WAVE_STEP_S) for v in range(a+d,b,d)]+[('shoulder',b,0.3)]

def return_plan(shoulder_from,elbow_from):
    """Back to ARM_POSE_REST from anywhere; same order as brain._rest_plan()."""
    r=config.ARM_POSE_REST; open_us=config.ARM_POSE_WAVE_HELLO['elbow']; plan=[]
    if shoulder_from!=r['shoulder'] and (elbow_from is None or elbow_from>open_us):
        plan.append(('elbow',open_us,0.6))
    if shoulder_from!=r['shoulder']: plan+=_ramp(shoulder_from,r['shoulder'])
    return plan+[('elbow',min(r['elbow'],config.ARM_SERVO_MAX_US),0.6),('wrist_pitch',config.ARM_REST_WRIST_US,0.0)]

def knock_plan(shoulder_from,elbow_from):
    """The whole knock, approach to rest, or None while ARM_POSE_KNOCK is unmeasured."""
    k=config.ARM_POSE_KNOCK
    if not k: return None
    open_us=config.ARM_POSE_WAVE_HELLO['elbow']
    plan=[]
    if elbow_from is None or elbow_from>open_us: plan.append(('elbow',open_us,0.6))
    plan+=_ramp(shoulder_from,k['shoulder'])
    plan.append(('elbow',k['elbow'],0.5))
    j=config.ARM_KNOCK_TAP_JOINT
    base=k.get(j,config.ARM_POSE_WAVE_HELLO.get(j,config.ARM_SERVO_CENTER_US))
    plan.append((j,base,0.3))
    for _ in range(config.ARM_KNOCK_TAPS):
        plan+=[(j,base+config.ARM_KNOCK_TAP_US,config.ARM_KNOCK_TAP_S),(j,base,config.ARM_KNOCK_TAP_S)]
    return plan+return_plan(k['shoulder'],k['elbow'])

def standoff_ok(front_cm):
    lo,hi=config.ARM_KNOCK_STANDOFF_CM
    return front_cm is not None and lo<=front_cm<=hi


class KnockPlayer:
    """Plays a plan one step per due tick. tick() -> 'running' | 'done' | 'released'. The arm
    being released mid-knock (current limit) ends it at once: re-driving would wake the chip."""
    def __init__(self,arm,plan):
        self.arm=arm; self.plan=list(plan); self.i=0; self._due=0.0; self.homing=False

    def tick(self,now=None):
        now=now if now is not None else time.time()
        if self.arm.released and self.i>0: return 'released'
        if self.i>=len(self.plan): return 'done'
        if now<self._due: return 'running'
        joint,us,delay=self.plan[self.i]
        self.arm.set_pulse(joint,us); self.i+=1; self._due=now+delay
        return 'running' if self.i<len(self.plan) else 'done'

    def go_home(self):
        """The door opened mid-knock: skip the remaining taps, return to rest from here."""
        if self.homing: return
        self.homing=True
        sh=int(self.arm.pulse('shoulder')); el=int(self.arm.pulse('elbow'))
        self.plan=self.plan[:self.i]+return_plan(sh,el)
