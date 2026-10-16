"""Fin Ray fingers for Willie's gripper, two pieces per finger (2026-10-16, owner: PLA + TPU).

Input: the fitted long finger `~/Downloads/gripper_parts/gripper_finger_jaw10_ext8_jaw+50 (print 2).stl`
(10 mm thick; pivot bar with two 3.2 mm holes 16 mm apart; a 10 mm-wide jaw at 135 deg, 82.6 mm along its
inner face). Outputs to ~/Downloads (print 2 of each -- the same part works on both sides, flipped):
  finray_base_PLA.stl   the original finger cut just past the jaw root, plus a half-thickness tongue
                        (z 0-5) the TPU jaw bolts onto; two M3 hex nut traps underneath. Print flat.
  finray_jaw_TPU.stl    the Fin Ray: a thin front beam on the original gripping face (so the jaws still
                        close to 0 and open to 73 mm), a back beam from the root's back corner to the tip,
                        and angled ribs between them. Pressing on the face makes it wrap round the object.
                        Base block sits on the tongue (z 5-10). TPU 95A, print flat.
Fixing: 2 x M3 x 8 (button or socket head, counterbored) + 2 x M3 nuts per finger.

Jaw frame: s along the jaw from its root on the gripping face to the tip, t across it from the gripping
face (0) toward the back. The jaw's back is widened from 10 mm to FIN_W at the root (it stays clear of the
linkage: the back faces away from the other finger).
"""
import math,os
import numpy as np,trimesh
from shapely.geometry import Polygon,LineString,box as sbox
from shapely.ops import unary_union
from trimesh.creation import extrude_polygon,cylinder

SRC=os.path.expanduser('~/Downloads/gripper_parts/gripper_finger_jaw10_ext8_jaw+50 (print 2).stl')
OUT=os.path.expanduser('~/Downloads')
T_FINGER=10.0
O=np.array([14.6,11.6])                 # jaw root on the gripping face (finger frame, measured)
D=np.array([1,-1])/math.sqrt(2)         # along the jaw, root -> tip
N=np.array([-1,-1])/math.sqrt(2)        # across the jaw, gripping face -> back
JAW_LEN=82.6                            # original gripping face length
S_CUT=2.0                               # PLA ends here (just past the root); TPU starts here
LAP=15.0                                # tongue / base block length along s
FIN_W=20.0                              # Fin Ray depth at the root (t), tapering to 0 at the tip
FRONT=1.2; BACK=1.4; RIB=1.0            # TPU wall thicknesses
RIB_PITCH=7.0; RIB_TILT_DEG=15.0        # ribs lean toward the root (classic Fin Ray)
TIP_SOLID=4.0                           # solid nose
BOLT_S=(S_CUT+4.5,S_CUT+LAP-4.5); BOLT_T=4.0   # two bolts on the tongue (tongue spans t 0..10)
BOLT_D=3.3; HEAD_D=6.4; HEAD_DEPTH=1.8; NUT_AF=5.7; NUT_DEPTH=2.6

def st(s,t):
    """Jaw (s,t) -> finger (x,y)."""
    p=O+D*s+N*t; return (float(p[0]),float(p[1]))

def jaw_poly(pts): return Polygon([st(s,t) for s,t in pts])

def prism(poly,z0,z1):
    m=extrude_polygon(poly,z1-z0); m.apply_translation([0,0,z0]); return m

def U(ms): return trimesh.boolean.union(ms,engine='manifold')
def Dif(a,ms): return trimesh.boolean.difference([a]+list(ms),engine='manifold')

def bolt_cut(z0,z1,s,t,d): return cylinder(radius=d/2,height=z1-z0,sections=48,
    transform=trimesh.transformations.translation_matrix([*st(s,t),(z0+z1)/2]))

def hexagon(af,z0,z1,s,t):
    return cylinder(radius=af/math.sqrt(3),height=z1-z0,sections=6,
                    transform=trimesh.transformations.translation_matrix([*st(s,t),(z0+z1)/2]))

def base_pla():
    f=trimesh.load(SRC)
    # keep everything behind s=S_CUT (the pivot bar and the root), then add the half-thickness tongue
    keep=jaw_poly([(S_CUT,-60),(S_CUT,60),(-200,60),(-200,-60)])
    f=trimesh.boolean.intersection([f,prism(keep,-1,T_FINGER+1)],engine='manifold')
    tongue=prism(jaw_poly([(S_CUT-0.5,0),(S_CUT+LAP,0),(S_CUT+LAP,10.0),(S_CUT-0.5,10.0)]),0,T_FINGER/2)
    b=U([f,tongue])
    cuts=[bolt_cut(-1,T_FINGER+1,s,BOLT_T,BOLT_D) for s in BOLT_S]+[hexagon(NUT_AF,-1,NUT_DEPTH,s,BOLT_T) for s in BOLT_S]
    return Dif(b,cuts)

def finray_outline():
    s0,s1=S_CUT,S_CUT+JAW_LEN
    def back_t(s): return FIN_W*(s1-s)/(s1-(s0+LAP))   # back beam: FIN_W at the end of the base block -> 0 at the tip
    outer=Polygon([st(s0,0),st(s1,0),st(s0+LAP,FIN_W),st(s0,FIN_W)])
    # hollow inside: front beam FRONT thick, back beam BACK thick, base block and nose solid
    a=s0+LAP; b=s1-TIP_SOLID
    inner_pts=[]
    for s in np.linspace(a,b,40):
        inner_pts.append((s,back_t(s)-BACK/math.cos(math.atan(FIN_W/(s1-a)))))
    inner=Polygon([st(a,FRONT)]+[st(s,max(FRONT,t)) for s,t in inner_pts]+[st(b,FRONT)])
    ribs=[]
    tilt=math.radians(RIB_TILT_DEG)
    s=a+RIB_PITCH
    while s<b-2:
        # rib from the front beam at s, leaning toward the root as it goes back
        L=FIN_W*1.5
        p0=st(s,0); p1=st(s-math.tan(tilt)*L,L)
        ribs.append(LineString([p0,p1]).buffer(RIB/2,cap_style=2))
        s+=RIB_PITCH
    hollow=inner.difference(unary_union(ribs))
    return outer.difference(hollow)

def jaw_tpu():
    prof=finray_outline()
    body=prism(prof,0,T_FINGER)
    # base block sits on the PLA tongue: remove the tongue's volume (z 0..5) where they overlap
    tongue=prism(jaw_poly([(S_CUT-1,-1),(S_CUT+LAP,-1),(S_CUT+LAP,10.0),(S_CUT-1,10.0)]),-1,T_FINGER/2)
    body=Dif(body,[tongue])
    cuts=[bolt_cut(-1,T_FINGER+1,s,BOLT_T,BOLT_D) for s in BOLT_S]+[bolt_cut(T_FINGER-HEAD_DEPTH,T_FINGER+1,s,BOLT_T,HEAD_D) for s in BOLT_S]
    return Dif(body,cuts)

if __name__=='__main__':
    b=base_pla(); j=jaw_tpu()
    clash=trimesh.boolean.intersection([b,j],engine='manifold').volume
    b.export(os.path.join(OUT,'finray_base_PLA.stl')); j.export(os.path.join(OUT,'finray_jaw_TPU.stl'))
    print(f'base: {b.extents.round(1)} wt {b.is_watertight}; jaw: {j.extents.round(1)} wt {j.is_watertight}; overlap {clash:.2f} mm3')
    # the gripping face must stay on the original face line (jaws still close to 0)
    face=[st(s,0) for s in (S_CUT+LAP+5,S_CUT+JAW_LEN-5)]
    print('gripping face points (finger frame):',np.round(face,2).tolist())
