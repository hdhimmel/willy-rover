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
        self._target=dict.fromkeys(self._WHEELS,0.0); self._actual=dict.fromkeys(self._WHEELS,0.0)
        self._lock=threading.Lock(); self.current_speed=0.0
        self._running=True
        self._thread=threading.Thread(target=self._ramp_loop,daemon=True); self._thread.start()
    # FR-500-004 (closed-loop speed) -- NOT implemented as closed-loop: this ramps the
    # commanded target by a fixed rate/time step (open-loop), it does not read encoder
    # counts_per_sec() to correct for a surface change. See sensors.py's Encoders class.
    def _ramp_loop(self):
        # FR-400-003: slew-rate limit so throttle changes smoothly rather than jumping instantly.
        dt=0.02; step=config.SPEED_RAMP_PER_S*dt
        while self._running:
            with self._lock:
                for w in self._WHEELS:
                    tgt=self._target[w]; cur=self._actual[w]
                    cur = tgt if abs(tgt-cur)<=step else cur+(step if tgt>cur else -step)
                    self._actual[w]=cur; self._motors[w].throttle=max(-1.0,min(1.0,cur))
                self.current_speed=(self._actual['lf']+self._actual['rf'])/2
            time.sleep(dt)
    # FR-400-001 (independent left/right control): six wheels individually targetable
    # (lf/lm/lr vs rf/rm/rr), driver assignment fixed by as-built wiring (0x60 left,
    # 0x61 right -- see CLAUDE.md).
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
# commands per-corner steering angles during normal drive yet (crab/point-turn
# kinematics are undefined in the master doc, per the comment below).
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
    def _set_pulse(self,channel,us):
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
