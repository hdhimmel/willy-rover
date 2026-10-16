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
  Shoulder_Rod.stl           8 mm D-rod (1 mm flat), 48 mm: crank -> 608 -> into the arm hub, stopping short
                             of the servo horn. Print LYING ON THE FLAT (layers lengthwise = strong in bending)
  Shoulder_Rod_Hub.stl       keys the rod to the arm: disk in the -Y horn recess (4 x M2 at r=7, like a horn),
                             sleeve into the arm's 10 mm hole, collar onto the bearing's inner race; D-bore
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
    lip=cyl_y(LIP_D,-CHEEK_IN+1,-BOSS_OUT+BRG_W-1)   # 2026-10-16: was -CHEEK_IN-1 -- left a 1 mm skin on the inner face
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

ROD_FLAT=1.0                        # D-flat depth: the rod prints on it (layers run lengthwise) and drives the crank
ROD_IN_ARM=8.0                      # rod end, |y| on the far side of the arm centre -- stops short of the servo horn recess
ROD_CLEAR=0.2

def _d_profile(d,flat,h):
    """D-section prism along z, the flat on +y, centred on the origin."""
    c=cylinder(radius=d/2,height=h,sections=96)
    return trimesh.boolean.intersection([c,box(bounds=[[-d,-d,-h],[d,d/2-flat,h]])],engine='manifold')

def rod():
    """2026-10-16 (owner: a printed rod): an 8 mm D-rod from past the crank into the arm hub. Printed
    lying on its flat, so bending (the spring pulls on the crank) runs along the layers."""
    y_end=-BOSS_OUT-CRANK_GAP-CRANK_T-1.0
    L=ROD_IN_ARM-y_end
    r=_d_profile(BRG_BORE,ROD_FLAT,L)
    r.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[0,1,0]))   # length along x
    r.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[1,0,0]))   # flat face down
    r.apply_translation(-r.bounds[0]); return r

SPACER_OD=11.5                       # passes the 14 mm lip hole; presses the 608's inner race only (OD ~12)
def spacer():
    """Arm face -> 608 inner race, fitted from OUTSIDE before the bearing: drop it in through the seat and
    the lip hole, then press the bearing in, then slide the rod through all of it. Printed on end."""
    L=(-ARM_FACE)-(-BOSS_OUT+BRG_W)-0.2
    t=D(cylinder(radius=SPACER_OD/2,height=L,sections=96),cylinder(radius=BRG_BORE/2+0.25,height=L+2,sections=96))
    t.apply_translation([0,0,L/2]); return t

def hub():
    """Keys the rod to the upper arm: disk in the -Y horn recess (4 x M2 at r=7, like a horn), a sleeve
    into the arm's 10 mm centre hole, a collar out to the 608's inner race. D-bore for the rod.
    Built in base coordinates along y, then stood on the disk for printing."""
    y_disk0=-ARM_FACE+RECESS_DEPTH-0.2
    y_inner=-BOSS_OUT+BRG_W
    # 2026-10-16 (owner): no collar -- with the horn on the servo side the arm can't drop in with 11 mm
    # sticking out of it. The hub is flush; the separate SPACER does the collar's job, fitted from outside.
    h=U(cyl_y(RECESS_D-0.4,y_disk0,-ARM_FACE),
        cyl_y(9.8,y_disk0-0.01,ROD_IN_ARM-1.0))                  # sleeve inside the arm's 10 mm hole
    for k in range(4):
        t=k*math.pi/2
        h=D(h,cyl_y(2.4,y_disk0-1,-ARM_FACE+0.01,x=AX_X+HORN_SCREW_R*math.cos(t),z=AX_Z+HORN_SCREW_R*math.sin(t)))
    bore=_d_profile(BRG_BORE+ROD_CLEAR,ROD_FLAT,200)
    bore.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[1,0,0]))
    bore.apply_translation([AX_X,0,AX_Z])
    h=D(h,bore)
    h.apply_translation([-AX_X,0,-AX_Z])
    h.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2,[1,0,0]))
    h.apply_translation([0,0,-h.bounds[0][2]]); return h

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
    parts={'Shoulder_Base_1servo':base(),'Shoulder_Rod':rod(),'Shoulder_Rod_Hub':hub(),'Shoulder_Spacer':spacer(),'Shoulder_Crank':crank()}
    for n,p in parts.items():
        f=os.path.join(OUT,n+'.stl'); p.export(f)
        print(f'{n}: watertight={p.is_watertight} vol={p.volume:.0f} size={np.ptp(p.bounds,axis=0).round(1)} -> {f}')
