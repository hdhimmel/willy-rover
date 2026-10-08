import time,config,logsetup
from rotate import corner_us
log=logsetup.setup('steer_override')

# FR-600-004 manual steering override (2026-10-08). The operator sets the wheels by voice or
# email ("steer left 20", "wheels straight") and they are held there. Until now the only override
# was the bench script (scripts/steer_jog.py), which needs the service stopped.
#
# Geometry: the front corners take the angle and the rear corners the opposite, middles straight
# -- the four-wheel-steer shape of a turn about the middle axle. Clamped twice (FR-600-003):
# to STEER_OVERRIDE_MAX_DEG here, and to SERVO_MIN_US..SERVO_MAX_US by corner_us().
#
# Parked only. Steered DRIVING (arc turns, crab) is still deferred (owner 2026-08-18), so the
# override is approved only with every wheel stopped (safety.approve_steer), and the moment the
# rover leaves IDLE for anything the wheels are centred -- or, for a fault, released where they
# are, so a fault never moves a servo.

_FAULTS=frozenset({'STALL_FAULT','SENSOR_FAULT','TILT_FAULT','OVERCURRENT_FAULT','SAFE_MODE',
                   'LOW_BATTERY','SHUTDOWN'})

def override_pulses(deg):
    """Corner pulses for `deg` (+ = right, - = left), clamped. Middles centred."""
    d=max(-config.STEER_OVERRIDE_MAX_DEG,min(config.STEER_OVERRIDE_MAX_DEG,float(deg)))
    out={'lf':corner_us('lf',d),'rf':corner_us('rf',d),'lr':corner_us('lr',-d),'rr':corner_us('rr',-d)}
    for m in ('lm','rm'): out[m]=config.STEER_CENTER_US.get(m,config.SERVO_CENTER_US)
    return out,d


class SteerOverride:
    def __init__(self,steering):
        self.steering=steering; self.deg=None; self._pulses=None; self._resteer_t=0.0

    @property
    def active(self): return self.deg is not None

    def apply(self,deg,now=None):
        """Write the pulses NOW -- the same tick the command is handled (one control cycle)."""
        self._pulses,self.deg=override_pulses(deg)
        for c,us in self._pulses.items(): self.steering.set_pulse(c,us)
        self._resteer_t=(now if now is not None else time.time())+config.ROTATE_RESTEER_S
        log.info(f'Steering override: {self.deg:+.0f} deg (front {"right" if self.deg>0 else "left"})'
                 if self.deg else 'Steering override: straight')
        return self.deg

    def tick(self,state,now=None):
        """Every tick. In IDLE: re-assert the pulses ahead of Steering's idle release, so the
        wheels are HELD (owner's gear fitting holds at 1500). Any other state ends the override."""
        if not self.active: return
        now=now if now is not None else time.time()
        if state=='IDLE':
            if now>=self._resteer_t:
                for c,us in self._pulses.items(): self.steering.set_pulse(c,us)
                self._resteer_t=now+config.ROTATE_RESTEER_S
            return
        self.end('fault' if state in _FAULTS else 'centre',reason=state)

    def end(self,how='centre',reason=''):
        """'centre' straightens the wheels; 'release' / 'fault' drops servo power where they are."""
        if not self.active: return
        self.deg=None; self._pulses=None
        try:
            if how=='centre': self.steering.center_all()
            else: self.steering.release()
        except Exception: log.warning('Steering override end failed',exc_info=True)
        log.info(f'Steering override ended ({how}{": "+reason if reason else ""})')
