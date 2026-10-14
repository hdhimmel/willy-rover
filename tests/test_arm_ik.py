import math,os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import config,arm_ik

# 2026-10-14 vision-guided reach: camera -> floor, arm IK, drive-into-reach, camera fit.

CAM=dict(CAM_FRONT_HEIGHT_MM=330.0,CAM_FRONT_TILT_DEG=15.0,CAM_FRONT_HFOV_DEG=66.0,
         CAM_FRONT_X_MM=110.0,CAM_FRONT_Y_MM=-20.0)
W,H=1280,720
# made-up but self-consistent servo calibration: (us at 0 deg, us per deg)
CAL={'base':(1500,10.0),'shoulder':(1050,10.0),'elbow':(1000,8.0),'wrist_pitch':(1000,6.0)}

@pytest.fixture
def cam(monkeypatch):
    for k,v in CAM.items(): monkeypatch.setattr(config,k,v)

@pytest.fixture
def cal(monkeypatch,cam):
    monkeypatch.setattr(config,'ARM_JOINT_CAL',CAL)
    monkeypatch.setattr(config,'ARM_JOINT_LIMITS_US',{'elbow':(800,2500),'wrist_pitch':(500,2500)})
    monkeypatch.setattr(config,'PICK_USE_IK',True)

def _pixel(p,c=CAM):
    """Project world point p (x fwd, y left, z up; mm, base-axis frame) to (u, v)."""
    t=math.radians(c['CAM_FRONT_TILT_DEG']); f=(W/2)/math.tan(math.radians(c['CAM_FRONT_HFOV_DEG'])/2)
    d=(p[0]-c['CAM_FRONT_X_MM'],p[1]-c['CAM_FRONT_Y_MM'],p[2]-c['CAM_FRONT_HEIGHT_MM'])
    ax=(math.cos(t),0,-math.sin(t)); dn=(-math.sin(t),0,-math.cos(t)); rt=(0,-1,0)
    dot=lambda a,b: sum(i*j for i,j in zip(a,b))
    z=dot(d,ax); return (W/2+f*dot(d,rt)/z, H/2+f*dot(d,dn)/z)

def _ball(x,y,r=35.0):
    """A detection box for a ball of radius r resting at (x, y)."""
    u,_=_pixel((x,y,r)); _,v2=_pixel((x,y,0)); _,v1=_pixel((x,y,2*r))
    c=CAM; t=math.radians(c['CAM_FRONT_TILT_DEG'])
    depth=(x-c['CAM_FRONT_X_MM'])*math.cos(t)+(c['CAM_FRONT_HEIGHT_MM']-r)*math.sin(t)
    f=(W/2)/math.tan(math.radians(c['CAM_FRONT_HFOV_DEG'])/2); half=f*r/depth
    return {'class':'sports ball','conf':0.9,'bbox':(u-half,v1,u+half,v2),'frame_w':W,'frame_h':H}

def test_floor_point_recovers_where_the_ball_is(cam):
    for x,y in ((500,0),(700,150),(450,-120),(900,60)):
        p=arm_ik.floor_point(_ball(x,y))
        assert abs(p['x']-x)<15 and abs(p['y']-y)<10, (x,y,p)
        assert 55<p['size_mm']<85                       # a 70 mm ball, roughly

def test_floor_point_above_the_horizon_is_none(cam):
    det={'bbox':(600,0,640,10),'frame_w':W,'frame_h':H}
    assert arm_ik.floor_point(det) is None

def test_uncalibrated_camera_gives_nothing(monkeypatch):
    monkeypatch.setattr(config,'CAM_FRONT_HEIGHT_MM',None)
    assert arm_ik.floor_point(_ball(500,0) if False else {'bbox':(0,0,1,1),'frame_w':W,'frame_h':H}) is None

def test_ik_round_trip():
    hits=0
    for x,y,z in ((260,0,35),(300,80,35),(320,-60,20),(280,0,50),(350,0,35),(300,250,35)):
        a=arm_ik.solve(x,y,z)
        if a is None: continue
        hits+=1
        fx,fy,fz=arm_ik.forward(a)
        assert abs(fx-x)<0.5 and abs(fy-y)<0.5 and abs(fz-z)<0.5
        assert a['shoulder']>a['shoulder']-a['elbow']   # elbow up: forearm below the upper arm
    assert hits>=3

def test_ik_out_of_reach_is_none():
    assert arm_ik.solve(1200,0,35) is None and arm_ik.solve(0,0,35) is None

def test_pulses_need_every_joint_calibrated(monkeypatch):
    a={'base':0,'shoulder':40,'elbow':80,'wrist_pitch':30}
    monkeypatch.setattr(config,'ARM_JOINT_CAL',dict(CAL,shoulder=None))
    assert arm_ik.pose_from_angles(a) is None
    monkeypatch.setattr(config,'ARM_JOINT_CAL',CAL)
    monkeypatch.setattr(config,'ARM_JOINT_LIMITS_US',{})
    assert arm_ik.pose_from_angles(a)=={'base':1500,'shoulder':1450,'elbow':1640,'wrist_pitch':1180}

def test_not_ready_lists_what_is_missing(monkeypatch):
    monkeypatch.setattr(config,'CAM_FRONT_TILT_DEG',None)
    monkeypatch.setattr(config,'ARM_JOINT_CAL',dict(CAL,elbow=None))
    m=arm_ik.missing()
    assert 'CAM_FRONT_TILT_DEG' in m and 'elbow angle' in m and not arm_ik.ready()
    assert arm_ik.plan_for({'bbox':(0,0,1,1),'frame_w':W,'frame_h':H})[0]=='fail'

def test_ik_never_reaches_through_the_body():
    assert arm_ik.solve(0,0,35) is None and arm_ik.solve(150,0,35) is None

def test_original_140mm_forearm_cannot_reach_the_floor(monkeypatch):
    monkeypatch.setattr(config,'ARM_L2_MM',140.1)
    assert all(arm_ik.solve(r,0,35) is None for r in range(220,600,10))

def test_plan_reach_drive_or_turn(cal,monkeypatch):
    band=arm_ik.reach_band(35)
    assert band and band[0]<band[1]
    mid=(band[0]+band[1])/2
    act=arm_ik.plan_for(_ball(mid,0))
    assert act[0]=='reach' and set(act[1])=={'base','shoulder','elbow','wrist_pitch'}
    assert arm_ik.plan_for(_ball(band[1]+300,0))[0]=='forward'
    monkeypatch.setattr(config,'ARM_ANGLE_LIMITS_DEG',{'base':(-30,30)})
    act=arm_ik.plan_for(_ball(500,400))
    assert act[0]=='turn' and act[1]>0                  # off to the left past the base: turn left

def test_fit_camera_recovers_height_tilt_fov():
    spots=[(450,0),(600,0),(800,0),(600,200),(600,-200),(1000,100)]
    samples=[dict(_ball(x,y),x=x,y=y) for x,y in spots]
    hgt,tilt,hfov,rms=arm_ik.fit_camera(samples,CAM['CAM_FRONT_X_MM'],CAM['CAM_FRONT_Y_MM'])
    assert abs(hgt-330)<8 and abs(tilt-15)<1.0 and abs(hfov-66)<2.0 and rms<5

def test_fit_camera_with_the_height_tape_measured():
    spots=[(450,0),(600,0),(800,0),(600,200)]
    samples=[dict(_ball(x,y),x=x,y=y) for x,y in spots]
    hgt,tilt,hfov,rms=arm_ik.fit_camera(samples,CAM['CAM_FRONT_X_MM'],CAM['CAM_FRONT_Y_MM'],height=330)
    assert hgt==330 and abs(tilt-15)<1.0 and abs(hfov-66)<2.0 and rms<5

def test_plan_takes_the_last_fix_near_the_bottom_of_the_image(cal,monkeypatch):
    # a ball just above the bottom edge of the real camera's view (current body calibration)
    for k,v in dict(CAM_FRONT_HEIGHT_MM=280,CAM_FRONT_TILT_DEG=19.8,CAM_FRONT_HFOV_DEG=71.4,
                    CAM_FRONT_X_MM=140,CAM_FRONT_Y_MM=0).items(): monkeypatch.setattr(config,k,v)
    det={'class':'sports ball','conf':0.9,'bbox':(570,560,710,700),'frame_w':W,'frame_h':H}
    act=arm_ik.plan_for(det)
    assert act[0]=='fix' and 0<act[2]<=config.PICK_MAX_BLIND_MM
    info=act[1]; pose,a=arm_ik.reach_after_creep(info,act[2])
    assert pose is not None
    x,y,z=arm_ik.forward(a)
    assert abs(x-(info['x']-act[2]))<1 and abs(y-info['y'])<1
    high={'class':'sports ball','conf':0.9,'bbox':(600,300,670,365),'frame_w':W,'frame_h':H}
    assert arm_ik.plan_for(high)[0]=='forward'           # further out: keep driving while it is visible
