"""One-servo shoulder: servo on one cheek, 608 bearing on the other, spring counterbalance (2026-10-15).

Owner: the two shoulder servos fought each other (opposite directions, CH2/CH3). Decision: ONE
DS3225 MG (25 kg.cm, 40 x 20 x 40.5 -- fits the original window) on the cheek on the ELBOW-SERVO
side of the upper arm (the side whose elbow end has the horn recess), the other side on the SAME
bearing as the elbow (608, 22 x 8 x 7; the elbow seat is 22.3 x 7 deep with the axle's 8 mm end in
it), plus an extension spring on a crank to take most of the arm's weight off the servo.

Input: the original yoke `Base.stl` / `Alt_Govde.stl` (MakerWorld licence -- NOT committed; path in
SHOULDER_BASE_SRC, default ~/Downloads/RC+Rover+with+Robot+Arm+6+DOF (1)/Base.stl).
Outputs to ~/Downloads:
  Shoulder_Base_1servo.stl   the yoke: +Y cheek keeps the servo window, -Y cheek window filled, an
                             outer boss with the 608 seat (pressed in from OUTSIDE against a 5 mm lip),
                             a spring-anchor pocket with a printed bar in the disk outside the -Y cheek
  Shoulder_Idler_Axle.stl    screws into the upper arm's -Y horn recess (4 x M2 at r=7, like a horn),
                             10 mm collar to the bearing's inner race, 8 mm through the bearing,
                             D-flat end for the crank
  Shoulder_Crank.stl         clamps on the D-flat (M3 grub), spring holes at r = 15 / 20 / 25 mm

Base frame (mm): turntable axis = z axis, cheeks at y = +-21..+-29, servo window x -0.5..40,
z 0..20, flange holes x -5 / 44.5. SHOULDER_X: the shoulder axis. A DS3225's spline is ~10 mm from
one end of its body; we take the end over the turntable centre (x = 9.7). CHECK on the old base
before printing: the spline should sit near the middle of the disk -- if it is at the far end,
set SHOULDER_X=29.8.

Crank: fit it pointing OPPOSITE the upper arm. Spring from the crank pin down to the anchor bolt
(below the axis): the pull lifts the arm hardest when the arm is level and nothing when it is
upright -- the same shape as gravity. Tie the spring to the crank pin with a short cord so it goes
slack (not compressed) when the arm is upright. Start on the r=15 hole and go out until the arm
just stays put level with the servo off.
"""
import math,os
import numpy as np,trimesh
from trimesh.creation import box,cylinder

SRC=os.environ.get('SHOULDER_BASE_SRC',os.path.expanduser('~/Downloads/RC+Rover+with+Robot+Arm+6+DOF (1)/Base.stl'))
OUT=os.path.expanduser('~/Downloads')
AX_X=float(os.environ.get('SHOULDER_X','9.7')); AX_Z=10.0
CHEEK_IN,CHEEK_OUT=21.0,29.0        # |y| of the cheek faces
ARM_FACE=15.0                       # |y| of the upper arm's faces (30 mm thick)
RECESS_D,RECESS_DEPTH=21.0,3.5      # horn recess in the upper arm
HORN_SCREW_R=7.0                    # 4 x 2 mm holes in the arm at r=7 (0/90/180/270 deg)
BRG_D,BRG_W,BRG_BORE=22.0,7.0,8.0   # 608, same as the elbow
SEAT_D=22.3; LIP_D=14.0             # lip touches the outer race only
BOSS_D,BOSS_OUT=32.0,33.0           # outer boss: cheek wall 21..33 = 12 mm (elbow seat wall is 12.5)
COLLAR_D=10.0                       # presses on the inner race; clears the M2 heads at r=7
CRANK_GAP=1.0; CRANK_T=5.0; CRANK_R=(15.0,20.0,25.0)
ANCHOR_Y=44.0; ANCHOR_POCKET=(10.0,14.0,7.0)   # x, y, depth into the disk top (z=-20)
DISK_TOP=-20.0

def cyl_y(d,y0,y1,x=AX_X,z=AX_Z,sections=96):
    """Cylinder along y between y0 and y1."""
    c=cylinder(radius=d/2,height=abs(y1-y0),sections=sections)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[1,0,0]))
    c.apply_translation([x,(y0+y1)/2,z]); return c

def U(*a): return trimesh.boolean.union(list(a),engine='manifold')
def D(a,*b): return trimesh.boolean.difference([a,*b],engine='manifold')

def base():
    m=trimesh.load(SRC)
    dz=-30.0-m.bounds[0][2]          # Base.stl sits 20 mm higher than Alt_Govde.stl; work in Alt_Govde's frame
    m.apply_translation([0,0,dz])
    # -Y cheek: fill the servo window, the 1.5 mm flange recess on its outer face and the four flange holes
    fill=box(bounds=[[-7.6,-CHEEK_OUT,-0.1],[47.1,-CHEEK_IN,20.1]])   # window + the outer flange recess
    holes=[cyl_y(3.4,-CHEEK_OUT,-CHEEK_IN,x=x,z=z) for x in (-5,44.5) for z in (5,15)]
    m=U(m,fill,*holes)
    # outer boss, then the 608 seat from outside against a lip
    m=U(m,cyl_y(BOSS_D,-BOSS_OUT,-CHEEK_OUT+0.5))
    seat=cyl_y(SEAT_D,-BOSS_OUT-1,-BOSS_OUT+BRG_W)
    lip=cyl_y(LIP_D,-CHEEK_IN-1,-BOSS_OUT+1)
    m=D(m,seat,lip)
    # spring anchor: a pocket in the disk top outside the -Y cheek with a printed 4 mm bar across it
    # (along x) for the spring hook -- a bolt would need a 90 mm hole out to the disk edge
    px,py,pd=ANCHOR_POCKET
    pocket=box(bounds=[[AX_X-px/2,-ANCHOR_Y-py/2,DISK_TOP-pd],[AX_X+px/2,-ANCHOR_Y+py/2,DISK_TOP+1]])
    bar=cylinder(radius=2.0,height=px+2,sections=48)
    bar.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[0,1,0]))
    bar.apply_translation([AX_X,-ANCHOR_Y,DISK_TOP-pd/2])
    pocket=D(pocket,bar)
    m=D(m,pocket); m.apply_translation([0,0,-dz]); return m

def axle():
    """Built along y in base coordinates, then laid flat for printing (disk down)."""
    y_disk0=-ARM_FACE+RECESS_DEPTH-0.2          # inside the recess
    y_inner=-BOSS_OUT+BRG_W                      # inner face of the bearing
    y_end=-BOSS_OUT-CRANK_GAP-CRANK_T-1.0
    disk=cyl_y(RECESS_D-0.4,y_disk0,-ARM_FACE)
    collar=cyl_y(COLLAR_D,-ARM_FACE,y_inner)
    shaft=cyl_y(BRG_BORE,y_inner,y_end)              # press fit in the 608 bore
    a=U(disk,collar,shaft)
    for k in range(4):
        t=k*math.pi/2
        a=D(a,cyl_y(2.4,y_disk0-1,-ARM_FACE+0.01,x=AX_X+HORN_SCREW_R*math.cos(t),z=AX_Z+HORN_SCREW_R*math.sin(t)))
    # D-flat on the crank end (1 mm off)
    a=D(a,box(bounds=[[AX_X-10,y_end-1,AX_Z+BRG_BORE/2-1],[AX_X+10,-BOSS_OUT-0.5,AX_Z+10]]))
    a.apply_translation([-AX_X,0,-AX_Z])
    a.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2,[1,0,0]))
    a.apply_translation([0,0,-a.bounds[0][2]]); return a

def crank():
    """Flat bar: hub on the D-flat with an M3 grub, three spring holes; printed flat."""
    hub_d=18.0; w=10.0; L=max(CRANK_R)+6
    c=U(cylinder(radius=hub_d/2,height=CRANK_T,sections=96),
        box(bounds=[[0,-w/2,-CRANK_T/2],[L,w/2,CRANK_T/2]]),
        cylinder(radius=w/2,height=CRANK_T,sections=64,transform=trimesh.transformations.translation_matrix([L,0,0])))
    bore=cylinder(radius=BRG_BORE/2+0.1,height=CRANK_T+2,sections=96)
    keep=box(bounds=[[-10,-10,-CRANK_T],[10,BRG_BORE/2-1+0.1,CRANK_T]])
    bore=trimesh.boolean.intersection([bore,keep],engine='manifold')
    c=D(c,bore)
    for r in CRANK_R:
        c=D(c,cylinder(radius=1.7,height=CRANK_T+2,sections=48,transform=trimesh.transformations.translation_matrix([r,0,0])))
    grub=cylinder(radius=1.25,height=hub_d,sections=48)          # M3 grub, self-tapped into 2.5 mm
    grub.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[1,0,0]))
    grub.apply_translation([0,hub_d/4+1,0])
    c=D(c,grub)
    c.apply_translation([0,0,CRANK_T/2]); return c

if __name__=='__main__':
    parts={'Shoulder_Base_1servo':base(),'Shoulder_Idler_Axle':axle(),'Shoulder_Crank':crank()}
    for n,p in parts.items():
        f=os.path.join(OUT,n+'.stl'); p.export(f)
        print(f'{n}: watertight={p.is_watertight} vol={p.volume:.0f} size={np.ptp(p.bounds,axis=0).round(1)} -> {f}')
