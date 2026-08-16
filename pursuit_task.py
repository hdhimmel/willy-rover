import config,logsetup
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
        self._lost_count=0; self._fail_reason=''

    @property
    def active(self): return self.state in _MOTION_STATES

    def start(self,mode='come_here'):
        if self.active: return False,'pursuit already in progress'
        self.state='LOCALIZE'; self._mode=mode; self._lost_count=0; self._fail_reason=''
        log.info(f'Pursuit task started: target=person mode={mode}')
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

    def _localize(self,d,tilt):
        det=self._best(self.detector.detect(classes=['person']))
        if det is None:
            self._lost_count+=1
            if self._lost_count>20:
                self.state='FAILED'; self._fail_reason='no one found'
            return
        self._dist_cm,self._bearing_deg=self.detector.localize(det)
        self._lost_count=0; self.state='APPROACH'

    def _approach(self,d,tilt):
        # Same bearing-correction/obstacle-priority shape as RetrievalTask._approach — a real
        # obstacle still takes priority over the pursuit path.
        if self.safety.timed_move_active: return
        if d['front']<config.DIST_STOP:
            self.safety.stop(); return
        det=self._best(self.detector.detect(classes=['person']))
        if det is None:
            self._lost_count+=1
            if self._lost_count>20:
                self.safety.stop(); self.state='FAILED'; self._fail_reason='lost sight of you while approaching'
            return
        self._lost_count=0
        self._dist_cm,self._bearing_deg=self.detector.localize(det)
        if abs(self._bearing_deg)>8:
            self.safety.stop()
            (self.safety.turn_right_for if self._bearing_deg>0 else self.safety.turn_left_for)(0.15,config.SPEED_SLOW*0.5)
            return
        if self._dist_cm>config.PURSUIT_STANDOFF_CM:
            self.safety.forward(config.SPEED_SLOW*0.6)
        else:
            self.safety.stop()
            self.state='FOLLOWING' if self._mode=='follow' else 'DONE'

    def _following(self,d,tilt):
        # Holds position, watching. Re-enters APPROACH once the person is far enough past
        # standoff that closing the gap again is worth a move (hysteresis avoids inching
        # forward/back every tick on small standoff-boundary jitter).
        if self.safety.timed_move_active: return
        det=self._best(self.detector.detect(classes=['person']))
        if det is None:
            self._lost_count+=1
            if self._lost_count>20:
                self.safety.stop(); self.state='FAILED'; self._fail_reason='lost sight of you'
            return
        self._lost_count=0
        self._dist_cm,self._bearing_deg=self.detector.localize(det)
        if self._dist_cm>config.PURSUIT_STANDOFF_CM+config.PURSUIT_RESUME_HYSTERESIS_CM:
            self.state='APPROACH'
