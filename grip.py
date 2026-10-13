import config,logsetup
log=logsetup.setup('grip')

# FR-1700-004/005/006 gripper and grasp sequence (2026-10-08). Replaces retrieval_task.py's old
# fixed primitive, which drove the gripper to 500/2500 us (it stalls at 1050 and 2210), jumped the
# shoulder 300 us and sent the elbow to 1500 us -- the position that destroyed an MG996R on
# 2026-09-17. The gripper now has POSITION FEEDBACK (servo pot wiper on ADS1115 A2, 2026-10-04,
# replacing the FSR402), and this module uses it.
#
# FEEDBACK IS READ AS A RATIO TO THE ARM RAIL. The pot is powered from the 6 V arm rail (R3), so
# its wiper voltage moves with the rail; 2026-10-05 the A2 reading "shifted between runs" for the
# same pulse. wiper / rail removes that (read_feedback below). No absolute calibration is needed:
# GripCloser only asks "is the jaw still following the command, or has something stopped it?".


def read_feedback(adc,current):
    """Pot wiper as a fraction of the arm rail, or None if either reading is unavailable."""
    try:
        v=adc.grip_feedback_volts()
        r=current.rail('arm_6v')['voltage_v']
        if v is None or r is None or r<config.GRIP_RAIL_MIN_V: return None
        return v/r
    except Exception:
        return None


class GripCloser:
    """Close the gripper in steps and decide what happened, from the feedback.

    gripped  -- the jaw stopped following the command before 'shut': something is in it. The
                command is left GRIP_SQUEEZE_US past where it stopped, so the object is held and
                the jaw will visibly move again if the object is pulled out (hand-off sensing).
    empty    -- the jaw followed all the way to GRIP_CLOSED_US: nothing is in it.
    unsensed -- no feedback readings: closes to GRIP_UNSENSED_US and says so; the caller must
                verify some other way (vision).

    Tick-driven: step() is called once per control tick and returns None until a result.
    """
    def __init__(self,set_pulse,feedback,open_us=None,closed_us=None):
        self.set_pulse=set_pulse; self.feedback=feedback
        self.open_us=open_us if open_us is not None else config.GRIP_OPEN_US
        self.closed_us=closed_us if closed_us is not None else config.GRIP_CLOSED_US
        self.cmd=self.open_us; self.fb0=None; self.hist=[]; self.result=None; self.held_us=None

    def step(self):
        if self.result: return self.result
        fb=self.feedback()
        if self.fb0 is None:
            self.fb0=fb; self.hist=[fb]
            if fb is None:
                self.set_pulse(config.GRIP_UNSENSED_US); self.cmd=config.GRIP_UNSENSED_US
                self.result='unsensed'; self.held_us=self.cmd
                log.warning('Gripper feedback unavailable: closed to GRIP_UNSENSED_US, grip not sensed')
                return self.result
            return None                      # first call only records the open-jaw reading
        if fb is not None: self.hist.append(fb)
        n=config.GRIP_STALL_STEPS
        moved=len(self.hist)>n and abs(self.hist[-1]-self.hist[-1-n])>=config.GRIP_FB_MIN_DELTA
        travelled=self.cmd-self.open_us
        if len(self.hist)>n and not moved and travelled>=config.GRIP_MIN_TRAVEL_US:
            # The command kept advancing over the last n steps and the jaw did not follow.
            stop_us=self.cmd-n*config.GRIP_CLOSE_STEP_US
            self.held_us=min(self.closed_us,stop_us+config.GRIP_SQUEEZE_US)
            self.set_pulse(self.held_us); self.cmd=self.held_us; self.result='gripped'
            log.info(f'Gripped: jaw stopped near {stop_us:.0f} us, holding at {self.held_us:.0f} us')
            return self.result
        if self.cmd>=self.closed_us:
            self.result='empty'; self.held_us=self.cmd
            log.info('Gripper closed fully: nothing in it')
            return self.result
        self.cmd=min(self.closed_us,self.cmd+config.GRIP_CLOSE_STEP_US)
        self.set_pulse(self.cmd)
        return None


def released_by_person(fb_at_hold,fb_now):
    """FR-1700-006 hand-off sensing: with the jaw held GRIP_SQUEEZE_US past the object, pulling the
    object out lets the jaw move -- the feedback changes. True once it has moved enough."""
    if fb_at_hold is None or fb_now is None: return False
    return abs(fb_now-fb_at_hold)>=config.GRIP_HANDOFF_DELTA


def _ramp(joint,a,b,last_delay=0.3):
    """Steps from a to b, ARM_WAVE_APPROACH_STEP_US apart (same as brain.RoverBrain._ramp)."""
    step=config.ARM_WAVE_APPROACH_STEP_US
    if a==b: return [(joint,b,last_delay)]
    d=step if b>a else -step
    return [(joint,v,config.ARM_WAVE_STEP_S) for v in range(a+d,b,d)]+[(joint,b,last_delay)]

def shoulder_ramp(a,b,last_delay=0.3):
    """A shoulder move from a to b on BOTH servos (CH2+CH3), in ARM_PAIR_STEP_US steps every
    ARM_PAIR_STEP_S, then CH3 dropped again (config.ARM_SHOULDER_PAIR note, 2026-10-13)."""
    step=config.ARM_PAIR_STEP_US; out=[('shoulder_pair',1,0.2)]
    if a!=b:
        d=step if b>a else -step
        out+=[('shoulder',v,config.ARM_PAIR_STEP_S) for v in range(a+d,b,d)]
    return out+[('shoulder',b,last_delay),('shoulder_pair',0,0.2)]

def reach_plan(base_us,shoulder_from,elbow_from,pose=None):
    """Arm steps (joint, us, delay_s) from wherever the arm is to the reach-down pose, honouring the
    owner's rule: OPEN THE ELBOW before the shoulder moves, shoulder in ARM_WAVE_APPROACH_STEP_US
    steps. Returns None when ARM_POSE_REACH has not been measured -- no guessed pose, ever."""
    reach=pose or config.ARM_POSE_REACH      # pose: from reach_table (taught spots), 2026-10-13
    if not reach or not config.ARM_SHOULDER_POSES_VERIFIED: return None
    if 'base' in reach: base_us=reach['base']   # rest/lift shoulder values too (10-12)
    # 2026-10-13 path, matching the measurement: stand the arm up (shoulder ARM_STOW_UPRIGHT_US),
    # set the elbow to the reach value THERE (1300 keeps the hand off the wheel), then step the
    # shoulder forward to the floor. Elbow and shoulder both stepped (a jump slams the joint).
    ramp=_ramp; up=config.ARM_STOW_UPRIGHT_US
    plan=[('gripper',config.GRIP_OPEN_US,0.3),('wrist_pitch',config.ARM_REST_WRIST_US,0.3)]
    plan+=shoulder_ramp(shoulder_from,up)
    plan+=([('elbow',reach['elbow'],0.6)] if elbow_from is None else ramp('elbow',elbow_from,reach['elbow']))
    plan+=[('base',base_us,0.4)]
    plan+=shoulder_ramp(up,reach['shoulder'])
    if 'wrist_pitch' in reach: plan.append(('wrist_pitch',reach['wrist_pitch'],0.3))
    return plan


def lift_plan(shoulder_from):
    """Back up to carry: shoulder in steps toward the rest shoulder; the elbow is not touched (it
    is holding the object's height and the gripper is shut on it)."""
    # 2026-10-13: up to UPRIGHT, not to rest -- lying back with the elbow open swings the hand
    # into his front. Stowing (with the object released) is a separate, later step.
    return shoulder_ramp(shoulder_from,config.ARM_STOW_UPRIGHT_US)
