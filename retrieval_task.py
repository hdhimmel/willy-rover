import time,config,logsetup,grip,reach_table,arm_ik,odometry


def base_for_x(x):
    """Arm base pulse whose jaws land at image x (RETRIEVAL_BASE_X_MAP, linear, clamped)."""
    pts=sorted(config.RETRIEVAL_BASE_X_MAP,key=lambda p:p[1])
    if x<=pts[0][1]: return pts[0][0]
    if x>=pts[-1][1]: return pts[-1][0]
    for (b0,x0),(b1,x1) in zip(pts,pts[1:]):
        if x0<=x<=x1: return int(round(b0+(b1-b0)*(x-x0)/(x1-x0)))
log=logsetup.setup('retrieval')

# FR-1700 Object Detection and Retrieval Task — the "core mission" per the FRD. This is a
# sub-state-machine driven by RoverBrain as its own top-level FSM state ('RETRIEVE'), the same
# way DOCK/AVOID/STUCK are — see brain.py's _retrieve(). It never runs outside that state, so
# Directives 1-5 (tilt/battery/E-stop-equivalent/stall) are already checked by RoverBrain._tick()
# before _retrieve() is ever called; abort() below is what brain.py calls on any of those firing
# mid-task (FR-1700-007) rather than this module re-checking them independently.
#
# GRASP (rebuilt 2026-10-08 on grip.py). REACH: elbow opened before the shoulder moves, shoulder
# in 50 us steps -- the owner's self-collision rule, as wave/stow -- to ARM_POSE_REACH, which is NOT
# YET MEASURED: until it is, the grasp refuses and says why rather than guess a pose. CLOSE: the
# gripper closes in steps against its position feedback (A2 wiper / arm rail): "gripped" when the
# jaw stops following before shut, "empty" when it shuts on nothing, "unsensed" without feedback
# (then vision verifies). Never commanded outside the measured GRIP_OPEN_US..GRIP_CLOSED_US.
# LIFT: shoulder stepped back. No 1500 us elbow anywhere.
#
# HAND-OFF IS SENSED (FR-1700-006): the jaw is held GRIP_SQUEEZE_US past the object, so it moves
# when the person takes the object -- that, a spoken "got it", or the timeout releases it.
# The whole task stays gated off by config.ENABLE_RETRIEVAL_TASK until the reach pose is measured
# and the feedback thresholds are checked on the rover.
_MOTION_STATES=('LOCALIZE','APPROACH','GRASP','VERIFY','DELIVER','AWAIT_CONFIRM')

class RetrievalTask:
    def __init__(self,safety,arm,detector,display=None,voice=None,feedback=None):
        # safety: a safety.SafetyController — the same single authoritative motor gate brain.py's
        # own FSM routes through (docs/WildWilly_Claude_Fix_Implementation_Plan.md §3). Nothing in
        # this class talks to DriveBase directly.
        self.safety=safety; self.arm=arm; self.detector=detector
        self.display=display; self.voice=voice
        self.state='IDLE'; self._target_class=None; self._requester_hint=None
        self._dist_cm=999.0; self._bearing_deg=0.0; self._lost_count=0; self._retries=0
        self._fail_reason=''; self._confirm_deadline=0.0
        self._grasp_step=0; self._grasp_deadline=None
        # 2026-10-08: gripper feedback (grip.read_feedback: A2 wiper / arm rail), None = no sensing
        self.feedback=feedback or (lambda: None)
        self._phase=None; self._plan=[]; self._closer=None; self._grip_result=None; self._fb_hold=None

    @property
    def active(self): return self.state in _MOTION_STATES

    def start(self,target_class,requester_hint=None,pick_only=False,colour=None):
        if self.active: return False,'retrieval task already in progress'
        self.pick_only=pick_only      # 2026-10-13 "pick up the X": no hand-off, end HOLDING
        self._blind=None; self._backoff=None; self._backoff_mm=0
        self.pick_outcome=None; self.hold_message=None; self._handoff_asks=0
        self.colour=colour
        self.state='LOCALIZE'; self._target_class=target_class; self._requester_hint=requester_hint
        self.turn_request=None
        self._lost_count=0; self._retries=0; self._fail_reason=''
        self._phase=None; self._plan=[]; self._grip_result=None; self._fb_hold=None
        log.info(f'Retrieval task started: target={target_class}')
        return True,'started'

    def abort(self,reason):
        # FR-1700-007: called by brain.py, never decided internally — "never complete a grasp or
        # hand-off motion while a higher-priority directive is active".
        if self.active:
            self.safety.stop()
            log.warning(f'Retrieval task ABORTED: {reason}')
        self.state='ABORTED'; self._fail_reason=reason
        self._grasp_step=0; self._grasp_deadline=None; self._phase=None; self._plan=[]
        try: self.arm.drop_pair()                # outside review 2026-10-13: never leave CH3 driven
        except Exception: pass

    def reset(self): self.state='IDLE'

    def tick(self,d,tilt):
        if self.display: self.display.update_state(state='processing',status=f'Retrieving: {self._target_class}')
        {'LOCALIZE':self._localize,'APPROACH':self._approach,'GRASP':self._grasp,
         'VERIFY':self._verify,'DELIVER':self._deliver,'AWAIT_CONFIRM':self._await_confirm,
        }.get(self.state,lambda d,t:None)(d,tilt)

    def _best(self,dets):
        if dets: return max(dets,key=lambda x:x['conf'])
        # colour fallback for a spoken colour ("red ball"), same as brain._reach_object (10-13)
        col=getattr(self,'colour',None)
        if col and hasattr(self.detector,'detect_colour'):
            return self.detector.detect_colour(col,label=self._target_class)
        return None

    def _localize(self,d,tilt):
        # FR-1700-001/002.
        det=self._best(self.detector.detect(classes=[self._target_class]))
        if det is None:
            self._lost_count+=1
            if self._lost_count>20:
                self.state='FAILED'; self._fail_reason=f'{self._target_class} not found'
            return
        self._dist_cm,self._bearing_deg=self.detector.localize(det)
        self._lost_count=0; self.state='APPROACH'

    def _approach(self,d,tilt):
        # 2026-10-13: line up by IMAGE POSITION (config.RETRIEVAL_TARGET_XY: where the object sits
        # when the reach lands on it), turning the body for left/right and creeping for near/far.
        # The camera cannot see under the reached arm, so all lining-up happens before the reach.
        if self.safety.timed_move_active: return
        if getattr(self,'_blind',None): return self._blind_creep(d)
        det=self._best(self.detector.detect(classes=[self._target_class]))
        if det is None:
            self._lost_count+=1; self._confirm_key=None
            if self._lost_count>20:
                self.safety.stop(); self.state='FAILED'; self._fail_reason='lost sight of target while approaching'
            return
        self._lost_count=0
        # Taught reach spots (reach_table.py): close enough to one he has learned -> reach from
        # here with the blended pose, no further lining up.
        # 2026-10-14: once the vision reach is calibrated it decides; taught spots are not used.
        pose=None if arm_ik.ready() else reach_table.pose_for(reach_table.box_xy(det))[0]
        if pose is not None:
            self.safety.stop()
            if self._confirm(('zone',)):
                self._reach_pose=pose; self.state='GRASP'
                log.info(f'In a taught reach zone: {reach_table.box_xy(det)} -> {pose}')
            return
        self._reach_pose=None
        x1,y1,x2,y2=det['bbox']
        cx=(x1+x2)/2/det['frame_w']; cy=(y1+y2)/2/det['frame_h']
        tx,ty=config.RETRIEVAL_TARGET_XY; tolx,toly=config.RETRIEVAL_TARGET_TOL
        if getattr(self,'pick_only',False):
            return self._approach_pick(d,det,cx,cy)
        if abs(cx-tx)>tolx or abs(cy-ty)>toly: self._confirm_key=None   # moving: start again
        if abs(cx-tx)>tolx:
            (self.safety.turn_right_for if cx>tx else self.safety.turn_left_for)(
                config.RETRIEVAL_TURN_PULSE_S,config.SPEED_SLOW*0.5)
            return
        if cy<ty-toly:
            if d.get('front',999)<(config.RETRIEVAL_PICK_STOP_CM if getattr(self,'pick_only',False) else config.DIST_STOP):
                # something closer than the object is in the way -- never push through it
                self.safety.stop(); self.state='FAILED'; self._fail_reason='something is in the way'
                return
            near,far=config.RETRIEVAL_CREEP_PULSE_S
            self.safety.forward_for(near if ty-cy<0.15 else far,config.SPEED_SLOW*0.6)
            return
        if cy>ty+toly:
            self.safety.reverse_for(config.RETRIEVAL_CREEP_PULSE_S[0],config.SPEED_SLOW*0.6)
            return
        self.safety.stop()
        if self._confirm(('target',)):
            self._object_cm=grip.object_height_cm(det)
            log.info(f'Object height estimate: {self._object_cm} cm')
            self.state='GRASP'; self._spot_xy=(cx,cy)
            log.info(f'Lined up: object at ({cx:.3f},{cy:.3f}), target ({tx},{ty})')

    def _approach_pick(self,d,det,cx,cy):
        """Pick-up line-up: rotate the body for a big x error, creep for y, then let the arm
        base take up the rest of x (RETRIEVAL_BASE_X_MAP)."""
        if arm_ik.ready(): return self._approach_ik(d,det,cx,cy)
        if getattr(config,'PICK_USE_IK',False) and not getattr(self,'_ik_note',False):
            self._ik_note=True
            log.info(f'Vision reach not calibrated ({", ".join(arm_ik.missing())}): image-position line-up')
        tx,ty=config.RETRIEVAL_TARGET_XY; _,toly=config.RETRIEVAL_TARGET_TOL
        ex=cx-tx
        lo=min(x for _,x in config.RETRIEVAL_BASE_X_MAP); hi=max(x for _,x in config.RETRIEVAL_BASE_X_MAP)
        if config.RETRIEVAL_ROTATE_X>=1.0 and not lo-0.03<=cx<=hi+0.03:
            # outside what the arm base can reach and body turns are off: say so, don't guess
            self.safety.stop(); self.state='FAILED'
            self._fail_reason=f"it's too far {'right' if cx>hi else 'left'} for my arm. Move it in front of my left side"
            return
        if abs(ex)>config.RETRIEVAL_ROTATE_X:
            self._confirm_key=None
            # object right of the target (ex>0) -> turn right (negative degrees in rotate.py)
            self.turn_request=-ex*config.ROTATE_CAMERA_HFOV_DEG
            log.info(f'Line-up: object at x {cx:.2f}, rotating {self.turn_request:+.0f} deg')
            return
        if cy<ty-toly or cy>ty+toly:
            self._confirm_key=None
            if cy<ty-toly:
                if d.get('front',999)<config.RETRIEVAL_PICK_STOP_CM:
                    self.safety.stop(); self.state='FAILED'; self._fail_reason='something is in the way'
                    return
                near,far=config.RETRIEVAL_CREEP_PULSE_S
                self.safety.forward_for(near if ty-cy<0.15 else far,config.RETRIEVAL_CREEP_SPEED)
            else:
                self.safety.reverse_for(config.RETRIEVAL_CREEP_PULSE_S[0],config.RETRIEVAL_CREEP_SPEED)
            return
        self.safety.stop()
        if self._confirm(('pick',)):
            self._object_cm=grip.object_height_cm(det)
            self._reach_pose=dict(config.ARM_POSE_REACH,base=base_for_x(cx)); self._spot_xy=(cx,cy)
            log.info(f'Lined up: object at ({cx:.3f},{cy:.3f}), height {self._object_cm} cm, base {self._reach_pose["base"]}')
            self.state='GRASP'

    def _approach_ik(self,d,det,cx,cy):
        """2026-10-14 vision-guided pick-up (arm_ik.py): where is it on the floor? Reach it if the
        arm can; otherwise turn or creep so it comes into reach, looking again after every move."""
        act=arm_ik.plan_for(det)
        kind=act[0]
        if kind=='reach':
            self.safety.stop()
            if self._confirm(('ik',)):
                pose,info=act[1],act[2]
                self._reach_pose=pose; self._spot_xy=(cx,cy); self._object_cm=info['size_mm']/10
                log.info(f"Vision reach: object at x {info['x']:.0f} y {info['y']:.0f} mm, "
                         f"{info['size_mm']:.0f} mm across -> angles "
                         f"{ {k:round(v,1) for k,v in info['angles'].items()} } -> {pose}")
                self.state='GRASP'
            return
        if kind!='fix': self._confirm_key=None
        if kind=='turn':
            self.turn_request=act[1]
            log.info(f'Vision reach: object {act[1]:+.0f} deg off the arm, turning'); return
        if kind=='forward':
            if d.get('front',999)<config.RETRIEVAL_PICK_STOP_CM:
                self.safety.stop(); self.state='FAILED'; self._fail_reason='something is in the way'; return
            near,far=config.RETRIEVAL_CREEP_PULSE_S
            self.safety.forward_for(near if act[1]<100 else far,config.RETRIEVAL_CREEP_SPEED); return
        if kind=='reverse':
            self.safety.reverse_for(config.RETRIEVAL_CREEP_PULSE_S[0],config.RETRIEVAL_CREEP_SPEED); return
        if kind=='fix':
            self.safety.stop()
            if self._confirm(('fix',)):
                info,creep=act[1],act[2]
                self._blind={'info':info,'creep':creep,'start':self._wheel_mm(),'pulses':0}
                self._spot_xy=(cx,cy); self._object_cm=info['size_mm']/10
                log.info(f"Last fix: object at x {info['x']:.0f} y {info['y']:.0f} mm, "
                         f"{info['size_mm']:.0f} mm across; creeping {creep:.0f} mm out of view")
            return
        self.safety.stop(); self.state='FAILED'; self._fail_reason=act[1]

    def _wheel_mm(self):
        """Mean signed wheel travel in mm (bad-encoder wheels left out), or None."""
        enc=getattr(self,'encoders',None)
        if enc is None or not getattr(enc,'is_healthy',False): return None
        c=enc.counts; ws=[w for w in c if w not in config.STALL_IGNORE_WHEELS]
        if not ws: return None
        return sum(c[w]*config.ENCODER_SIGN[w] for w in ws)/len(ws)*odometry._COUNTS_TO_M*1000.0

    def _moved_mm(self,b):
        now=self._wheel_mm()
        if b['start'] is None or now is None: return b['pulses']*config.PICK_CREEP_MM_PER_PULSE
        return abs(now-b['start'])

    def _blind_creep(self,d):
        """Creep the last stretch with the object out of view, then reach to where it was."""
        b=self._blind; done=self._moved_mm(b)
        if done>=b['creep']-config.PICK_CREEP_TOL_MM or b['pulses']>=config.PICK_CREEP_MAX_PULSES:
            self.safety.stop(); self._blind=None
            pose,a=arm_ik.reach_after_creep(b['info'],done)
            how='' if b['start'] is not None else ' (encoders unavailable: pulse estimate)'
            log.info(f"Blind creep done: {done:.0f} of {b['creep']:.0f} mm in {b['pulses']} pulses{how}")
            if pose is None:
                self.state='FAILED'; self._fail_reason="after creeping up, it's out of my reach"; return
            self._reach_pose=pose; self._backoff_mm=done
            log.info(f"Vision reach (blind): angles { {k:round(v,1) for k,v in a.items()} } -> {pose}")
            self.state='GRASP'; return
        if d.get('front',999)<config.RETRIEVAL_PICK_STOP_CM:
            self.safety.stop(); self._blind=None; self.state='FAILED'; self._fail_reason='something is in the way'; return
        self.safety.forward_for(config.PICK_CREEP_PULSE_S,config.RETRIEVAL_CREEP_SPEED); b['pulses']+=1

    def _confirm(self,key):
        """True once the same in-position verdict has held for RETRIEVAL_CONFIRM_FRAMES
        consecutive fresh detections with the rover stopped. vision.detect() captures a new frame
        on every call (no cache), but the first frame after a move can still show the scene from
        during it; this also stops one false detection from starting a reach."""
        n=self._confirm_n+1 if getattr(self,'_confirm_key',None)==key else 1
        self._confirm_key=key; self._confirm_n=n
        return n>=config.RETRIEVAL_CONFIRM_FRAMES

    def _approach_by_distance_unused(self,d,tilt):
        # FR-1700-003: respects the same obstacle thresholds as brain.py's ROAM/SLOW/AVOID —
        # a real obstacle takes priority over the retrieval path, same as normal driving.
        # Non-blocking (§2): bearing-correction turns are now deadline-based via self.safety,
        # serviced by brain.py's central self.safety.tick() call every tick — this guard just
        # keeps _approach() from issuing a second, overlapping turn while one is still in flight
        # (the camera frame during a turn is stale anyway, so waiting costs nothing real).
        if self.safety.timed_move_active: return
        if d['front']<config.DIST_STOP:
            getattr(self.safety,'obstacle_stop',self.safety.stop)()   # brake, not ramp (2026-10-07); return
        det=self._best(self.detector.detect(classes=[self._target_class]))
        if det is None:
            self._lost_count+=1
            if self._lost_count>20:
                self.safety.stop(); self.state='FAILED'; self._fail_reason='lost sight of target while approaching'
            return
        self._lost_count=0
        self._dist_cm,self._bearing_deg=self.detector.localize(det)
        if abs(self._bearing_deg)>8:
            self.safety.stop()
            (self.safety.turn_right_for if self._bearing_deg>0 else self.safety.turn_left_for)(0.15,config.SPEED_SLOW*0.5)
            return
        if self._dist_cm>config.RETRIEVAL_APPROACH_STOP_CM:
            self.safety.forward(config.SPEED_SLOW*0.6)
        else:
            self.safety.stop(); self.state='GRASP'

    # FR-1700-004 / FR-300-002 (E-stop must be able to preempt in-progress motion): each step
    # below issues its pulses then returns — the *_S delay is served as a deadline polled on the
    # next tick() call, never a time.sleep(). This was previously a single blocking call
    # (open->sleep(0.3)->lower->sleep(0.5)->close->sleep(0.3)->raise, ~1.1s total) that blocked
    # brain.py's tick thread for its whole duration; a tilt/battery/sensor fault firing mid-grasp
    # had no way to reach abort() until the sleeps finished, which defeated the same non-blocking
    # control-loop guarantee Phase 1 (§2) established for drive motion. Splitting it into steps
    # serviced from the normal ~20Hz tick means abort() (called by brain.py's Directive 1-4 checks)
    # can land between any two steps instead of only after all of them.
    # 2026-10-08: rebuilt on grip.py. REACH (elbow opened first, shoulder stepped -- the owner's
    # self-collision rule), CLOSE with position feedback (gripped / empty / unsensed), LIFT
    # (shoulder stepped back). One step per tick, so abort() can land between any two.
    def _joint_now(self,joint,default):
        return int(self.arm.pulse(joint)) if self.arm.was_driven(joint) else default

    def _start_grasp(self):
        base_us=config.ARM_SERVO_CENTER_US   # 2026-10-13: lined up by turning the body
        plan=grip.reach_plan(base_us,self._joint_now('shoulder',config.ARM_POSE_REST['shoulder']),
                             self._joint_now('elbow',None),pose=getattr(self,'_reach_pose',None),
                             object_cm=getattr(self,'_object_cm',None))
        if plan is None:
            self.state='FAILED'; self._fail_reason='reach pose not measured'
            log.warning('Grasp refused: ARM_POSE_REACH is not measured (scripts/arm_jog.py)')
            if self.voice: self.voice.speak("I can't reach down yet: my arm's reach position hasn't been measured.")
            return False
        self._plan=plan; self._phase='reach'; self._grasp_deadline=None
        log.info(f'Attempting grasp (retry {self._retries}/{config.RETRIEVAL_GRASP_RETRIES})')
        return True

    def _run_plan(self,now):
        """One arm step per call; True when the plan is finished."""
        if self._grasp_deadline is not None and now<self._grasp_deadline: return False
        if not self._plan: return True
        joint,us,delay=self._plan.pop(0)
        self.arm.set_pulse(joint,us); self._grasp_deadline=now+delay
        return False

    def _grasp(self,d,tilt):
        now=time.time()
        if self._phase is None:
            if not self._start_grasp(): return
        if self._phase=='reach':
            if self._run_plan(now):
                self._phase='close'
                self._closer=grip.GripCloser(lambda us: self.arm.set_pulse('gripper',us),self.feedback)
                self._grasp_deadline=now
            return
        if self._phase=='close':
            if now<self._grasp_deadline: return
            r=self._closer.step(); self._grasp_deadline=now+config.ARM_WAVE_STEP_S
            if r:
                self._grip_result=r; self._fb_hold=self.feedback() if r=='gripped' else None
                self._plan=grip.lift_plan(self._joint_now('shoulder',config.ARM_POSE_REST['shoulder']),
                                          self._joint_now('elbow',None))
                self._phase='lift'; self._grasp_deadline=None
            return
        if self._phase=='lift':
            if self._run_plan(now):
                self._phase=None; self.state='VERIFY'

    def _verify(self,d,tilt):
        # 2026-10-14 blind creep: back off the same distance first, so the camera sees the floor
        # spot of the last fix again before it judges the pick.
        if getattr(self,'_backoff_mm',0)>0:
            if self.safety.timed_move_active: return
            b=getattr(self,'_backoff',None)
            if b is None: b=self._backoff={'start':self._wheel_mm(),'pulses':0}
            if self._moved_mm(b)<self._backoff_mm-config.PICK_CREEP_TOL_MM and b['pulses']<config.PICK_CREEP_MAX_PULSES:
                self.safety.reverse_for(config.PICK_CREEP_PULSE_S,config.RETRIEVAL_CREEP_SPEED); b['pulses']+=1; return
            self.safety.stop(); self._backoff=None; self._backoff_mm=0
        # FR-1700-005. The gripper's own feedback first: 'empty' means it closed on nothing.
        # 2026-10-14 (owner): a stopped jaw is not proof -- the front camera then checks the object
        # left the floor (grip.camera_check). Still on the floor = a miss, retried.
        look='unknown'
        if self._grip_result!='empty':
            look=grip.camera_check(lambda: self._best(self.detector.detect(classes=[self._target_class])),
                                   getattr(self,'_spot_xy',None))
        self.verify_result=look
        # 2026-10-14 (review): three outcomes. CONFIRMED = the jaw stopped on something AND the
        # camera saw it leave the floor. MISS = closed on nothing, or still on the floor (retry).
        # Anything else (camera failed, feedback missing or contradictory) is UNCERTAIN: never
        # reported as got-it and never delivered -- he keeps holding, says so, and the task ends.
        confirmed=self._grip_result=='gripped' and look in ('gone','in_hand')
        if confirmed:
            self.pick_outcome='confirmed'; self.hold_message=None
            self.state='HOLDING' if getattr(self,'pick_only',False) else 'DELIVER'; return
        if self._grip_result=='empty' or look=='on_floor':
            self.arm.set_pulse('gripper',config.GRIP_OPEN_US)
            self._retries+=1
            if self._retries>=config.RETRIEVAL_GRASP_RETRIES:
                self.state='FAILED'; self._fail_reason='grasp failed after max retries'
                if self.voice: self.voice.speak("I wasn't able to pick that up, sorry.")
            else:
                self.state='APPROACH'
        else:
            self.pick_outcome='uncertain'
            self.hold_message=(f"I think I have the {self._target_class}, but I couldn't check. "
                               f"I'll keep holding it. Say let go to drop it.")
            log.warning(f'Pick UNCERTAIN: grip {self._grip_result}, camera {look} -- holding, not delivering')
            self.state='HOLDING'

    def _deliver(self,d,tilt):
        # FR-1700-006/008: never release without a person detected within a safe, defined range.
        det=self._best(self.detector.detect(classes=['person']))
        if det is None: return
        dist_cm,_=self.detector.localize(det)
        if dist_cm>config.RETRIEVAL_PERSON_MAX_RANGE_CM: return
        if self.voice: self.voice.speak("Here you go — say 'got it' once you have it.")
        # Hand-off baseline taken now, not at the grasp: carrying can shift the object in the jaws.
        if self._fb_hold is not None: self._fb_hold=self.feedback() or self._fb_hold
        self._handoff_hits=0
        self._confirm_deadline=time.time()+config.RETRIEVAL_HANDOFF_WAIT_S
        self.state='AWAIT_CONFIRM'

    def _await_confirm(self,d,tilt):
        confirmed=False
        if self.voice is not None:
            try:
                while True:
                    cmd=self.voice.pending_commands.get_nowait()
                    if cmd.get('intent')=='confirm_receipt' or 'got it' in cmd.get('text','').lower():
                        confirmed=True
                    else:
                        self.voice.pending_commands.put(cmd); break  # not for us, put back
            except Exception:
                pass
        # FR-1700-006: sensed hand-off -- the jaw is held GRIP_SQUEEZE_US past the object, so it
        # moves when the person pulls the object out.
        if not confirmed:
            hit=grip.released_by_person(self._fb_hold,self.feedback())
            self._handoff_hits=getattr(self,'_handoff_hits',0)+1 if hit else 0
            if self._handoff_hits>=config.GRIP_HANDOFF_READS:
                confirmed=True; log.info('Hand-off sensed: the gripper jaw closed as the object was taken')
        if confirmed:
            self.arm.set_pulse('gripper',config.GRIP_OPEN_US)  # release, to the measured open
            self.state='DONE'
        elif time.time()>self._confirm_deadline:
            # 2026-10-14 (review): a timeout means the hand-off is UNCONFIRMED, not done. Never open
            # on the clock: ask again, then keep holding and end the task (say "let go" to drop).
            self._handoff_asks=getattr(self,'_handoff_asks',0)+1
            if self._handoff_asks<config.RETRIEVAL_HANDOFF_ASKS:
                log.info('Hand-off not confirmed yet: asking again')
                if self.voice: self.voice.speak("I'm still holding it. Say 'got it' when you have it.")
                self._confirm_deadline=time.time()+config.RETRIEVAL_HANDOFF_WAIT_S
            else:
                log.warning('Hand-off never confirmed: keeping hold of the object, task ended')
                self.pick_outcome='handoff_unconfirmed'
                self.hold_message="Nobody took it, so I'm keeping hold of it. Say let go when you want it."
                self.state='HOLDING'
