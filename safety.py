import time,config,logsetup
from logsetup import log_event
log=logsetup.setup('safety')

# WildWilly_Claude_Fix_Implementation_Plan.md §3/§25: "Willy's AI may decide what it wants to
# accomplish, but it may never decide whether it is safe to move." SafetyController is the single
# authoritative gate between any motion source (reactive FSM, retrieval task, Claude-proposed
# action) and the physical motors — nothing else is allowed to call DriveBase directly.

_CONTINUOUS={'forward','reverse','turn_left','turn_right','stop'}

class Rejected:
    __slots__=('reason',)
    def __init__(self,reason): self.reason=reason
    def __repr__(self): return f'Rejected({self.reason!r})'

class ApprovedMotion:
    __slots__=('action','speed','duration')
    def __init__(self,action,speed,duration): self.action=action; self.speed=speed; self.duration=duration
    def __repr__(self): return f'ApprovedMotion({self.action!r},speed={self.speed},duration={self.duration})'

def approve_motion(action,speed=None,duration=None,*,front_cm=999.0,tilt_deg=0.0,
                    bat_tier='normal',motion_enabled=True):
    """Pure decision logic, no hardware access — independently unit-testable (tests/test_safety.py).
    Returns ApprovedMotion (with speed/duration clamped to configured limits) or Rejected(reason)."""
    if not motion_enabled: return Rejected('motion disabled (self-test failed)')
    if action not in _CONTINUOUS: return Rejected(f'unknown action {action!r}')
    if tilt_deg>config.IMU_TILT_LIMIT: return Rejected(f'tilt {tilt_deg:.1f}deg exceeds limit')
    if bat_tier in('shutdown','safe'): return Rejected(f'battery tier {bat_tier!r} forbids motion')
    if action=='forward' and front_cm<config.DIST_STOP: return Rejected(f'obstacle at {front_cm:.0f}cm blocks forward')
    spd=None if speed is None else max(0.0,min(config.SPEED_MAX,float(speed)))
    dur=None if duration is None else max(0.0,min(config.MAX_COMMAND_DURATION_S,float(duration)))
    return ApprovedMotion(action,spd,dur)

class SafetyController:
    def __init__(self,drive_base):
        self._drive=drive_base
        self._ctx={'front_cm':999.0,'tilt_deg':0.0,'bat_tier':'normal','motion_enabled':False}
        self._deadline=None; self._active_action=None
        self._last_estop_log_t=0.0

    def update_context(self,front_cm=None,tilt_deg=None,bat_tier=None,motion_enabled=None):
        # Called once near the top of brain.py's _tick() so per-call sites (forward()/stop()/etc.)
        # don't each have to thread sensor readings through — approve_motion() itself stays a pure
        # function of explicit args for testing; this is just where production wiring caches them.
        if front_cm is not None: self._ctx['front_cm']=front_cm
        if tilt_deg is not None: self._ctx['tilt_deg']=tilt_deg
        if bat_tier is not None: self._ctx['bat_tier']=bat_tier
        if motion_enabled is not None: self._ctx['motion_enabled']=motion_enabled

    def request(self,action,speed=None,duration=None):
        """Approve against the current cached context, then execute if approved.
        duration=None -> continuous command, caller re-issues every tick (ROAM/SLOW/etc.).
        duration=<n>  -> starts (or replaces) a non-blocking timed move serviced by tick();
                         does NOT sleep — this is what replaces motors.py's old *_for() blocking."""
        result=approve_motion(action,speed,duration,**self._ctx)
        if isinstance(result,Rejected):
            log.warning(f'motion rejected: action={action} reason={result.reason}')
            self._drive.stop(); self._deadline=None; self._active_action=None
            return result
        {'forward':self._drive.forward,'reverse':self._drive.reverse,
         'turn_left':self._drive.turn_left,'turn_right':self._drive.turn_right,
         'stop':lambda s=None:self._drive.stop()}[result.action](result.speed)
        if result.duration is not None:
            self._deadline=time.time()+result.duration; self._active_action=result.action
        else:
            self._deadline=None; self._active_action=None
        return result

    # Convenience wrappers mirroring DriveBase's old API shape, so FSM call sites read the same
    # as before (self.motors.forward(...) -> self.safety.forward(...)).
    def forward(self,speed=None): return self.request('forward',speed,None)
    def reverse(self,speed=None): return self.request('reverse',speed,None)
    def turn_left(self,speed=None): return self.request('turn_left',speed,None)
    def turn_right(self,speed=None): return self.request('turn_right',speed,None)
    def stop(self): return self.request('stop',None,None)
    def forward_for(self,duration,speed=None): return self.request('forward',speed,duration)
    def reverse_for(self,duration,speed=None): return self.request('reverse',speed,duration)
    def turn_left_for(self,duration,speed=None): return self.request('turn_left',speed,duration)
    def turn_right_for(self,duration,speed=None): return self.request('turn_right',speed,duration)

    @property
    def timed_move_active(self): return self._deadline is not None

    def tick(self):
        """Call once per brain tick regardless of FSM state. Enforces the deadline on an in-flight
        timed move and re-validates it against the obstacle condition (tilt/battery mid-flight
        aborts are already handled by brain.py's top-level Directive checks calling
        emergency_stop() before this runs, which also clears _deadline — nothing to duplicate here).
        Returns True while a timed move is still running, False once finished/absent."""
        if self._deadline is None: return False
        if self._active_action=='forward' and self._ctx['front_cm']<config.DIST_STOP:
            log_event(log,'OBSTACLE_STOP',severity='warning',subsystem='safety',
                      status='mid_flight_abort',front_cm=f'{self._ctx["front_cm"]:.0f}')
            self._drive.stop(); self._deadline=None; self._active_action=None; return False
        if time.time()>=self._deadline:
            self._drive.stop(); self._deadline=None; self._active_action=None; return False
        return True

    def emergency_stop(self,reason):
        # FR-300-002 (immediate motion disable): hard brake + clears any queued/in-flight
        # motion in the same call. brain.py's fault checks (sensor/tilt/battery) and voice
        # 'stop' all funnel through here -- see brain.py's _check_health()/_tick() call sites.
        # FR-300-001 (continuous physical E-stop monitoring) and FR-300-003 (explicit
        # operator reset before resuming) are NOT implemented: no physical E-stop GPIO is
        # polled anywhere in this codebase (grep for ESTOP finds only the log-throttle
        # constant below), and every fault state this class enters is recovered from
        # automatically once the triggering condition clears (see brain.py's SAFE_MODE/
        # SENSOR_FAULT handling) rather than requiring an explicit operator action. FR-300-001
        # is blocked on hardware (no sense pin wired, see CLAUDE.md); FR-300-003 is a real,
        # fixable design decision -- deliberately not built here without product sign-off on
        # what "explicit operator reset" should mean on this rover (a voice intent? a physical
        # button that doesn't exist yet? something else?), see [[project_willy_rover_frd_closure]].
        # Immediate hard brake (not the ramped stop()) — for tilt/battery faults and sustained
        # sensor faults, where a 0.5s ramp-down is the wrong call. Also clears any in-flight timed
        # move so a stale deadline can't fire after recovery.
        # brain.py calls this every tick for as long as the fault persists (correct — the brake
        # must be reasserted continuously) but the log line is throttled to ESTOP_LOG_INTERVAL_S
        # so a sustained fault doesn't flood the log at tick rate (found 2026-08-08 live: a
        # powered-off base sitting in battery-shutdown logged this line ~20x/sec, unbounded).
        now=time.time()
        if now-self._last_estop_log_t>config.ESTOP_LOG_INTERVAL_S:
            log.warning(f'emergency stop: {reason}'); self._last_estop_log_t=now
        self._drive.brake(); self._deadline=None; self._active_action=None
