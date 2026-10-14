"""Vision-guided reach (2026-10-14, owner): judge where an object is on the floor from the front
camera, drive until it is inside the arm's reach, then work the arm angles out instead of using
one taught pose.

Pure maths, no hardware -- everything here is testable off the rover.

  floor_point(det)       camera detection -> (x forward, y left) mm from the arm BASE AXIS,
                         plus the object's estimated size, or None
  solve(x, y, z)         arm angles (deg) putting the grip point at (x, y, z), or None
  pose_from_angles(a)    angles -> servo pulses {joint: us}, or None while a joint is uncalibrated
  plan_for(det)          ('reach', pose, info) | ('turn', deg) | ('forward'|'reverse', mm) |
                         ('fix', info, creep_mm) | ('fail', reason)
  reach_after_creep()    the pose once the blind creep is done
  fit_camera(samples)    camera height / tilt / HFOV from objects placed at taped spots

ANGLE CONVENTIONS (same as the arm measurement sheet, docs/drawings/WildWilly_Arm_Measurements.html)
  base      0 = arm pointing straight ahead, + = left
  shoulder  upper arm (its HOLE LINE, which is 10.9 deg off the part's edge) above horizontal-
            forward: 0 = level forward, 90 = straight up, >90 leaning back
  elbow     forearm relative to the upper arm's line: 0 = straight, + = folding down
  wrist     hand relative to the forearm: 0 = in line, + = curling down
So: forearm absolute angle = shoulder - elbow; hand absolute = shoulder - elbow - wrist.

CALIBRATION lives in config (None = not measured; the reach then refuses and says why):
  CAM_FRONT_HEIGHT_MM, CAM_FRONT_TILT_DEG, CAM_FRONT_HFOV_DEG, CAM_FRONT_X_MM, CAM_FRONT_Y_MM
  ARM_JOINT_CAL = {joint: (us_at_0_deg, us_per_deg)}
"""
import math
import config,logsetup
log=logsetup.setup('arm_ik')

JOINTS=('base','shoulder','elbow','wrist_pitch')


# ---------------------------------------------------------------- readiness

def missing():
    """Names of the calibration values still unset -- empty when the vision reach can run."""
    out=[k for k in ('CAM_FRONT_HEIGHT_MM','CAM_FRONT_TILT_DEG','CAM_FRONT_HFOV_DEG','CAM_FRONT_X_MM')
         if getattr(config,k,None) is None]
    cal=getattr(config,'ARM_JOINT_CAL',{}) or {}
    out+=[f'{j} angle' for j in JOINTS if not cal.get(j)]
    return out

def ready(): return getattr(config,'PICK_USE_IK',False) and not missing()


# ---------------------------------------------------------------- camera -> floor

def _ray(u_px,v_px,w,h,hfov_deg,tilt_deg):
    """Unit-free ray (forward, left, up) through pixel (u,v) of a camera looking forward and
    tilt_deg below horizontal. Square pixels assumed."""
    f=(w/2)/math.tan(math.radians(hfov_deg)/2)
    xr=(u_px-w/2)/f; yd=(v_px-h/2)/f
    t=math.radians(tilt_deg)
    # optical axis (cos t, 0, -sin t); image-down (-sin t, 0, -cos t); image-right (0, -1, 0)
    return (math.cos(t)-yd*math.sin(t), -xr, -math.sin(t)-yd*math.cos(t))

def _hit(ray,cam,z):
    """Where the ray from cam (x,y,z) meets the horizontal plane at height z, or None."""
    if ray[2]>=-1e-9 or cam[2]<=z: return None          # at or above the horizon
    lam=(z-cam[2])/ray[2]
    return (cam[0]+lam*ray[0],cam[1]+lam*ray[1]),lam

def floor_point(det,cam=None):
    """Detection -> {'x','y' (mm from the base axis, x forward, y left), 'size_mm', 'range_mm'}
    or None. The box's BOTTOM centre is taken as touching the floor to size the object; the
    object's centre is then placed at half that height (round things: a ball's centre)."""
    c=cam or _cam()
    if c is None: return None
    hgt,tilt,hfov,cx,cy=c
    x1,y1,x2,y2=det['bbox']; w=det['frame_w']; h=det['frame_h']
    pos=(cx,cy,hgt)
    bottom=_hit(_ray((x1+x2)/2,y2,w,h,hfov,tilt),pos,0.0)
    if bottom is None: return None
    rng=bottom[1]*math.sqrt(sum(r*r for r in _ray((x1+x2)/2,y2,w,h,hfov,tilt)))
    f=(w/2)/math.tan(math.radians(hfov)/2)
    size=(x2-x1)/f*rng                                   # width across the box at that range
    centre=_hit(_ray((x1+x2)/2,(y1+y2)/2,w,h,hfov,tilt),pos,size/2)
    if centre is None: return None
    (x,y),_=centre
    return {'x':x,'y':y,'size_mm':size,'range_mm':math.hypot(x,y)}

def _cam():
    vals=[getattr(config,k,None) for k in ('CAM_FRONT_HEIGHT_MM','CAM_FRONT_TILT_DEG','CAM_FRONT_HFOV_DEG',
                                             'CAM_FRONT_X_MM')]
    if any(v is None for v in vals): return None
    return (*vals,getattr(config,'CAM_FRONT_Y_MM',0.0) or 0.0)


def obstacle_cm(dets,cam=None):
    """Camera brake (2026-10-14): distance in cm from the FRONT OF THE WHEELS to the nearest
    detection standing in his path, judged where its box meets the floor, or None.
    A box cut off by the bottom of the frame is closer than the camera can see: it is placed
    at the nearest visible floor. CAMERA_BRAKE_OVERHANG_CM is taken off for table tops and seats
    that stick out past their legs."""
    c=cam or _cam()
    if c is None or not dets: return None
    hgt,tilt,hfov,cx,cy=c; best=None; half=config.CAMERA_BRAKE_HALF_WIDTH_MM
    for d in dets:
        x1,y1,x2,y2=d['bbox']; w=d['frame_w']; h=d['frame_h']
        v=min(y2,h-1)
        lft=_hit(_ray(x1,v,w,h,hfov,tilt),(cx,cy,hgt),0.0)
        rgt=_hit(_ray(x2,v,w,h,hfov,tilt),(cx,cy,hgt),0.0)
        mid=_hit(_ray((x1+x2)/2,v,w,h,hfov,tilt),(cx,cy,hgt),0.0)
        if mid is None or lft is None or rgt is None: continue
        ys=sorted((lft[0][1],rgt[0][1]))
        if ys[1]<-half or ys[0]>half: continue              # beside his path, not in it
        cm=(mid[0][0]-config.ARM_FRONT_REACH_CLEAR_MM)/10.0-config.CAMERA_BRAKE_OVERHANG_CM
        if y2>=config.CAMERA_BRAKE_CUTOFF_FRAC*h: cm-=config.CAMERA_BRAKE_CUTOFF_EXTRA_CM
        cm=max(0.0,cm)
        if best is None or cm<best: best=cm
    return best


# ---------------------------------------------------------------- arm IK

def solve(x,y,z,grip_mm=None,accept=None):
    """Angles {'base','shoulder','elbow','wrist_pitch'} (deg) putting the grip point at (x, y, z)
    mm (base axis frame, z above the floor), hand coming down from above, or None.
    Tries the hand straight down first, then tilted forward (more reach), per
    ARM_HAND_TILT_CHOICES_DEG; elbow-up solution; every joint inside its angle limits."""
    L1=config.ARM_L1_MM; L2=config.ARM_L2_MM; Lg=grip_mm or config.ARM_GRIP_POINT_MM
    sx=config.ARM_SHOULDER_FWD_MM; sz=config.ARM_SHOULDER_HEIGHT_MM; m=config.ARM_IK_MARGIN_MM
    base=math.degrees(math.atan2(y,x)); r=math.hypot(x,y)
    for tilt in config.ARM_HAND_TILT_CHOICES_DEG:
        ha=math.radians(-90+tilt)                          # hand absolute angle (down, tilted fwd)
        wx=r-Lg*math.cos(ha)-sx; wz=z-Lg*math.sin(ha)-sz   # wrist pivot relative to the shoulder
        d=math.hypot(wx,wz)
        if not (abs(L1-L2)+m<=d<=L1+L2-m): continue
        g=math.acos(max(-1,min(1,(L1*L1+d*d-L2*L2)/(2*L1*d))))
        th1=math.atan2(wz,wx)+g                            # elbow up
        ex=L1*math.cos(th1); ez=L1*math.sin(th1)
        thf=math.atan2(wz-ez,wx-ex)
        a={'base':base,'shoulder':math.degrees(th1),'elbow':math.degrees(th1-thf),
           'wrist_pitch':math.degrees(thf-ha)}
        if ez+sz<config.ARM_IK_MIN_ELBOW_HEIGHT_MM: continue   # elbow would hit the floor/wheels
        cb,sb=math.cos(math.radians(base)),math.sin(math.radians(base))
        pts=((sx+ex,ez+sz),(sx+wx,wz+sz),(r,z))                   # elbow, wrist, grip (radial, height)
        if any(_in_body(pr*cb,pr*sb,pz) for pr,pz in pts): continue
        if _within_angle_limits(a) and (accept is None or accept(a)): return a
    return None

def _in_body(x,y,z):
    hl,hw,top=config.ARM_IK_KEEPOUT_MM
    return abs(x)<=hl and abs(y)<=hw and z<=top

def _within_angle_limits(a):
    lim=getattr(config,'ARM_ANGLE_LIMITS_DEG',{}) or {}
    return all(lo<=a[j]<=hi for j,(lo,hi) in lim.items() if j in a)

def forward(a,grip_mm=None):
    """Grip point (x, y, z) mm for angles a -- the inverse of solve(), for tests and checks."""
    L1=config.ARM_L1_MM; L2=config.ARM_L2_MM; Lg=grip_mm or config.ARM_GRIP_POINT_MM
    t1=math.radians(a['shoulder']); tf=t1-math.radians(a['elbow']); th=tf-math.radians(a['wrist_pitch'])
    r=config.ARM_SHOULDER_FWD_MM+L1*math.cos(t1)+L2*math.cos(tf)+Lg*math.cos(th)
    z=config.ARM_SHOULDER_HEIGHT_MM+L1*math.sin(t1)+L2*math.sin(tf)+Lg*math.sin(th)
    b=math.radians(a['base'])
    return (r*math.cos(b),r*math.sin(b),z)

def pose_from_angles(a):
    """{joint: us} from angles, clamped to ARM_JOINT_LIMITS_US, or None if a joint is uncalibrated
    or the pulse would fall outside its limits."""
    cal=getattr(config,'ARM_JOINT_CAL',{}) or {}
    out={}
    for j in JOINTS:
        c=cal.get(j)
        if not c: return None
        us=int(round(c[0]+c[1]*a[j]))
        lo,hi=config.ARM_JOINT_LIMITS_US.get(j,(config.ARM_SERVO_MIN_US,config.ARM_SERVO_MAX_US))
        if not lo<=us<=hi:
            log.info(f'IK: {j} {a[j]:.1f} deg -> {us} us is outside {lo}-{hi}'); return None
        out[j]=us
    return out


# ---------------------------------------------------------------- reach or move

def plan_for(det):
    """What to do about a detection: reach it, or move so it comes into reach.
    ('reach', pose, info) | ('turn', deg) | ('forward', mm) | ('reverse', mm) | ('fail', reason)"""
    if missing(): return ('fail',"my camera and arm aren't calibrated yet: "+', '.join(missing()))
    p=floor_point(det)
    if p is None: return ('fail',"I can't tell where it is on the floor")
    z=min(p['size_mm']/2,config.ARM_IK_MAX_GRIP_HEIGHT_MM)
    a=solve(p['x'],p['y'],z,accept=lambda a: pose_from_angles(a) is not None)
    info=dict(p,z=z,angles=a)
    if a: return ('reach',pose_from_angles(a),info)
    base=math.degrees(math.atan2(p['y'],p['x']))
    lo,hi=(getattr(config,'ARM_ANGLE_LIMITS_DEG',{}) or {}).get('base',(-60,60))
    if not lo+5<=base<=hi-5:                                 # outside what the base can turn to
        return ('turn',base)
    band=reach_band(z)
    if band is None: return ('fail',"no arm position reaches the floor in front of me")
    best=band[0]+(band[1]-band[0])*config.PICK_IK_TARGET_FRAC  # far part of the band: less blind creep
    if abs(p['y'])>=best: return ('turn',base)
    tx=math.sqrt(best*best-p['y']*p['y'])                   # a straight creep keeps y
    if p['x']<=tx: return ('reverse',tx-p['x'])
    if det['bbox'][3]>=config.PICK_FIX_BOTTOM_FRAC*det['frame_h']:
        creep=p['x']-tx
        if creep>config.PICK_MAX_BLIND_MM: return ('forward',creep)
        return ('fix',info,creep)
    return ('forward',p['x']-tx)

def reach_after_creep(info,travelled_mm):
    """(pose, angles) for the remembered object after driving travelled_mm straight forward,
    or (None, None)."""
    a=solve(info['x']-travelled_mm,info['y'],info['z'],accept=lambda a: pose_from_angles(a) is not None)
    return (pose_from_angles(a),a) if a else (None,None)

def reach_band(z=35.0):
    """(nearest, furthest) range in mm, straight ahead, where solve() finds a reach that the
    calibrated pulses allow -- the band he drives into. None if there is none."""
    ok=[r for r in range(100,801,5)
        if solve(r,0,z,accept=lambda a: pose_from_angles(a) is not None if getattr(config,'ARM_JOINT_CAL',None) else True)]
    return (ok[0],ok[-1]) if ok else None


# ---------------------------------------------------------------- camera calibration

def fit_camera(samples,cam_x,cam_y=0.0,height=None):
    """samples: [{'bbox','frame_w','frame_h','x','y'}] -- detections of an object whose FLOOR
    CONTACT point was taped at (x forward, y left) mm from the base axis. Fits height, tilt and
    HFOV to the boxes' bottom-centres (height held at `height` if given, e.g. tape-measured).
    Returns (height_mm, tilt_deg, hfov_deg, rms_mm)."""
    def err(hgt,tilt,hfov):
        e=0.0
        for s in samples:
            x1,y1,x2,y2=s['bbox']
            hit=_hit(_ray((x1+x2)/2,y2,s['frame_w'],s['frame_h'],hfov,tilt),(cam_x,cam_y,hgt),0.0)
            if hit is None: return 1e12
            (px,py),_=hit; e+=(px-s['x'])**2+(py-s['y'])**2
        return e
    best=None
    # coarse grid, then refine around the best point
    H=[height] if height is not None else [150+10*i for i in range(46)]
    T=[0+2*i for i in range(31)]; F=[50+4*i for i in range(16)]
    for hgt in H:
        for tilt in T:
            for hfov in F:
                v=err(hgt,tilt,hfov)
                if best is None or v<best[0]: best=(v,hgt,tilt,hfov)
    _,hgt,tilt,hfov=best; step=(0.0 if height is not None else 5.0,1.0,2.0)
    for _ in range(60):
        moved=False
        for i,ds in enumerate(step):
            if ds==0: continue
            for sgn in (1,-1):
                cand=[hgt,tilt,hfov]; cand[i]+=sgn*ds
                v=err(*cand)
                if v<best[0]: best=(v,*cand); hgt,tilt,hfov=cand; moved=True
        if not moved: step=tuple(s/2 for s in step)
        if max(step)<0.01: break
    rms=math.sqrt(best[0]/len(samples))
    return hgt,tilt,hfov,rms
