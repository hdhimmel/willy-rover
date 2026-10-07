import math,time,config,logsetup
log=logsetup.setup('rotate')

# ROTATION MODE (owner, 2026-10-07): turn on the spot with the corner wheels steered onto the
# turning circle, instead of skid-turning six straight wheels.
#
# Why: a skid turn drags every tyre sideways. Measured 2026-10-07 on the floor: duty 0.6 for
# 1.5 s strained in place (+0.8 deg); duty 1.0 for 1.0 s turned +62 deg, "rough". With the four
# corners pointed along the circle round his centre, they roll instead of scrub; the middles sit
# on the centre line and roll straight.
#
# GEOMETRY. Corner at (+-a, +-b), a = WHEELBASE_M/2 (0.16), b = TRACK_WIDTH_M/2 (0.155). The wheel
# must be perpendicular to the radius, so |angle| = atan(a/b) = 46 deg, and:
#     front-left RIGHT, rear-right RIGHT, front-right LEFT, rear-left LEFT,  middles straight.
# The same angles serve both spin directions; the drive decides which way he goes (left spin =
# left wheels back, right wheels forward -- as the skid turn). Corners sit on a 0.22 m radius,
# middles on 0.155 m, so corners run 1.44x faster than the middles.
#
# STEERING SCALE, owner-measured 2026-10-07 by eye (no protractor): on all four corners +us
# turns the wheel RIGHT, ~15 deg per 200 us. 46 deg would need ~610 us, past the +-500 us the
# servos are allowed (SERVO_MIN/MAX_US, the narrow range). So the corners go to the limit
# (~37 deg) until a wider servo range is confirmed. Close is far better than straight.
#
# WATCHED THE WHOLE WAY (owner: "use the cameras and sensors to watch the turning"):
#   - IMU heading is the feedback: stop on the angle reached, never on a timer. A timeout only
#     catches a turn that is not happening.
#   - sonar + ToF: anything inside ROTATE_CLEAR_CM stops it; the corners sweep a wider circle
#     than the body.
#   - front camera: frame-to-frame horizontal shift is integrated into a second, independent
#     rotation estimate. If the IMU says he has turned and the camera says the scene has not
#     moved (or the reverse), one of them is wrong: stop and say so. Magnitudes only -- the
#     image's sign convention is not measured.
#   - encoders: Directive 5 stall detection in brain.py still runs every tick for commanded wheels.
#
# Shape: tick-serviced, like the other tasks. abort() is the preemption contract.

def corner_us(corner,deg):
    """Pulse for a corner wheel at `deg` degrees RIGHT of straight (negative = left), from the
    measured scale and per-corner direction, clamped to the allowed servo range."""
    sign=config.STEER_RIGHT_SIGN.get(corner,1)
    us=config.STEER_CENTER_US.get(corner,config.SERVO_CENTER_US)+sign*deg*config.STEER_US_PER_DEG
    return max(config.SERVO_MIN_US,min(config.SERVO_MAX_US,us))

def rotation_angle_deg():
    return math.degrees(math.atan2(config.WHEELBASE_M/2,config.TRACK_WIDTH_M/2))

def rotation_pulses():
    """Corner pulses for rotation mode; middles centred."""
    th=rotation_angle_deg()
    out={'lf':corner_us('lf',+th),'rr':corner_us('rr',+th),'rf':corner_us('rf',-th),'lr':corner_us('lr',-th)}
    for m in ('lm','rm'): out[m]=config.STEER_CENTER_US.get(m,config.SERVO_CENTER_US)
    return out

def wheel_targets(direction,speed):
    """Per-wheel drive fractions for a spin. direction +1 = left (CCW), -1 = right (CW).
    Corners on the larger radius get the full speed; middles scaled by radius."""
    r_corner=math.hypot(config.WHEELBASE_M/2,config.TRACK_WIDTH_M/2); r_mid=config.TRACK_WIDTH_M/2
    mid=speed*r_mid/r_corner
    t={}
    for w in ('lf','lm','lr','rf','rm','rr'):
        s=mid if w[1]=='m' else speed
        side=-1.0 if w[0]=='l' else 1.0           # left spin: left side back, right forward
        t[w]=side*direction*s
    return t

def _wrap(a): return (a+180.0)%360.0-180.0


class CameraYaw:
    """Integrated horizontal image shift -> degrees. Frame-to-frame (phase correlation on a small
    greyscale copy), because a whole turn soon leaves the first frame's view entirely."""
    def __init__(self,grab):
        self.grab=grab; self.prev=None; self.deg=0.0; self.ok=grab is not None
    def _small(self,f):
        import cv2,numpy as np
        g=cv2.cvtColor(f,cv2.COLOR_BGR2GRAY)
        g=cv2.resize(g,(160,90),interpolation=cv2.INTER_AREA)
        return np.float32(g)
    def update(self):
        if not self.ok: return None
        try:
            f=self.grab()
            if f is None: return None
            import cv2
            s=self._small(f)
            if self.prev is not None:
                (dx,_dy),_resp=cv2.phaseCorrelate(self.prev,s)
                self.deg+=abs(dx)*config.ROTATE_CAMERA_HFOV_DEG/160.0
            self.prev=s
            return self.deg
        except Exception:
            log.warning('Camera yaw estimate failed; continuing on IMU alone',exc_info=True)
            self.ok=False; return None


class Rotation:
    def __init__(self,steering,drive,imu,distances,camera_grab=None,say=None,clock=time.time):
        self.steering=steering; self.drive=drive; self.imu=imu; self.distances=distances
        self.camera_grab=camera_grab; self.say=say or (lambda t:None); self.clock=clock
        self.state='IDLE'   # IDLE|SETTLE|SPIN|DONE|FAILED|ABORTED
        self._fail_reason=''

    @property
    def active(self): return self.state in('SETTLE','SPIN')
    @property
    def fail_reason(self): return self._fail_reason

    def start(self,degrees):
        """degrees > 0 = left (CCW), < 0 = right (CW)."""
        if self.active: return False,'already rotating'
        if abs(degrees)<config.ROTATE_MIN_DEG: return False,'too small to rotate for'
        self._goal=float(degrees); self._dir=1 if degrees>0 else -1
        self._h0=self.imu.heading; self._t0=self.clock(); self._last_steer=0.0
        self._cam=CameraYaw(self.camera_grab if config.ROTATE_USE_CAMERA else None)
        self._pulses=rotation_pulses(); self._steer()
        self.state='SETTLE'; self._fail_reason=''
        log.info(f'Rotation start: {degrees:+.0f} deg from heading {self._h0:.1f}, corners {self._pulses}')
        return True,'started'

    def _steer(self):
        for c,us in self._pulses.items(): self.steering.set_pulse(c,us)
        self._last_steer=self.clock()

    def _turned(self):
        return _wrap(self.imu.heading-self._h0)

    def _finish(self,state,reason=''):
        self.drive.stop(); self.state=state; self._fail_reason=reason
        try: self.steering.center_all()
        except Exception: log.warning('Could not recentre steering after rotation',exc_info=True)
        if state=='DONE': log.info(f'Rotation done: turned {self._turned():+.1f} deg of {self._goal:+.0f}')
        else:
            log.warning(f'Rotation {state}: {reason} (turned {self._turned():+.1f} deg)')
            if state=='FAILED': self.say(f"I stopped turning: {reason}.")

    def abort(self,reason):
        if self.active: self._finish('ABORTED',reason)
        else: self.state='ABORTED'; self._fail_reason=reason

    def reset(self): self.state='IDLE'

    def tick(self,d,tilt):
        if not self.active: return
        now=self.clock()
        if now-self._last_steer>=config.ROTATE_RESTEER_S: self._steer()   # beat the idle release
        if self.state=='SETTLE':
            if now-self._t0>=config.ROTATE_SETTLE_S:
                self.drive.set_wheels(wheel_targets(self._dir,config.ROTATE_SPEED))
                self.state='SPIN'; self._spin_t0=now
            return
        near=min(d.get('front',999),d.get('left',999),d.get('right',999))
        if near<config.ROTATE_CLEAR_CM:
            self._finish('FAILED',f'something is {near:.0f} centimetres away'); return
        turned=self._turned()
        cam=self._cam.update()
        if (cam is not None and now-self._spin_t0>=config.ROTATE_CAMERA_GRACE_S and
                abs(abs(turned)-cam)>config.ROTATE_CAMERA_MAX_DISAGREE_DEG):
            self._finish('FAILED',f'my gyro says {abs(turned):.0f} degrees but my camera says {cam:.0f}'); return
        if turned*self._dir<-config.ROTATE_WRONG_WAY_DEG:
            self._finish('FAILED','I was turning the wrong way'); return
        if abs(turned)>=abs(self._goal)-config.ROTATE_STOP_EARLY_DEG:
            self._finish('DONE'); return
        if now-self._spin_t0>config.ROTATE_TIMEOUT_S:
            self._finish('FAILED',f'I only turned {abs(turned):.0f} of {abs(self._goal):.0f} degrees'); return
