import time, threading, config
import hw_sim
if not config.SIMULATE_HARDWARE:
    import board, busio
    from adafruit_motorkit import MotorKit
    from adafruit_pca9685 import PCA9685
    _i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)

class DriveBase:
    _WHEELS=('lf','lm','lr','rf','rm','rr')
    def __init__(self):
        if config.SIMULATE_HARDWARE:
            self._motors={w:hw_sim.SimMotor() for w in self._WHEELS}
        else:
            kits={a:MotorKit(i2c=_i2c,address=a) for a in (config.MOTORKIT_LEFT_ADDR,config.MOTORKIT_RIGHT_ADDR)}
            self._motors={w:getattr(kits[a],f'motor{p}') for w,(a,p) in config.MOTOR_PORT.items()}
            self._pcas=[k._pca for k in kits.values()]   # for sleep/wake; MotorKit holds it here
        if config.SIMULATE_HARDWARE: self._pcas=[]
        self._target=dict.fromkeys(self._WHEELS,0.0); self._actual=dict.fromkeys(self._WHEELS,0.0)
        self._lock=threading.Lock(); self.current_speed=0.0
        self._coasting=False; self._idle_since=time.monotonic()
        self._running=True
        self._thread=threading.Thread(target=self._ramp_loop,daemon=True); self._thread.start()
    # FR-500-004 (closed-loop speed) -- NOT implemented as closed-loop: this ramps the
    # commanded target by a fixed rate/time step (open-loop), it does not read encoder
    # counts_per_sec() to correct for a surface change. See sensors.py's Encoders class.
    # Idle power, added 2026-09-30. throttle=0.0 is adafruit_motor's HARD BRAKE -- both legs
    # driven -- so a stopped rover was holding six bridges on at 50Hz forever. Measured on the
    # +12V motor branch: 0.019A doing nothing. Once every wheel is commanded to zero AND has
    # finished ramping, release the bridges (throttle=None coasts) and sleep both MotorKit
    # PCA9685s. Any non-zero command wakes them first. brake() never comes through here.
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
                for w in self._WHEELS:
                    tgt=self._target[w]; cur=self._actual[w]
                    cur = tgt if abs(tgt-cur)<=step else cur+(step if tgt>cur else -step)
                    self._actual[w]=cur
                    if not self._coasting: self._motors[w].throttle=max(-1.0,min(1.0,cur))
                self.current_speed=(self._actual['lf']+self._actual['rf'])/2
                if not commanded and not self._coasting and                         all(self._actual[w]==0.0 for w in self._WHEELS):
                    now=time.monotonic()
                    if self._idle_since is None: self._idle_since=now
                    elif now-self._idle_since>=config.MOTOR_COAST_AFTER_S: self._coast()
            time.sleep(dt)
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
    def brake(self):
        # Immediate, not ramped — for ESTOP/tilt-fault use where a 0.5s ramp-down is wrong.
        # throttle=0.0 is adafruit_motor's hard-brake (both legs driven); throttle=None coasts.
        with self._lock:
            if self._coasting: self._wake()   # a sleeping PCA9685 cannot brake; wake before driving
            for w in self._WHEELS: self._target[w]=0.0; self._actual[w]=0.0; self._motors[w].throttle=0.0
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
    # PCA9685 @0x42, CH0-5 (§3.1/§10). Kinematics (crab/point-turn coordination, per-corner
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
        us=config.SERVO_CENTER_US+(degrees/90.0)*half_span_us
        self._set_pulse(self._CORNERS[corner],us)
    def center_all(self):
        for ch in self._CORNERS.values(): self._set_pulse(ch,config.SERVO_CENTER_US)
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
