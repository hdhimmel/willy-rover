"""Two-piece ducted forearm joined with M3 screws and nuts (2026-10-15, owner).

Input: the one-piece ducted forearm from build_arm_ducts.py (`~/Downloads/On_Kol_duct10_<L>.stl`,
FOREARM_PIVOT_MM env var, default 265). Output:
  On_Kol_duct10_<L>_A.stl   wrist end + the LOWER half of the lap   (print flat, as is)
  On_Kol_duct10_<L>_B.stl   elbow end + the UPPER half of the lap   (print upright, supports under
                            the lap only -- its underside sits 14 mm up)

Joint: a half-lap LAP_MM long in the plain middle of the tongue, split at the duct's centre height,
so the 10 mm duct is a half-channel in each piece -- lay the wires in, then close it. The joint
section is widened to JOINT_W so four M3 bolts sit either side of the duct: head counterbores in B,
hex nut traps in A. Bolts M3 x BOLT_LEN.
"""
import math,os
import numpy as np,trimesh
from trimesh.creation import box,cylinder

L=float(os.environ.get('FOREARM_PIVOT_MM','265'))
DUCT_MM=float(os.environ.get('FOREARM_DUCT_MM','10'))   # 14 for the new body (owner, 2026-10-16)
SRC=os.path.expanduser(f'~/Downloads/On_Kol_duct{DUCT_MM:g}_{round(L)}.stl')
WRIST_AXLE=np.array([12.4,0,12.5]); ELBOW_HUB=np.array([152.3,0,20.0])
S=math.sqrt(L**2-(ELBOW_HUB[2]-WRIST_AXLE[2])**2)-(ELBOW_HUB[0]-WRIST_AXLE[0])
DUCT_Y,DUCT_Z=28.0,14.0; DUCT_R=DUCT_MM/2
X0,X1=56.0,98.0+S          # straight duct run (build_arm_ducts.py path)
LAP_MM=44.0
JOINT_W=37.0               # joint section width (y), centred on the duct (clears the nut traps at the bottom chamfer)
TAPER_MM=18.0              # blend from the arm's width to JOINT_W over this length each side
BOLT_DY=10.5               # bolts this far either side of the duct centre (clear of the arm's edge chamfer)
BOLT_D=3.4; HEAD_D=6.2; HEAD_DEPTH=3.2
NUT_AF=5.7; NUT_DEPTH=2.8  # M3 nut 5.5 AF + clearance
BOLT_LEN=30               # 26 mm of material + the nut

def hexagon(af,h,centre):
    r=af/math.sqrt(3)       # circumradius from across-flats
    return cylinder(radius=r,height=h,sections=6,transform=trimesh.transformations.translation_matrix(centre))

def build():
    m=trimesh.load(SRC)
    xj=(X0+X1)/2                                   # joint centre, middle of the straight duct run
    xa,xb=xj-LAP_MM/2,xj+LAP_MM/2
    # widen the joint: the tongue's own section height there, full JOINT_W wide
    sec=m.section(plane_origin=[xj,0,0],plane_normal=[1,0,0]); zb=sec.bounds[:,2]
    # 2026-10-15 (owner: "smooth the overlap to match the arm profile"): the joint is the arm's own
    # cross-section widened to JOINT_W (chamfered corners kept), blending back to the arm's width
    # over TAPER_MM each side -- a convex hull of the sections, so a straight, smooth swell.
    def ring(x,w=None):
        v=m.section(plane_origin=[x,0,0],plane_normal=[1,0,0]).vertices.copy()
        if w is not None:   # spread the two sides apart, so the corners keep the arm's own chamfer
            grow=(w-np.ptp(v[:,1]))/2
            v[:,1]=np.where(v[:,1]<DUCT_Y,v[:,1]-grow,v[:,1]+grow)
        return v
    pts=np.vstack([ring(xa-TAPER_MM),ring(xa-2,JOINT_W),ring(xj,JOINT_W),ring(xb+2,JOINT_W),ring(xb+TAPER_MM)])
    boss=trimesh.Trimesh(pts).convex_hull
    m=trimesh.boolean.union([m,boss],engine='manifold')
    duct=cylinder(radius=DUCT_R,height=xb-xa+40,transform=trimesh.transformations.rotation_matrix(math.pi/2,[0,1,0],[0,0,0]))
    duct.apply_translation([xj,DUCT_Y,DUCT_Z])
    m=trimesh.boolean.difference([m,duct],engine='manifold')
    big=1000
    a_keep=trimesh.boolean.union([box(bounds=[[-big,-big,-big],[xa,big,big]]),
                                  box(bounds=[[xa-1,-big,-big],[xb,big,DUCT_Z]])],engine='manifold')
    b_keep=trimesh.boolean.union([box(bounds=[[xb,-big,-big],[big,big,big]]),
                                  box(bounds=[[xa,-big,DUCT_Z],[xb+1,big,big]])],engine='manifold')
    A=trimesh.boolean.intersection([m,a_keep],engine='manifold')
    B=trimesh.boolean.intersection([m,b_keep],engine='manifold')
    cutsA=[];cutsB=[]
    for bx in (xa+LAP_MM*0.25,xa+LAP_MM*0.75):
        for sy in (-1,1):
            y=DUCT_Y+sy*BOLT_DY
            hole=cylinder(radius=BOLT_D/2,height=100,transform=trimesh.transformations.translation_matrix((bx,y,DUCT_Z)))
            cutsA.append(hole); cutsB.append(hole)
            cutsB.append(cylinder(radius=HEAD_D/2,height=2*HEAD_DEPTH,transform=trimesh.transformations.translation_matrix((bx,y,zb[1]))))
            cutsA.append(hexagon(NUT_AF,2*NUT_DEPTH,(bx,y,zb[0])))
    A=trimesh.boolean.difference([A,*cutsA],engine='manifold')
    B=trimesh.boolean.difference([B,*cutsB],engine='manifold')
    outA=SRC.replace('.stl','_A.stl'); outB=SRC.replace('.stl','_B.stl')
    A.export(outA)
    Bp=B.copy(); Bp.apply_translation(-Bp.bounds[0])
    Bp.export(outB)                                 # upright; support the lap's underside
    wall_top=zb[1]-HEAD_DEPTH-(DUCT_Z); wall_bot=DUCT_Z-zb[0]-NUT_DEPTH
    print(f'joint at x {xa:.0f}-{xb:.0f} mm, section z {zb[0]:.1f}-{zb[1]:.1f}, width {JOINT_W} mm')
    print(f'A: {A.extents.round(1)} watertight {A.is_watertight}  -> {outA}')
    print(f'B: {Bp.extents.round(1)} watertight {B.is_watertight} -> {outB}')
    print(f'clamp length per bolt {zb[1]-zb[0]-HEAD_DEPTH-NUT_DEPTH:.1f} mm -> M3 x {BOLT_LEN} with nuts; '
          f'bolt edge to duct edge {BOLT_DY-BOLT_D/2-DUCT_R:.1f} mm; to the side {JOINT_W/2-BOLT_DY-BOLT_D/2:.1f} mm')
    # reassembled check: A + B (B back in place) should be the joined forearm
    full=trimesh.boolean.union([A,B],engine='manifold')
    print(f'reassembled: length {full.extents[0]:.1f} mm, pieces overlap {trimesh.boolean.intersection([A,B],engine="manifold").volume:.1f} mm3')
    return A,Bp

if __name__=='__main__':
    build()
