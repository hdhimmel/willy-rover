import json,math,os,time,config,logsetup
log=logsetup.setup('reach_table')

# Reach by example (owner, 2026-10-13: "see an object, then calculate the position his arm needs to
# be in to touch it"). Willie has no measured camera geometry and no arm kinematics, so instead of
# calculating from angles he LEARNS: with the arm stowed he notes where an object sits in the front
# camera image, then the owner teaches the arm pose that touches it ("teach your arm" ... "remember
# this reach"). Later, for an object seen at (x,y), the pose is blended from the nearest taught
# spots (inverse-distance weights in image space). That absorbs the wide lens's distortion and the
# servos' slack without modelling either.
#
# Image coordinates are the detection box CENTRE as fractions of the frame (x right, y down), arm
# stowed (the arm blocks the camera once it is down). Each entry carries ARM_POSE_EPOCH: after a
# servo/horn change old entries are ignored, like taught poses.

JOINTS=('shoulder','elbow','wrist_pitch','base')

def _path(): return os.path.join(config.WILLY_MEMORY_ROOT,config.REACH_TABLE_PATH)

def load():
    try:
        with open(_path()) as f: rows=json.load(f)
    except (OSError,ValueError): return []
    return [r for r in rows if r.get('epoch')==config.ARM_POSE_EPOCH]

def add(xy,pose):
    try:
        with open(_path()) as f: rows=json.load(f)
    except (OSError,ValueError): rows=[]
    # float()/int(): detections carry numpy float32, which json cannot write (2026-10-13 live:
    # the save crashed the tick and left a half-written file). Written to a temp file and
    # renamed, so a failure can never corrupt the table.
    rows.append({'xy':[round(float(xy[0]),4),round(float(xy[1]),4)],
                 'pose':{j:int(pose[j]) for j in JOINTS if j in pose},
                 'epoch':config.ARM_POSE_EPOCH,'t':time.time()})
    tmp=_path()+'.tmp'
    with open(tmp,'w') as f: json.dump(rows,f,indent=1)
    os.replace(tmp,_path())
    return len([r for r in rows if r.get('epoch')==config.ARM_POSE_EPOCH])

def clear():
    try: os.remove(_path())
    except OSError: pass

def box_xy(det):
    x1,y1,x2,y2=det['bbox']
    return (float((x1+x2)/2/det['frame_w']),float((y1+y2)/2/det['frame_h']))

def nearest(xy,rows=None):
    rows=load() if rows is None else rows
    if not rows: return None,None
    best=min(rows,key=lambda r: math.dist(xy,r['xy']))
    return best,math.dist(xy,best['xy'])

def pose_for(xy,rows=None):
    """(pose, distance to the nearest taught spot) -- pose blended from up to REACH_TABLE_K nearest
    spots by inverse distance; None if nothing is taught or the nearest spot is further than
    REACH_TABLE_MAX_DIST (outside what he has learned: drive closer instead of guessing)."""
    rows=load() if rows is None else rows
    if not rows: return None,None
    ranked=sorted(rows,key=lambda r: math.dist(xy,r['xy']))[:config.REACH_TABLE_K]
    d0=math.dist(xy,ranked[0]['xy'])
    if d0>config.REACH_TABLE_MAX_DIST: return None,d0
    if d0<1e-6: return dict(ranked[0]['pose']),0.0
    w=[1.0/max(1e-6,math.dist(xy,r['xy']))**2 for r in ranked]
    pose={}
    for j in JOINTS:
        have=[(wi,r['pose'][j]) for wi,r in zip(w,ranked) if j in r['pose']]
        if have: pose[j]=int(round(sum(wi*v for wi,v in have)/sum(wi for wi,_ in have)))
    return pose,d0
