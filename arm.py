import time, threading
import config
import hw_sim
if not config.SIMULATE_HARDWARE:
    import board, busio
    from adafruit_pca9685 import PCA9685
    _i2c=busio.I2C(board.SCL,board.SDA,frequency=100000)

# FR-700-002 (preset positions): applied by brain.py's step sequences -- the wave through
# ARM_POSE_WAVE_HELLO, stow/home to ARM_POSE_REST (elbow opened first if the shoulder must move,
# 2026-10-06). Not yet run on the rover. center_all() below is no longer used for stow.
# FR-700-003 (joint limits) -- PARTIAL: _drive() below clamps to manufacturer-default
# ARM_SERVO_MIN_US/MAX_US, but real per-joint calibrated limits haven't been bench-set.
# FR-700-004 (arm stops on E-stop) -- PARTIAL: safety.SafetyController still only holds a
# drive_base reference (see safety.py's __init__), never an Arm instance, and
# emergency_stop() only calls self._drive.brake() -- there is no explicit "freeze the arm"
# call anywhere. What was a bigger problem until this fixed (2026-08-18): retrieval_task.py's
# _grasp() used to run its whole pulse sequence through blocking time.sleep() calls inside a
# single tick, so a tilt/battery/sensor-fault abort() had no way to even run until the arm had
# already finished moving. _grasp() is now a non-blocking, tick-serviced step sequence, so
# brain.py's Directive 1-4 abort() calls can land between any two arm-motion steps -- the arm
# still has no independent brake distinct from "stop commanding new pulses" (a PWM servo simply
# holds its last position, unlike a spinning drive motor, so this is a smaller residual gap than
# it looks), but the previous total blackout window is closed. brain.py's own wave-hello gesture
# was the other known blocking culprit (~1.5s via time.sleep()) -- also converted to a
# non-blocking, tick-serviced step machine (_start_wave()/_wave()) the same day, once it became
# clear the "IDLE-only, low risk" reasoning for leaving it alone assumed no systemd watchdog was
# configured, which turned out to be wrong (WatchdogSec=500ms is real -- see FRD v3.1 G-5).
def _all_outputs_off(addr):
    """Raw write, before the driver exists: ALL_LED_ON_H (0xFB)=0, ALL_LED_OFF_H (0xFD)=0x10
    (full-off bit) -- every channel to no pulse. Failure is logged, never fatal."""
    try:
        while not _i2c.try_lock(): pass
        try:
            _i2c.writeto(addr,bytes([0xFB,0x00])); _i2c.writeto(addr,bytes([0xFD,0x10]))
        finally: _i2c.unlock()
    except Exception as e:
        import logging; logging.getLogger('arm').warning(f'arm outputs-off at start failed: {e}')

class Arm:
    # PCA9685 @0x43, CH0-6 -- the hardware-verified 2026-09-17 map is in config.py (ARM_BASE=6
    # ... ARM_WRIST_PITCH=0), not the old base->gripper CH1-7 order. No per-joint safe limits
    # or IK exist yet -- §20.6 bench calibration hasn't been run. FR-700-001's current limit is
    # enforced every tick by brain._check_arm_current() (2026-10-02), which releases the arm. This is a driver + primitive
    # set_pulse interface only, clamped to manufacturer defaults; arm_jog.py is the tool for
    # producing real calibration numbers. No autonomous motion is wired to this class anywhere.
    # Channel numbers re-verified against hardware 2026-10-12 -- see the map in config.py.
    # The shoulder is TWO servos (CH2 + CH3) on one joint: 'shoulder' drives both with the SAME
    # pulse (_PAIRED). There is deliberately no way to drive one of them alone -- two servos on one
    # axis at different pulses fight each other.
    _JOINTS={'base':config.ARM_BASE,'shoulder':config.ARM_SHOULDER,
             'elbow':config.ARM_ELBOW,'wrist_rot':config.ARM_WRIST_ROT,'wrist_pitch':config.ARM_WRIST_PITCH,
             'gripper':config.ARM_GRIPPER}
    _PAIRED={'shoulder':(config.ARM_SHOULDER,config.ARM_SHOULDER_B)}
    def _channels(self,joint):
        if joint in self._PAIRED and (config.ARM_SHOULDER_PAIR or getattr(self,'_pair',False)):
            return self._PAIRED[joint]
        return (self._JOINTS[joint],)
    def drop_pair(self):
        """Disengage CH3 from the shoulder WITHOUT waking the chip or touching the idle timer.
        Every interrupted arm sequence ends here (outside review 2026-10-13: a stop, abort or
        teach timeout used to leave both shoulder servos driven together -- the arrangement that
        locked at 3-6 A that day)."""
        was=getattr(self,'_pair',False); self._pair=False
        if was and not config.ARM_SHOULDER_PAIR and not self._asleep:
            try: self._pca.channels[config.ARM_SHOULDER_B].duty_cycle=0
            except Exception: pass
        return was
    def _set_pair(self,on):
        """Engage CH3 on the shoulder (at CH2's current pulse) for a heavy move, or drop it."""
        self._pair=bool(on)
        ch=config.ARM_SHOULDER_B
        if on and 'shoulder' in self._driven:
            self._pca.channels[ch].duty_cycle=int(self._pulse['shoulder']/self._PERIOD_US*65535)
        elif not on and not config.ARM_SHOULDER_PAIR:
            self._pca.channels[ch].duty_cycle=0
        return int(on)
    _PERIOD_US=1_000_000/config.SERVO_PWM_FREQ
    def __init__(self,on_idle=None):
        # NO JUMP AT STARTUP (2026-10-02, seen on the rover). Releasing only SLEEPs the PCA9685,
        # and the chip keeps the last pulse widths; PCA9685()'s reset() writes MODE1=0, which
        # wakes it, so the shoulder jumped back to the previous run's pulse before any of our
        # code ran. Set ALL_LED_OFF_H full-off at register level FIRST: every channel then
        # outputs no pulse (servos limp) until something deliberately drives a joint.
        if not config.SIMULATE_HARDWARE: _all_outputs_off(config.ARM_PCA_ADDR)
        self._pca=hw_sim.SimServoBank() if config.SIMULATE_HARDWARE else PCA9685(_i2c,address=config.ARM_PCA_ADDR)
        self._pca.frequency=config.SERVO_PWM_FREQ
        self._pulse=dict.fromkeys(self._JOINTS,config.ARM_SERVO_CENTER_US)
        self._asleep=False; self._idle_since=time.monotonic(); self._running=True
        self._driven=set()   # joints commanded since boot -- pulse() is only real for these
        # 2026-10-13 (owner): after use the arm goes back to stow, never just released where it
        # is. When set, the idle timer calls on_idle() (the brain stows, then releases) instead
        # of releasing. Called from this thread: it must only set a flag.
        self.on_idle=on_idle
        if config.ARM_RELEASE_WHEN_IDLE:
            self._thread=threading.Thread(target=self._idle_loop,daemon=True); self._thread.start()
    # Idle release, added 2026-09-30. THIS IS SERVO PROTECTION, not power saving. The servo
    # fitted before 2026-09-17 held ~8A at 1500us indefinitely and was destroyed by it (see
    # center_all below) -- a joint stalling against its own mechanism cooks itself, and the
    # only thing that stops it is taking the pulses away. Idle draw is 0.35W, which is not
    # the point.
    # ⚠ A RELEASED ARM FALLS. config.ARM_RELEASE_AFTER_S is deliberately long, and the first
    #   test belongs with the arm low and nothing underneath it.
    def _idle_loop(self):
        while self._running:
            time.sleep(0.5)
            if (not self._asleep and self._idle_since is not None
                    and time.monotonic()-self._idle_since>=config.ARM_RELEASE_AFTER_S):
                if self.on_idle is not None:
                    self._idle_since=None          # once per idle spell; the next move re-arms it
                    try: self.on_idle()
                    except Exception: self.release()
                else:
                    self.release()
    def release(self):
        """Stop driving every joint. The arm goes limp and will move under gravity.
        Outputs are zeroed before the chip sleeps, so nothing that later wakes it -- a restart,
        a single-joint move -- can replay an old pulse on the other joints."""
        for ch in sorted({c for j in self._JOINTS for c in self._channels(j)}|{config.ARM_SHOULDER_B}):
            try: self._pca.channels[ch].duty_cycle=0
            except Exception: pass
        try: self._pca.mode1_reg=self._pca.mode1_reg|0x10      # MODE1 bit4 SLEEP
        except Exception: pass
        self._asleep=True; self._pair=False
    def _wake(self):
        if not self._asleep: return
        try:
            m=self._pca.mode1_reg
            if m & 0x10: self._pca.mode1_reg=m & ~0x10
            time.sleep(0.001)                                  # >=500us oscillator settle
        except Exception: pass
        self._asleep=False
    @property
    def released(self): return self._asleep
    def keep_alive(self):
        """Postpone the idle release (teach mode: the arm is holding a pose being taught)."""
        if not self._asleep: self._idle_since=time.monotonic()
    def _drive(self,joint,us):
        self._wake(); self._idle_since=time.monotonic()
        us=max(config.ARM_SERVO_MIN_US,min(config.ARM_SERVO_MAX_US,us))
        lo,hi=config.ARM_JOINT_LIMITS_US.get(joint,(config.ARM_SERVO_MIN_US,config.ARM_SERVO_MAX_US))
        us=max(lo,min(hi,us))
        for j,other,(olo,ohi),(clo,chi) in getattr(config,'ARM_COUPLED_LIMITS_US',()):
            if j==joint and other in self._driven and olo<=self._pulse.get(other,0)<=ohi:
                us=max(clo,min(chi,us))
        duty=int(us/self._PERIOD_US*65535)
        for ch in self._channels(joint): self._pca.channels[ch].duty_cycle=duty
        self._pulse[joint]=us; self._driven.add(joint)
        return us
    # FR-700-001 (control all arm joints): each joint on its own channel, except the shoulder.
    #
    # SHOULDER PAIR, 2026-10-12. CH2 and CH3 are the two shoulder servos. Measured with new servos
    # fitted (horns set at 1500us): each ALONE raises the shoulder as the pulse goes UP, and both
    # together at the SAME pulse held at ~0.1A (no fighting) and moved the arm smoothly. So they
    # get identical pulses -- NOT mirrored (2*center - x), which would make them fight. The
    # 09-17 "not a pair" finding was made while one of the two servos was dead.
    def set_pulse(self,joint,us):
        if joint=='shoulder_pair': self._wake(); self._idle_since=time.monotonic(); return self._set_pair(us)
        return self._drive(joint,us)
    def pulse(self,joint): return self._pulse[joint]
    def was_driven(self,joint):
        """False until the joint has been commanded this boot: pulse() then holds a placeholder
        (centre), not the servo's real position -- never step FROM it."""
        return joint in self._driven
    @property
    def joints(self): return list(self._JOINTS)
    # THE ELBOW IS EXCLUDED, DELIBERATELY. ARM_SERVO_CENTER_US drives CH1 into the top of Willy:
    # the servo fitted before 2026-09-17 held ~8A at 1500us indefinitely and was destroyed by it.
    # Centring every joint on startup would repeat that on every boot. The elbow has no known
    # safe centre until §20.6 calibration establishes one, so it is left where it is.
    def center_all(self):
        for j in self.joints:
            if j=='elbow': continue
            self.set_pulse(j,config.ARM_SERVO_CENTER_US)
