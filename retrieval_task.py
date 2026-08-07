import time,config,logsetup
log=logsetup.setup('retrieval')

# FR-1700 Object Detection and Retrieval Task — the "core mission" per the FRD. This is a
# sub-state-machine driven by RoverBrain as its own top-level FSM state ('RETRIEVE'), the same
# way DOCK/AVOID/STUCK are — see brain.py's _retrieve(). It never runs outside that state, so
# Directives 1-5 (tilt/battery/E-stop-equivalent/stall) are already checked by RoverBrain._tick()
# before _retrieve() is ever called; abort() below is what brain.py calls on any of those firing
# mid-task (FR-1700-007) rather than this module re-checking them independently.
#
# GRASP PLANNING IS A FIXED PRIMITIVE SEQUENCE, NOT INVERSE KINEMATICS: no per-joint calibration
# has been run on the arm (§20.6 pending, same gap noted in arm.py/config.py since the baseline
# pass) — there is no reach-envelope model to plan a real grasp pose against. This sequence
# (rotate base toward bearing, open gripper, lower by a fixed offset, close, raise) is a rough
# working approximation, not a calibrated motion. Bench-calibrate §20.6 before trusting this
# near anything fragile.
#
# HAND-OFF CONFIRMATION IS TIME-BASED, NOT SENSED: there is no tactile/force sensor on the
# gripper to detect "the person actually has it" (FR-1700-006). This waits for either an
# explicit voice confirmation intent or a fixed timeout before releasing — a real gap, flagged
# rather than papered over.

_MOTION_STATES=('LOCALIZE','APPROACH','GRASP','VERIFY','DELIVER','AWAIT_CONFIRM')

class RetrievalTask:
    def __init__(self,safety,arm,detector,display=None,voice=None):
        # safety: a safety.SafetyController — the same single authoritative motor gate brain.py's
        # own FSM routes through (docs/WildWilly_Claude_Fix_Implementation_Plan.md §3). Nothing in
        # this class talks to DriveBase directly.
        self.safety=safety; self.arm=arm; self.detector=detector
        self.display=display; self.voice=voice
        self.state='IDLE'; self._target_class=None; self._requester_hint=None
        self._dist_cm=999.0; self._bearing_deg=0.0; self._lost_count=0; self._retries=0
        self._fail_reason=''; self._confirm_deadline=0.0

    @property
    def active(self): return self.state in _MOTION_STATES

    def start(self,target_class,requester_hint=None):
        if self.active: return False,'retrieval task already in progress'
        self.state='LOCALIZE'; self._target_class=target_class; self._requester_hint=requester_hint
        self._lost_count=0; self._retries=0; self._fail_reason=''
        log.info(f'Retrieval task started: target={target_class}')
        return True,'started'

    def abort(self,reason):
        # FR-1700-007: called by brain.py, never decided internally — "never complete a grasp or
        # hand-off motion while a higher-priority directive is active".
        if self.active:
            self.safety.stop()
            log.warning(f'Retrieval task ABORTED: {reason}')
        self.state='ABORTED'; self._fail_reason=reason

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
            self.safety.stop(); return
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

    def _grasp(self,d,tilt):
        # FR-1700-004 — see module docstring: fixed primitive sequence, not real IK.
        log.info(f'Attempting grasp (retry {self._retries}/{config.RETRIEVAL_GRASP_RETRIES})')
        half=(config.ARM_SERVO_MAX_US-config.ARM_SERVO_MIN_US)/2
        base_us=config.ARM_SERVO_CENTER_US+(self._bearing_deg/90.0)*half
        self.arm.set_pulse('base',base_us)
        self.arm.set_pulse('gripper',config.ARM_SERVO_MIN_US)  # open
        time.sleep(0.3)
        self.arm.set_pulse('shoulder_a',config.ARM_SERVO_CENTER_US-300)  # rough "lower toward table"
        self.arm.set_pulse('elbow',config.ARM_SERVO_CENTER_US-300)
        time.sleep(0.5)
        self.arm.set_pulse('gripper',config.ARM_SERVO_MAX_US)  # close
        time.sleep(0.3)
        self.arm.set_pulse('shoulder_a',config.ARM_SERVO_CENTER_US)
        self.arm.set_pulse('elbow',config.ARM_SERVO_CENTER_US)
        self.state='VERIFY'

    def _verify(self,d,tilt):
        # FR-1700-005: if the target is still visible on the ground, the grasp didn't take —
        # report/retry rather than proceeding as if it succeeded.
        det=self._best(self.detector.detect(classes=[self._target_class]))
        if det is not None:
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
        if confirmed or time.time()>self._confirm_deadline:
            if not confirmed:
                log.warning('Hand-off released on timeout, no confirmation received — no tactile '
                            'sensor exists to verify receipt (see module docstring).')
            self.arm.set_pulse('gripper',config.ARM_SERVO_MIN_US)  # release
            self.state='DONE'
