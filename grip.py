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


def _ramp(joint,a,b,last_delay=0.3,step=None,dt=None):
    """Steps from a to b, ARM_WAVE_APPROACH_STEP_US apart (same as brain.RoverBrain._ramp)."""
    step=step or config.ARM_WAVE_APPROACH_STEP_US; dt=dt or config.ARM_WAVE_STEP_S
    if a==b: return [(joint,b,last_delay)]
    d=step if b>a else -step
    return [(joint,v,dt) for v in range(a+d,b,d)]+[(joint,b,last_delay)]

def shoulder_ramp(a,b,last_delay=0.3):
    """A shoulder move from a to b on BOTH servos (CH2+CH3), in ARM_PAIR_STEP_US steps every
    ARM_PAIR_STEP_S, then CH3 dropped again (config.ARM_SHOULDER_PAIR note, 2026-10-13)."""
    # Only FORWARD of upright (2026-10-13, measured): there the arm's weight hangs off the joint and
    # CH2 alone stalls (3.4 A lifting from the floor) while the pair does it at 0.3-1.6 A. At and
    # behind upright the pair FIGHTS (standing up from stow: 3.1 A at 1825 with both, 0.10 A with
    # CH2 alone), so those moves run on CH2 only.
    # ...and only LIFTING (b>a): going down, gravity does the work and CH2 alone lowered to the
    # floor at 0.3 A, while engaging CH3 at upright to go down locked them at 3.2 A (10-13).
    pair=b>a and a<config.ARM_STOW_UPRIGHT_US
    step=config.ARM_PAIR_STEP_US if pair else config.ARM_WAVE_APPROACH_STEP_US
    dt=config.ARM_PAIR_STEP_S if pair else config.ARM_WAVE_STEP_S*3
    out=[('shoulder_pair',1,0.2)] if pair else []
    if a!=b:
        d=step if b>a else -step
        out+=[('shoulder',v,dt) for v in range(a+d,b,d)]
    out.append(('shoulder',b,last_delay))
    return out+([('shoulder_pair',0,0.2)] if pair else [])

def object_height_cm(det):
    """Height of a detected object lined up at the reach spot, from its box (cm), or None. A box
    cut off by the bottom of the frame is measured by its width instead (round things)."""
    try:
        x1,y1,x2,y2=det['bbox']; fh=det['frame_h']
        px=(x2-x1) if y2>=fh*0.98 else (y2-y1)
        return px/config.RETRIEVAL_PX_PER_CM_AT_TARGET
    except Exception:
        return None

def reach_plan(base_us,shoulder_from,elbow_from,pose=None,object_cm=None):
    """Arm steps (joint, us, delay_s) from wherever the arm is to the reach-down pose, honouring the
    owner's rule: OPEN THE ELBOW before the shoulder moves, shoulder in ARM_WAVE_APPROACH_STEP_US
    steps. Returns None when ARM_POSE_REACH has not been measured -- no guessed pose, ever."""
    reach=pose or config.ARM_POSE_REACH      # pose: from reach_table (taught spots), 2026-10-13
    if not reach or not config.ARM_SHOULDER_POSES_VERIFIED: return None
    if 'base' in reach: base_us=reach['base']   # rest/lift shoulder values too (10-12)
    # 2026-10-13 path, matching the measurement: stand the arm up (shoulder ARM_STOW_UPRIGHT_US),
    # set the elbow to the reach value THERE (1300 keeps the hand off the wheel), then step the
    # shoulder forward to the floor. Elbow and shoulder both stepped (a jump slams the joint).
    # Owner 2026-10-13: "lift his arm before shifting left and right -- you cannot smash it on
    # the floor." With the elbow open the hand hangs near the floor even with the shoulder up, so
    # every base turn now happens with the ELBOW FOLDED (hand high). Then the shoulder goes
    # forward with the hand still folded up, and the elbow OPENS slowly to bring the open jaws
    # DOWN onto the object from above -- pausing at a hover height set from the object's size.
    ramp=_ramp; up=config.ARM_STOW_UPRIGHT_US; fold=config.ARM_POSE_REST['elbow']
    plan=[('gripper',config.GRIP_OPEN_US,0.3),('wrist_pitch',config.ARM_REST_WRIST_US,0.3)]
    plan+=fold_first(shoulder_from,elbow_from)                      # hand up before anything turns
    plan+=[('base',base_us,0.6)]
    plan+=shoulder_ramp(up,reach['shoulder'])                       # forward, still folded
    hover=reach['elbow']+(config.ARM_REACH_HOVER_ELBOW_US if object_cm is None else
          min(config.ARM_HOVER_MAX_US,int(config.ARM_ELBOW_US_PER_CM*(object_cm+config.ARM_HOVER_CLEARANCE_CM))))
    hover=min(hover,fold)
    plan+=ramp('elbow',fold,hover,step=25,dt=0.12,last_delay=0.8)    # down to hover
    plan+=[('elbow',v,config.ARM_REACH_LOWER_STEP_S)
           for v in range(hover-config.ARM_REACH_LOWER_STEP_US,reach['elbow'],-config.ARM_REACH_LOWER_STEP_US)]
    plan+=[('elbow',reach['elbow'],0.5)]
    if 'wrist_pitch' in reach: plan.append(('wrist_pitch',reach['wrist_pitch'],0.3))
    return plan


def fold_first(shoulder_from,elbow_from):
    """Get to upright with the elbow folded, never sweeping the hand low: if the arm is forward
    of upright, fold the elbow FIRST (hand comes up) then stand up; if it is back (stow side),
    stand up first then fold (folding there drives the forearm into his body, measured 10-12)."""
    up=config.ARM_STOW_UPRIGHT_US; fold=config.ARM_POSE_REST['elbow']
    def el(): return [('elbow',fold,0.6)] if elbow_from is None else _ramp('elbow',elbow_from,fold,step=25,dt=0.12)
    if shoulder_from<up: return el()+shoulder_ramp(shoulder_from,up)
    return shoulder_ramp(shoulder_from,up)+el()


def lift_plan(shoulder_from,elbow_from=None):
    """Lift the held object: fold the elbow (hand straight up off the floor), then stand the arm
    up (2026-10-13: lifting the shoulder alone left the hand near the floor)."""
    return fold_first(shoulder_from,elbow_from)
