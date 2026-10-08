import time, threading, logging, config
import hw_sim
log=logging.getLogger('motors')
if not config.SIMULATE_HARDWARE:
    import board, busio
    from adafruit_motorkit import MotorKit
    from adafruit_pca9685 import PCA9685
    _i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)

import math as _math

def cap_rpm():
    """Wheel RPM at SPEED_MAX (the mph cap)."""
    return config.SPEED_MAX_MPH*0.44704/(_math.pi*config.WHEEL_DIAMETER_M)*60.0

def wheel_duty(w,target_rpm,meas_rpm,integ,dt):
    """FR-500-004 (2026-10-02): (duty, new_integ) for one wheel, in the command frame
    (+ = this wheel's forward command). Pure, so it is tested directly.

    Feed-forward from WHEEL_FF does most of the work; a PI on the encoder error trims it,
    bounded to +-WHEEL_TRIM_MAX so a blocked wheel only gets a limited extra push. meas_rpm
    None (no healthy encoder) -> feed-forward only. Never drives against the target's sign,
    and stops integrating while saturated (anti-windup)."""
    if target_rpm==0: return 0.0,0.0
    d0,slope=config.WHEEL_FF.get(w,(0.22,225.0))
    sgn=1.0 if target_rpm>0 else -1.0
    ff=sgn*(d0+abs(target_rpm)/slope)
    if meas_rpm is None or not config.WHEEL_SPEED_CONTROL:
        return max(-1.0,min(1.0,ff)),0.0
    err=target_rpm-meas_rpm
    new_i=max(-config.WHEEL_TRIM_MAX,min(config.WHEEL_TRIM_MAX,integ+config.WHEEL_KI*err*dt))
    trim=max(-config.WHEEL_TRIM_MAX,min(config.WHEEL_TRIM_MAX,config.WHEEL_KP*err+new_i))
    duty=ff+trim
    if abs(duty)>1.0:
        duty=max(-1.0,min(1.0,duty)); new_i=integ        # saturated: hold the integrator
    if duty*sgn<0: duty=0.0                              # never drive against the target
    return duty,new_i

class DriveBase:
    _WHEELS=('lf','lm','lr','rf','rm','rr')
    def __init__(self,offline=False):
        # offline=True (2026-10-08): the motor FeatherWings are unreachable -- typically the 12 V
        # supply is off and only the Pi is powered. Writes go nowhere, is_healthy is False, and the
        # self-test (which expects 0x60/0x61) keeps motion disabled; voice, face and everything
        # else still run. Before this, a missing driver crashed RoverBrain() and systemd looped.
        self.offline=offline
        if config.SIMULATE_HARDWARE or offline:
            self._motors={w:hw_sim.SimMotor() for w in self._WHEELS}
        else:
            kits={a:MotorKit(i2c=_i2c,address=a) for a in (config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR)}
            self._motors={w:getattr(kits[a],f'motor{p}') for w,(a,p) in config.MOTOR_PORT.items()}
            self._pcas=[k._pca for k in kits.values()]   # for sleep/wake; MotorKit holds it here
        if config.SIMULATE_HARDWARE or offline: self._pcas=[]
        self._target=dict.fromkeys(self._WHEELS,0.0); self._actual=dict.fromkeys(self._WHEELS,0.0)
        self._lock=threading.Lock(); self.current_speed=0.0
        self._coasting=False; self._idle_since=time.monotonic()
        self._write_fail_t=None; self._write_fail_logged_t=0.0   # see _write()
        self._encoders=None; self._integ=dict.fromkeys(self._WHEELS,0.0)   # FR-500-004
        self._running=True
        self._thread=threading.Thread(target=self._ramp_loop,daemon=True); self._thread.start()
    # FR-500-004 (closed-loop speed): BUILT 2026-10-02. This loop ramps the commanded fraction
    # of the mph cap, then wheel_duty() turns it into a per-wheel duty from feed-forward plus a
    # bounded PI trim on the encoder RPM (feed-forward only when the encoders are unhealthy).
    # Idle power, added 2026-09-30. throttle=0.0 is adafruit_motor's HARD BRAKE -- both legs
    # driven -- so a stopped rover was holding six bridges on at 50Hz forever. Measured on the
    # +12V motor branch: 0.019A doing nothing. Once every wheel is commanded to zero AND has
    # finished ramping, release the bridges (throttle=None coasts) and sleep both MotorKit
    # PCA9685s. Any non-zero command wakes them first. brake() never comes through here.
    def attach_encoders(self,encoders):
        """FR-500-004: give the ramp loop encoder feedback. Without it, feed-forward only."""
        self._encoders=encoders

    def _measured_rpm(self):
        """Per-wheel RPM in the command frame, or None when there is no healthy feedback."""
        e=self._encoders
        if e is None: return None
        try:
            if not e.is_healthy: return None
            cps=e.counts_per_sec
        except Exception:
            return None
        k=60.0/config.ENCODER_COUNTS_PER_REV
        # counts follow the actual throttle sign (Pico A a-0.3), and the written throttle is
        # command*MOTOR_SIGN, so the command-frame speed is counts*MOTOR_SIGN.
        return {w:cps.get(w,0.0)*config.MOTOR_SIGN[w]*k for w in self._WHEELS}

    def _coast(self):
        for m in self._motors.values(): m.throttle=None
        for p in self._pcas:
            try: p.mode1_reg=p.mode1_reg|0x10        # MODE1 bit4 SLEEP: stops the PWM oscillator
            except Exception: pass                   # a bus hiccup must not kill the ramp thread
        self._coasting=True

    def _wake(self):
        for p in self._pcas:
            try:
                m=p.mode1_reg
                if m & 0x10: p.mode1_reg=m & ~0x10
            except Exception: pass
        if self._pcas: time.sleep(0.001)             # datasheet: >=500us for the oscillator
        self._coasting=False

    def _ramp_loop(self):
        # FR-400-003: slew-rate limit so throttle changes smoothly rather than jumping instantly.
        dt=0.02; step=config.SPEED_RAMP_PER_S*dt
        while self._running:
            with self._lock:
                commanded=any(self._target[w]!=0.0 for w in self._WHEELS)
                if commanded:
                    if self._coasting: self._wake()
                    self._idle_since=None
                meas=self._measured_rpm() if commanded else None
                crpm=cap_rpm()
                for w in self._WHEELS:
                    tgt=self._target[w]; cur=self._actual[w]
                    cur = tgt if abs(tgt-cur)<=step else cur+(step if tgt>cur else -step)
                    self._actual[w]=cur
                    # FR-500-004: the ramped command is a fraction of the mph cap; turn it into
                    # a wheel RPM and let wheel_duty() find the duty that holds it.
                    duty,self._integ[w]=wheel_duty(w,cur*crpm,None if meas is None else meas[w],
                                                   self._integ[w],dt)
                    if not self._coasting:      # MOTOR_SIGN: the right side is mounted mirrored
                        self._write(w,duty*config.MOTOR_SIGN[w])
                self.current_speed=(self._actual['lf']+self._actual['rf'])/2
                if not commanded and not self._coasting and                         all(self._actual[w]==0.0 for w in self._WHEELS):
                    now=time.monotonic()
                    if self._idle_since is None: self._idle_since=now
                    elif now-self._idle_since>=config.MOTOR_COAST_AFTER_S: self._coast()
            time.sleep(dt)
    def _write(self,w,value):
        """One throttle write that cannot kill the ramp thread. Until 2026-10-01 a single I2C
        OSError here escaped _ramp_loop and ended the thread, after which every ramped stop()
        did nothing -- only brake() still reached the wheels -- and nothing noticed. Now the
        failure is recorded, the other wheels are still written, and is_healthy goes false so
        brain.py's _check_health() escalates to SENSOR_FAULT and brakes."""
        try:
            self._motors[w].throttle=value
        except Exception:
            now=time.monotonic(); self._write_fail_t=now
            if now-self._write_fail_logged_t>5.0:
                self._write_fail_logged_t=now
                log.warning(f'motor driver write failed ({w})',exc_info=True)
    @property
    def is_healthy(self):
        """Ramp thread alive and no failed driver write in the last second. Never when offline."""
        if self.offline: return False
        if not self._thread.is_alive(): return False
        t=self._write_fail_t
        return t is None or time.monotonic()-t>1.0
    # FR-400-001 (independent left/right control): six wheels individually targetable
    # (lf/lm/lr vs rf/rm/rr), driver assignment fixed by as-built wiring -- **0x61 LEFT,
    # 0x60 RIGHT**, measured 2026-09-18 by M-1. This comment said "0x60 left, 0x61 right"
    # from the original build until then, and it was wrong the whole time; see config.py's
    # MOTOR_PORT block for why a side swap is invisible to everything _set() does.
    def _set(self,l,r):
        with self._lock:
            for w in ('lf','lm','lr'): self._target[w]=l
            for w in ('rf','rm','rr'): self._target[w]=r
    # FR-400-002 (forward/reverse/turning) and FR-400-004 (enforce software speed
    # limits): every method below clamps to config.SPEED_MAX before driving. Ramping
    # to that target then happens in _ramp_loop() above (FR-400-003).
    def forward(self,speed=None):
        s=min(config.SPEED_MAX,speed or config.SPEED_ROAM); self._set(s,s)
    def reverse(self,speed=None):
        s=min(config.SPEED_MAX,speed or config.SPEED_SLOW); self._set(-s,-s)
    def turn_left(self,speed=None):
        s=min(config.SPEED_MAX,speed or config.SPEED_TURN); self._set(-s,s)
    def turn_right(self,speed=None):
        s=min(config.SPEED_MAX,speed or config.SPEED_TURN); self._set(s,-s)
    def stop(self): self._set(0.0,0.0)
    def set_wheels(self,targets):
        """Per-wheel targets (fraction of the mph cap, + = that wheel forward), each clamped to
        SPEED_MAX. For rotation mode (rotate.py), where corners and middles need different
        speeds; everything else drives by side through _set()."""
        with self._lock:
            for w,v in targets.items():
                if w in self._target: self._target[w]=max(-config.SPEED_MAX,min(config.SPEED_MAX,float(v)))
    def brake(self):
        # Immediate, not ramped — for ESTOP/tilt-fault use where a 0.5s ramp-down is wrong.
        # throttle=0.0 is adafruit_motor's hard-brake (both legs driven); throttle=None coasts.
        with self._lock:
            # ALREADY STOPPED AND RELEASED -> NOTHING TO BRAKE (2026-10-02). A latched fault
            # re-issues emergency_stop() every tick; each one used to wake the sleeping drivers
            # and write brake, the ramp loop released them again after MOTOR_COAST_AFTER_S, and
            # round it went. Waking + braking writes each motor's two direction pins one after
            # the other, and for the instant between them the bridge DRIVES the motor: the owner
            # saw all the wheels twitching on the block. A stopped, released wheel has no motion
            # to brake, so leave it be. A brake while anything is moving or commanded is unchanged.
            if self._coasting and all(self._actual[w]==0.0 and self._target[w]==0.0 for w in self._WHEELS):
                self.current_speed=0.0; return
            if self._coasting: self._wake()   # a sleeping PCA9685 cannot brake; wake before driving
            # _write: one failing driver must not leave the wheels after it unbraked.
            for w in self._WHEELS: self._target[w]=0.0; self._actual[w]=0.0; self._write(w,0.0)
        self.current_speed=0.0
    # No *_for() blocking helpers here anymore — a sleep-based timed move on this thread would
    # stall whatever calls it (originally brain.py's tick loop, §2 of
    # docs/WildWilly_Claude_Fix_Implementation_Plan.md). Timed moves are now deadline-based and
    # live in safety.py's SafetyController, which is the only thing allowed to drive this class
    # per-tick.
    def cleanup(self):
        self._running=False; time.sleep(0.05)
        for m in self._motors.values(): m.throttle=None  # release — no holding current on exit
        for p in self._pcas:
            try: p.mode1_reg=p.mode1_reg|0x10            # and leave the oscillators asleep
            except Exception: pass
    # FR-500-003 (stall detection, Directive 5): what brain.py's stall check needs to know
    # "is this wheel currently commanded" -- target rather than actual/ramped value, since a
    # wheel legitimately reads near-zero counts during the ramp-up window right after a fresh
    # command starts (that is not a stall, just not-yet-moving) and the caller applies its own
    # settle grace period before trusting a stalled() reading either way.
    @property
    def commanded(self):
        with self._lock: return {w:self._target[w]!=0.0 for w in self._WHEELS}

# FR-600-001 (control steering servo) -- PARTIAL: set_angle()/center_all() below can
# drive any corner, but brain.py only ever calls center_all() once at startup; nothing
# commands per-corner steering angles during normal drive. Owner decision 2026-08-18
# (decision item #2, alongside the G-2 encoder-architecture call): deliberately deferred,
# not an oversight -- skid-steer (differential wheel speed only, wheels always centered)
# stays the only turning mechanism for now. Revisit once basic drive is live-verified;
# adding untested steering kinematics on top of a drive system that has never been
# live-tested at all would stack two unverified things at once.
class Steering:
    # PCA9685 @0x42; channels from config.STEER_* (CH0-3, CH8-9 since 2026-10-05). Kinematics (crab/point-turn coordination, per-corner
    # clearance limits) are undesigned in the master doc — this class only centers/holds
    # wheels straight; brain.py calls center_all() once at startup, nothing per-tick yet.
    _CORNERS={'lf':config.STEER_LF,'rf':config.STEER_RF,'lm':config.STEER_LM,
              'rm':config.STEER_RM,'lr':config.STEER_LR,'rr':config.STEER_RR}
    _PERIOD_US=1_000_000/config.SERVO_PWM_FREQ
    def __init__(self):
        self._pca=hw_sim.SimServoBank() if config.SIMULATE_HARDWARE else PCA9685(_i2c,address=config.STEER_PCA_ADDR)
        self._pca.frequency=config.SERVO_PWM_FREQ
        self._asleep=False; self._idle_since=time.monotonic(); self._running=True
        self._thread=threading.Thread(target=self._idle_loop,daemon=True); self._thread.start()
    # Idle release, added 2026-09-30. Centred steering servos hold their angle by being fed
    # pulses forever; stopping the pulses releases them. Safe here in a way it is not on the
    # arm -- a released steering servo cannot fall, and the linkage backdrives stiffly.
    def _idle_loop(self):
        while self._running:
            time.sleep(0.25)
            if (not self._asleep and self._idle_since is not None
                    and time.monotonic()-self._idle_since>=config.STEER_RELEASE_AFTER_S):
                self._sleep()
    def _sleep(self):
        try: self._pca.mode1_reg=self._pca.mode1_reg|0x10      # MODE1 bit4 SLEEP
        except Exception: pass
        self._asleep=True
    def _wake(self):
        if not self._asleep: return
        try:
            m=self._pca.mode1_reg
            if m & 0x10: self._pca.mode1_reg=m & ~0x10
            time.sleep(0.001)                                  # >=500us oscillator settle
        except Exception: pass
        self._asleep=False
    def release(self):
        """Drop the pulses now -- for park(), where geometry does the holding."""
        self._sleep()
    def _set_pulse(self,channel,us):
        self._wake(); self._idle_since=time.monotonic()
        us=max(config.SERVO_MIN_US,min(config.SERVO_MAX_US,us))
        self._pca.channels[channel].duty_cycle=int(us/self._PERIOD_US*65535)
    # FR-600-003 (travel limits): clamped to half_span_us below before any pulse is sent.
    def set_angle(self,corner,degrees):
        # degrees relative to center, clamped to the conservative servo range's half-span
        half_span_us=(config.SERVO_MAX_US-config.SERVO_MIN_US)/2
        us=self.center_us(corner)+(degrees/90.0)*half_span_us
        self._set_pulse(self._CORNERS[corner],us)
    @staticmethod
    def center_us(corner):
        """This corner's straight-ahead pulse (config.STEER_CENTER_US, from scripts/steer_jog.py)."""
        return config.STEER_CENTER_US.get(corner,config.SERVO_CENTER_US)
    def set_pulse(self,corner,us):
        """Raw pulse for one corner, clamped to SERVO_MIN_US..SERVO_MAX_US. Calibration only."""
        us=max(config.SERVO_MIN_US,min(config.SERVO_MAX_US,us))
        self._set_pulse(self._CORNERS[corner],us); return us
    def center_all(self):
        for corner,ch in self._CORNERS.items(): self._set_pulse(ch,self.center_us(corner))
    # Park brake -- owner's idea, 2026-09-30. Skid-steer never uses the corner servos, so
    # they are free for this: toe opposite corners against each other and the chassis cannot
    # roll in a straight line without the tyres scrubbing sideways. Then RELEASE them, and the
    # hold costs nothing to maintain -- geometry, not holding current. This is turning your
    # wheels into the kerb, and it is the only parking brake this rover has: a released or
    # braked drive motor still creeps on a slope.
    # ⚠ Angles are a starting point, not calibrated. §20.6 has never been run.
    def park(self,degrees=25.0):
        for corner,sign in (('lf',+1),('rf',-1),('lm',+1),('rm',-1),('lr',+1),('rr',-1)):
            self.set_angle(corner,sign*degrees)
        time.sleep(0.6)          # let them reach the angle BEFORE the pulses stop
        self.release()
    def unpark(self):
        self.center_all()
