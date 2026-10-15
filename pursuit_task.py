import math,config,logsetup,arm_ik
log=logsetup.setup('pursuit')

# FR-1000 "come here"/"follow me" + FR-1700 person detection. Same shape as retrieval_task.py's
# RETRIEVE sub-state-machine (its own top-level brain.py FSM state, 'PURSUE' — see brain.py's
# _pursue()) so Directives 1-5 are already enforced by RoverBrain._tick() before this ever ticks;
# abort() is what brain.py calls on any Directive 1-4 preemption firing mid-task, same contract
# as RetrievalTask.abort()/NavigationTask.abort().
#
# TWO MODES, one state machine. mode='come_here': arrive within standoff distance and stop --
# DONE. mode='follow': arrive within standoff, then hold in FOLLOWING, continuously
# re-localizing; if the person moves back out past standoff+hysteresis it re-enters APPROACH and
# keeps pace. FOLLOWING has no built-in end condition of its own by design -- the only way out is
# losing sight of the person (>20 ticks -> FAILED), a Directive 1-4 preemption calling abort()
# (tilt/battery/sensor fault), or a spoken "stop" (voice.py's stop_requested bypasses the command
# queue precisely so this is always reachable mid-task, see its docstring).

_MOTION_STATES=('LOCALIZE','APPROACH','FOLLOWING')

class PursuitTask:
    def __init__(self,safety,detector,display=None,voice=None):
        self.safety=safety; self.detector=detector; self.display=display; self.voice=voice
        self.state='IDLE'; self._mode='come_here'; self._dist_cm=999.0; self._bearing_deg=0.0
        self._cls='person'; self._standoff=config.PURSUIT_STANDOFF_CM; self.who='you'
        self._lost_count=0; self._fail_reason=''; self._search_steps=0

    @property
    def active(self): return self.state in _MOTION_STATES

    def start(self,mode='come_here',target_class='person',standoff_cm=None,who='you'):
        """2026-10-15: any detector class (e.g. 'dog' for Storm) with its own standoff."""
        if self.active: return False,'pursuit already in progress'
        self.state='LOCALIZE'; self._mode=mode; self._lost_count=0; self._fail_reason=''
        self._search_steps=0; self._cls=target_class; self.who=who
        self._standoff=standoff_cm if standoff_cm is not None else config.PURSUIT_STANDOFF_CM
        log.info(f'Pursuit task started: target={target_class} mode={mode} standoff={self._standoff} cm')
        return True,'started'

    def abort(self,reason):
        if self.active:
            self.safety.stop()
            log.warning(f'Pursuit task ABORTED: {reason}')
        self.state='ABORTED'; self._fail_reason=reason

    def reset(self): self.state='IDLE'

    def tick(self,d,tilt):
        if self.display:
            status='Following you' if self.state=='FOLLOWING' else 'Coming to find you'
            self.display.update_state(state='processing',status=status)
        {'LOCALIZE':self._localize,'APPROACH':self._approach,
         'FOLLOWING':self._following}.get(self.state,lambda d,t:None)(d,tilt)

    def _best(self,dets):
        return max(dets,key=lambda x:x['conf']) if dets else None

    def _locate(self,det):
        """(cm ahead of the wheels, bearing deg, + = right). The calibrated camera's floor contact
        (2026-10-14) when it has one -- a dog or a person stands on the floor -- else the old
        width-based estimate."""
        try:
            p=arm_ik.floor_contact(det)
            if p is not None:
                return (max(0.0,(p[0]-config.ARM_FRONT_REACH_CLEAR_MM)/10.0),
                        -math.degrees(math.atan2(p[1],p[0])))
        except Exception: pass
        return self.detector.localize(det)

    def _localize(self,d,tilt):
        # FR-1000-006 search sweep (2026-10-02): if nobody is in view, look around in
        # PURSUIT_SEARCH_STEPS timed turns before giving up, instead of failing on the spot.
        # Turns are skid turns of fixed duration (steering is uncalibrated), so a "full circle"
        # is approximate.
        if self.safety.timed_move_active: return
        det=self._best(self.detector.detect(classes=[self._cls]))
        if det is None:
            self._lost_count+=1
            if self._lost_count>config.PURSUIT_LOOK_TICKS:
                if self._search_steps<config.PURSUIT_SEARCH_STEPS:
                    self._search_steps+=1; self._lost_count=0
                    self.safety.turn_left_for(config.PURSUIT_SEARCH_TURN_S,config.SPEED_TURN*0.6)
                else:
                    self.state='FAILED'; self._fail_reason='no one found after looking around'
            return
        self._dist_cm,self._bearing_deg=self._locate(det)
        self._lost_count=0; self.state='APPROACH'

    def _approach(self,d,tilt):
        # Same bearing-correction/obstacle-priority shape as RetrievalTask._approach — a real
        # obstacle still takes priority over the pursuit path.
        if self.safety.timed_move_active: return
        if d['front']<config.DIST_STOP:
            getattr(self.safety,'obstacle_stop',self.safety.stop)()   # brake, not ramp (2026-10-07); return
        det=self._best(self.detector.detect(classes=[self._cls]))
        if det is None:
            self._lost_count+=1
            if self._lost_count>20:
                self.safety.stop(); self.state='FAILED'; self._fail_reason=f'lost sight of {self.who} while approaching'
            return
        self._lost_count=0
        self._dist_cm,self._bearing_deg=self._locate(det)
        if abs(self._bearing_deg)>8:
            self.safety.stop()
            (self.safety.turn_right_for if self._bearing_deg>0 else self.safety.turn_left_for)(0.15,config.SPEED_SLOW*0.5)
            return
        if self._dist_cm>self._standoff:
            self.safety.forward(config.SPEED_SLOW*0.6)
        else:
            self.safety.stop()
            self.state='FOLLOWING' if self._mode=='follow' else 'DONE'

    def _following(self,d,tilt):
        # Holds position, watching. Re-enters APPROACH once the person is far enough past
        # standoff that closing the gap again is worth a move (hysteresis avoids inching
        # forward/back every tick on small standoff-boundary jitter).
        if self.safety.timed_move_active: return
        det=self._best(self.detector.detect(classes=[self._cls]))
        if det is None:
            self._lost_count+=1
            if self._lost_count>20:
                self.safety.stop(); self.state='FAILED'; self._fail_reason='lost sight of you'
            return
        self._lost_count=0
        self._dist_cm,self._bearing_deg=self._locate(det)
        if self._dist_cm>self._standoff+config.PURSUIT_RESUME_HYSTERESIS_CM:
            self.state='APPROACH'
