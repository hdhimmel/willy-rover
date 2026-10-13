import json,os,re,time,config,logsetup
log=logsetup.setup('teach')

# Teaching by voice (owner, 2026-10-13). Two things:
#
# 1. ARM POSES. "Teach your arm" -> "shoulder up", "more", "elbow down", ... -> "remember this as
#    knock". Each jog is one ARM_TEACH_STEP_US step on one joint, through Arm.set_pulse (so the
#    per-joint limits and the shoulder pair apply) and under the brain's every-tick current guard.
#    The servos cannot report where they are, so a pose is the pulses WE sent, never a reading:
#    moving the arm by hand teaches nothing. Saved poses carry ARM_POSE_EPOCH; after a servo or
#    horn change the epoch is bumped and every older pose is refused rather than replayed wrong.
#
# 2. ROUTINES. "When I say goodnight, do stow your arm, then go home, then ..." -- the existing
#    FR-1900-007 instruction store, extended to several steps. Every step must be something the
#    fast path already understands (checked when taught, not when run), and each one runs through
#    the brain's normal command path with all its gating. The next step starts only once the
#    brain is back in IDLE; "stop" abandons the rest.


# ---------------------------------------------------------------- arm poses

def _poses_path(): return os.path.join(config.WILLY_MEMORY_ROOT,config.ARM_POSES_PATH)

def load_poses():
    try:
        with open(_poses_path()) as f: d=json.load(f)
        return d if isinstance(d,dict) else {}
    except (OSError,ValueError): return {}

def save_pose(name,pulses):
    d=load_poses()
    d[name]={'pulses':{j:int(u) for j,u in pulses.items()},'epoch':config.ARM_POSE_EPOCH,'t':time.time()}
    with open(_poses_path(),'w') as f: json.dump(d,f,indent=1)

def forget_pose(name):
    d=load_poses()
    if name not in d: return False
    del d[name]
    with open(_poses_path(),'w') as f: json.dump(d,f,indent=1)
    return True

def get_pose(name):
    """(pulses, None) or (None, reason the pose cannot be used)."""
    p=load_poses().get(name)
    if not p: return None,f"I don't know a pose called {name}."
    if p.get('epoch')!=config.ARM_POSE_EPOCH:
        return None,f"My arm has changed since I learned {name}. Teach it to me again."
    return p['pulses'],None

# Order a pose is approached in: the elbow first (owner rule: open it before the shoulder moves),
# then the shoulder, then the light joints.
_APPROACH_ORDER=('elbow','shoulder','wrist_pitch','wrist_rot','base','gripper')

def pose_plan(target,current):
    """Arm steps (joint, us, delay_s) to `target`. current[joint] is the pulse now, or None if the
    joint has not been driven this boot -- its position is unknown, so it is sent straight to the
    target (one move: it was taught there, on this hardware)."""
    step=config.ARM_WAVE_APPROACH_STEP_US; plan=[]
    for j in _APPROACH_ORDER:
        if j not in target: continue
        b=int(target[j]); a=current.get(j)
        if a is None: plan.append((j,b,0.4)); continue
        a=int(a)
        if a==b: continue
        d=step if b>a else -step
        plan+=[(j,v,config.ARM_WAVE_STEP_S) for v in range(a+d,b,d)]+[(j,b,0.3)]
    return plan


class ArmTeacher:
    """Jog state for one teaching session. jog() returns (joint, new_pulse) for the brain to send,
    or (None, reason)."""
    def __init__(self,clock=time.time):
        self.clock=clock; self.active=False; self.last=None
        self.step=config.ARM_TEACH_STEP_US; self.touched={}; self._t=0.0
    def start(self): self.active=True; self.last=None; self.step=config.ARM_TEACH_STEP_US; self.touched={}; self._t=self.clock()
    def end(self): self.active=False; self.last=None
    def note(self): self._t=self.clock()
    def timed_out(self): return self.active and self.clock()-self._t>config.ARM_TEACH_IDLE_S
    def set_step(self,size):
        self.step=config.ARM_TEACH_STEP_SIZES_US.get(size,self.step); self.note(); return self.step
    def jog(self,joint,direction,current_us):
        """current_us None = joint not driven this boot: start it at ARM_TEACH_START_US instead
        of stepping from a placeholder."""
        sign=config.ARM_TEACH_DIRECTIONS.get(joint,{}).get(direction)
        if sign is None: return None,f"I can't move my {joint.replace('_',' ')} {direction}."
        self.note(); self.last=(joint,direction)
        if current_us is None:
            us=config.ARM_TEACH_START_US[joint]
        else:
            us=int(current_us)+sign*self.step
        lo,hi=config.ARM_JOINT_LIMITS_US.get(joint,(config.ARM_SERVO_MIN_US,config.ARM_SERVO_MAX_US))
        if not lo<=us<=hi:
            return None,f"My {joint.replace('_',' ')} can't go any further {direction}."
        self.touched[joint]=us
        return joint,us
    def again(self,current_of):
        if not self.last: return None,"I haven't moved anything yet."
        j,d=self.last
        return self.jog(j,d,current_of(j))


# ---------------------------------------------------------------- routines

_THEN=re.compile(r'\s*(?:,\s*|\s)(?:and\s+)?then\s+|\s*,\s*and\s+then\s+',re.I)

def split_steps(action_text):
    """'stow your arm, then go home, then wave' -> ['stow your arm','go home','wave']."""
    return [s.strip(' ,.') for s in _THEN.split(action_text.strip()) if s.strip(' ,.')]


class RoutineRunner:
    """Runs a routine's steps one at a time. tick() is called every brain tick with whether the
    brain is free (IDLE, nothing queued, not speaking); it returns the next step to dispatch,
    or None. A step that keeps the brain busy past ROUTINE_STEP_TIMEOUT_S abandons the rest."""
    def __init__(self,clock=time.time):
        self.clock=clock; self.name=None; self.steps=[]; self._free_since=None; self._step_t=0.0
    @property
    def active(self): return self.name is not None
    def start(self,name,steps):
        self.name=name; self.steps=list(steps); self._free_since=None; self._step_t=self.clock()
    def abandon(self,why):
        if self.active: log.info(f'Routine "{self.name}" abandoned: {why} ({len(self.steps)} steps left)')
        self.name=None; self.steps=[]
    def tick(self,free):
        if not self.active: return None
        now=self.clock()
        if not free:
            self._free_since=None
            if now-self._step_t>config.ROUTINE_STEP_TIMEOUT_S: self.abandon('step timed out')
            return None
        if self._free_since is None: self._free_since=now; return None
        if now-self._free_since<config.ROUTINE_STEP_GAP_S: return None
        if not self.steps:
            log.info(f'Routine "{self.name}" finished'); self.name=None; return None
        self._free_since=None; self._step_t=now
        return self.steps.pop(0)
