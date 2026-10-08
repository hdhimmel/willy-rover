import time,config,logsetup,grip
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

    def start(self,target_class,requester_hint=None):
        if self.active: return False,'retrieval task already in progress'
        self.state='LOCALIZE'; self._target_class=target_class; self._requester_hint=requester_hint
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

    def reset(self): self.state='IDLE'

    def tick(self,d,tilt):
        if self.display: self.display.update_state(state='processing',status=f'Retrieving: {self._target_class}')
        {'LOCALIZE':self._localize,'APPROACH':self._approach,'GRASP':self._grasp,
         'VERIFY':self._verify,'DELIVER':self._deliver,'AWAIT_CONFIRM':self._await_confirm,
        }.get(self.state,lambda d,t:None)(d,tilt)

    def _best(self,dets):
        return max(dets,key=lambda x:x['conf']) if dets else None

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
        half=(config.ARM_SERVO_MAX_US-config.ARM_SERVO_MIN_US)/2
        base_us=max(config.ARM_SERVO_MIN_US,min(config.ARM_SERVO_MAX_US,
                    config.ARM_SERVO_CENTER_US+(self._bearing_deg/90.0)*half))
        plan=grip.reach_plan(base_us,self._joint_now('shoulder',config.ARM_POSE_REST['shoulder']),
                             self._joint_now('elbow',None))
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
                self._plan=grip.lift_plan(self._joint_now('shoulder',config.ARM_POSE_REST['shoulder']))
                self._phase='lift'; self._grasp_deadline=None
            return
        if self._phase=='lift':
            if self._run_plan(now):
                self._phase=None; self.state='VERIFY'

    def _verify(self,d,tilt):
        # FR-1700-005. The gripper's own feedback first: 'empty' means it closed on nothing;
        # 'gripped' means something stopped the jaw. Vision only decides when it was unsensed.
        if self._grip_result=='gripped':
            self.state='DELIVER'; return
        det=None if self._grip_result=='empty' else self._best(self.detector.detect(classes=[self._target_class]))
        if self._grip_result=='empty' or det is not None:
            self.arm.set_pulse('gripper',config.GRIP_OPEN_US)
            self._retries+=1
            if self._retries>=config.RETRIEVAL_GRASP_RETRIES:
                self.state='FAILED'; self._fail_reason='grasp failed after max retries'
                if self.voice: self.voice.speak("I wasn't able to pick that up, sorry.")
            else:
                self.state='APPROACH'
        else:
            self.state='DELIVER'

    def _deliver(self,d,tilt):
        # FR-1700-006/008: never release without a person detected within a safe, defined range.
        det=self._best(self.detector.detect(classes=['person']))
        if det is None: return
        dist_cm,_=self.detector.localize(det)
        if dist_cm>config.RETRIEVAL_PERSON_MAX_RANGE_CM: return
        if self.voice: self.voice.speak("Here you go — say 'got it' once you have it.")
        self._confirm_deadline=time.time()+15.0
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
        if not confirmed and grip.released_by_person(self._fb_hold,self.feedback()):
            confirmed=True; log.info('Hand-off sensed: the gripper jaw moved as the object was taken')
        if confirmed or time.time()>self._confirm_deadline:
            if not confirmed:
                log.warning('Hand-off released on timeout, no confirmation received — no tactile '
                            'sensor exists to verify receipt (see module docstring).')
            self.arm.set_pulse('gripper',config.GRIP_OPEN_US)  # release, to the measured open
            self.state='DONE'
