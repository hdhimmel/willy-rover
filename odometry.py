import math,time,logsetup,config
log=logsetup.setup('odometry')

# §8 of docs/WildWilly_Claude_Fix_Implementation_Plan.md: differential-drive dead-reckoning pose
# estimate from wheel encoders. Six-wheel skid-steer, not true differential-drive — left/right
# wheel counts are each averaged across their 3 wheels (lf/lm/lr, rf/rm/rr) to smooth individual
# encoder noise, then treated as a single virtual left/right pair for the standard arc-update
# odometry math. This is dead-reckoning only: no slip correction and no fusion with the IMU
# heading. WHEEL_DIAMETER_M is owner-measured as of 2026-08-25 (4.00 in / 0.1016 m), but
# TRACK_WIDTH_M and ENCODER_COUNTS_PER_REV are both still placeholders (see config.py) — do not treat
# x/y/heading as accurate localization, only as a rough relative-motion estimate (§8's own
# instruction: "Do not claim localization accuracy beyond what the sensors support").

class Pose:
    __slots__=('x','y','heading','linear_velocity','angular_velocity','timestamp','stale')
    def __init__(self,x=0.0,y=0.0,heading=0.0,linear_velocity=0.0,angular_velocity=0.0,
                 timestamp=0.0,stale=True):
        self.x=x; self.y=y; self.heading=heading
        self.linear_velocity=linear_velocity; self.angular_velocity=angular_velocity
        self.timestamp=timestamp; self.stale=stale
    def __repr__(self):
        return (f'Pose(x={self.x:.3f},y={self.y:.3f},heading={math.degrees(self.heading):.1f}deg,'
                f'v={self.linear_velocity:.3f},w={self.angular_velocity:.3f},stale={self.stale})')

_LEFT=('lf','lm','lr'); _RIGHT=('rf','rm','rr')
_COUNTS_TO_M=(math.pi*config.WHEEL_DIAMETER_M)/config.ENCODER_COUNTS_PER_REV

def _avg(counts,wheels): return sum(counts[w] for w in wheels)/len(wheels)

def integrate(pose,d_left_m,d_right_m,dt,timestamp):
    """Pure function, no hardware/threading — independently testable (tests/test_odometry.py).
    d_left_m/d_right_m are this tick's per-side distance deltas in meters (already
    count->meters converted by the caller). Returns a new Pose; does not mutate the input."""
    if dt<=0: return pose
    d_center=(d_left_m+d_right_m)/2.0
    d_heading=(d_right_m-d_left_m)/config.TRACK_WIDTH_M
    heading_mid=pose.heading+d_heading/2.0
    x=pose.x+d_center*math.cos(heading_mid)
    y=pose.y+d_center*math.sin(heading_mid)
    heading=math.atan2(math.sin(pose.heading+d_heading),math.cos(pose.heading+d_heading))  # wrap to [-pi,pi]
    return Pose(x,y,heading,d_center/dt,d_heading/dt,timestamp,stale=False)

class Odometry:
    def __init__(self,encoders):
        self._encoders=encoders
        self._pose=Pose(timestamp=time.perf_counter())
        self._last_left=0.0; self._last_right=0.0

    def update(self):
        """Call once per brain tick. No-op (holds last pose, marks stale) if the encoder subsystem
        isn't healthy — §8.5-style safe failure mode: better to freeze the estimate than integrate
        a fault-driven garbage delta. Rollover: counts accumulate as unbounded Python ints in
        Encoders (software-summed per quadrature edge, not read from a fixed-width hardware
        register), so there is no rollover case to guard against here."""
        now=time.perf_counter()
        if not self._encoders.is_healthy:
            self._pose.stale=True
            return self._pose
        counts=self._encoders.counts
        left=_avg(counts,_LEFT); right=_avg(counts,_RIGHT)
        dt=now-self._pose.timestamp
        d_left_m=(left-self._last_left)*_COUNTS_TO_M
        d_right_m=(right-self._last_right)*_COUNTS_TO_M
        self._pose=integrate(self._pose,d_left_m,d_right_m,dt,now)
        self._last_left=left; self._last_right=right
        return self._pose

    @property
    def pose(self): return self._pose

    def reset(self,x=0.0,y=0.0,heading=0.0):
        log.info(f'Odometry reset to x={x} y={y} heading={math.degrees(heading):.1f}deg')
        counts=self._encoders.counts
        self._last_left=_avg(counts,_LEFT); self._last_right=_avg(counts,_RIGHT)
        self._pose=Pose(x,y,heading,0.0,0.0,time.perf_counter(),stale=False)
