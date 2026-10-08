import time,config,logsetup
from logsetup import log_event
log=logsetup.setup('safety')

# WildWilly_Claude_Fix_Implementation_Plan.md §3/§25: "Willie's AI may decide what it wants to
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

# ⚠ front_cm DEFAULTS TO 0.0, NOT 999.0 -- changed 2026-09-30, Software Design S-9.
# 999.0 meant 'assume the way is clear unless told otherwise', and sonar now arrives
# over a serial link where not-being-told is a normal failure mode. A caller that omits
# front_cm is a caller with no obstacle information, and the answer to that is no.
def approve_motion(action,speed=None,duration=None,*,front_cm=0.0,tilt_deg=0.0,
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

def approve_steer(deg,*,wheels_moving,tilt_deg=0.0,bat_tier='normal',motion_enabled=True,**_):
    """FR-600-004 manual steering override, parked only (steer_override.py). Same gates as any
    motion, plus: no wheel may be turning -- steered driving is deferred (owner 2026-08-18).
    Returns ApprovedMotion('steer', clamped degrees) or Rejected."""
    if not motion_enabled: return Rejected('motion disabled (self-test failed)')
    if tilt_deg>config.IMU_TILT_LIMIT: return Rejected(f'tilt {tilt_deg:.1f}deg exceeds limit')
    if bat_tier in('shutdown','safe'): return Rejected(f'battery tier {bat_tier!r} forbids motion')
    if wheels_moving: return Rejected('the wheels are moving; I only steer when stopped')
    d=max(-config.STEER_OVERRIDE_MAX_DEG,min(config.STEER_OVERRIDE_MAX_DEG,float(deg)))
    return ApprovedMotion('steer',d,None)

class SafetyController:
    def __init__(self,drive_base):
        self._drive=drive_base
        # front_cm starts at 0.0 -- blocked -- so forward motion is refused until a real
        # sonar reading has actually arrived. It used to start at 999.0, which granted
        # clear path before a single frame had been read. S-9.
        self._ctx={'front_cm':0.0,'tilt_deg':0.0,'bat_tier':'normal','motion_enabled':False}
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

    def obstacle_stop(self):
        """Stop for an obstacle inside DIST_STOP: a hard BRAKE, not the ramped stop(). 2026-10-07
        ("why does he still bump into things"): stop() ramps at SPEED_RAMP_PER_S, ~0.3 s from
        1 mph, and with a sonar refreshing only every ~90 ms he rolled ~10 cm past the point an
        obstacle was first seen. Clears any timed move -- this is the tick thread's own call."""
        self._drive.brake(); self._deadline=None; self._active_action=None

    def brake_now(self,reason):
        """Immediate hard brake from ANY thread, for a caller about to block every thread for
        seconds (brain.py's brake-before-generation; the deliberative layer is named there, not
        here -- this module stays reflex-only). The tick loop and motor ramp will be frozen, so the
        brake must be written synchronously before the block starts. DriveBase.brake() holds its own lock. Deliberately does
        NOT touch the timed-move state, which belongs to the tick thread; the tick re-issues or
        finishes motion once the call returns. Stop-only by construction. Kept here so that
        nothing outside this class calls DriveBase directly (tests/test_no_direct_drive_bypass)."""
        log_event(log,'BRAKE_NOW',severity='warning',subsystem='safety',status='braked',reason=reason)
        self._drive.brake()

    def set_wheels(self,targets):
        """Per-wheel targets for rotation mode (rotate.py), approved like any other turn: motion
        enabled, tilt and battery tier are checked first, so rotation never bypasses this class
        (§25). A spin turns on the spot, so it is approved as a turn, not as forward motion."""
        net=sum(v for w,v in targets.items() if w[0]=='r')-sum(v for w,v in targets.items() if w[0]=='l')
        action='turn_left' if net>=0 else 'turn_right'
        result=approve_motion(action,max(abs(v) for v in targets.values()),None,**self._ctx)
        if isinstance(result,Rejected):
            log.warning(f'rotation rejected: {result.reason}')
            self._drive.stop(); self._deadline=None; self._active_action=None
            return result
        self._deadline=None; self._active_action=None
        self._drive.set_wheels(targets)
        return result

    def approve_steer(self,deg):
        """FR-600-004: approve a parked steering override against the cached context."""
        moving=self._deadline is not None or any(getattr(self._drive,'commanded',{}).values())
        r=approve_steer(deg,wheels_moving=moving,**self._ctx)
        if isinstance(r,Rejected): log.warning(f'steering override rejected: {r.reason}')
        return r

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
            self.obstacle_stop(); return False
        if time.time()>=self._deadline:
            self._drive.stop(); self._deadline=None; self._active_action=None; return False
        return True

    def emergency_stop(self,reason):
        # FR-300-002 (immediate motion disable): hard brake + clears any queued/in-flight
        # motion in the same call. brain.py's fault checks (sensor/tilt/battery) and voice
        # 'stop' all funnel through here -- see brain.py's _check_health()/_tick() call sites.
        # FR-300-001: the E-stop is the MAIN POWER SWITCH (there is no mushroom switch). It
        # cuts all power, the Pi included, so there is nothing for software to sense -- the
        # requirement is met by hardware. This method is the SOFTWARE stop (faults, voice).
        #
        # FR-300-003 (explicit operator reset before resuming) IS implemented, in brain.py.
        # CORRECTED 2026-09-17: this comment used to say it was not, and claimed "every fault
        # state this class enters is recovered from automatically once the triggering condition
        # clears". That stopped being true on 2026-08-18 and the comment was never updated -- an
        # external reviewer read it in September and reported the requirement as open. The
        # authority is brain.py's _await_reset_or_resume(): a latched fault keeps braking after
        # its condition clears and waits for an explicit operator action. It covers
        # SENSOR_FAULT, TILT_FAULT, STALL_FAULT and -- since 2026-09-17 -- battery SAFE_MODE,
        # which was the last emergency_stop() path that still auto-resumed.
        #
        # "Explicit operator reset" means, by owner decision 2026-09-17, EITHER a screen tap
        # (display.reset_tapped()) OR the 'reset' voice intent (brain._voice_reset_requested()).
        #
        # This class deliberately holds no latch of its own. brain.py owns fault state, and
        # emergency_stop() is re-asserted every tick for as long as the fault stands -- so a
        # latch here would be a second source of truth for the same condition.
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
