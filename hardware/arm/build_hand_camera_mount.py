"""Hand back plate with a two-piece case for the InnoMaker U20CAM-1080P (2026-10-14).

Starts from the ORIGINAL back plate of the hand (`El.stl`, downloaded as `hand back.stl`; not
stored here -- MakerWorld Standard Digital File License, see README.md).

  hand_back_camera.stl      the plate with the BACK of the case on its outer face: a leaning wall
                            with a shallow rim the board sits in, a pocket for the parts on the
                            board's back, and the cable hole through the middle (owner: cable out
                            the back)
  hand_camera_cap.stl       the FRONT of the case: a cap with the lens hole and corner bosses that
                            clamp the board. Print it face down.

Four M2 x 16 screws go through cap, board and wall, nuts behind the wall. The board's hole spacing
is not in InnoMaker's manual, so every hole is a slot covering 26-30 mm.

The camera looks past the ANGLED end of the plate (the fingertip end, owner), tilted CAM_TILT_DEG
down so the jaws sit mid-picture with the floor ahead still in view (owner: my call).

Plate frame: x along the plate (angled end at x=50), y across, z up; plate z 0-3, outer face z=3
(assumed). The case is kept clear of all six plate screws (screwdriver from above).
Case frame: u across the board (+y), v up the board face, w out of the face (the camera axis);
w=0 is the BACK of the board.
"""
import math,os
import numpy as np,trimesh
from shapely.geometry import Polygon
from trimesh.creation import extrude_polygon,box,cylinder

SRC=os.path.expanduser(r'~/Downloads/hand back.stl')
OUT=os.path.expanduser(r'~/Downloads/hand_back_camera.stl')
OUT_CAP=os.path.expanduser(r'~/Downloads/hand_camera_cap.stl')
CAM_TILT_DEG=20.0      # camera axis below the plate's direction
BOARD=32.0; BOARD_T=1.6
CAVITY=32.3            # inside of the case (board + clearance)
SHELL=1.05             # case side walls -> outside 34.4 mm: a 4 mm screwdriver still reaches the plate screws at y 4.8/43.5
WALL=5.0               # back wall behind the board
CAP_IN=4.0             # room in front of the board for its parts (the lens holder goes through)
CAP_FRONT=2.0          # cap face
LENS_HOLE=17.0         # M12 lens holder is usually 14-16 mm square
BOSS=5.0               # corner bosses in the cap that clamp the board
BOARD_CX,BOARD_CZ=28.0,23.5   # board centre, plate frame (raised so the cap clears the plate)
SLOT=(26.0,30.0); SLOT_W=2.4
POCKET=(24.0,24.0,2.5) # behind the board, for its parts
CABLE=(12.0,8.0)       # cable hole through the back wall (u, v)

OUTER=CAVITY+2*SHELL

def frame():
    t=math.radians(CAM_TILT_DEG)
    w=np.array([math.cos(t),0,-math.sin(t)]); v=np.array([math.sin(t),0,math.cos(t)]); u=np.array([0,1.0,0])
    T=np.eye(4); T[:3,0]=u; T[:3,1]=v; T[:3,2]=w; T[:3,3]=[BOARD_CX,24.15,BOARD_CZ]
    return T

def lbox(lo,hi):
    lo=np.array(lo,float); hi=np.array(hi,float)
    return box(extents=hi-lo,transform=trimesh.transformations.translation_matrix((lo+hi)/2))

def slots(w0,w1):
    """Four diagonal slots (26-30 mm spacing) as cutters along w from w0 to w1, case frame."""
    out=[]; h=w1-w0; wc=(w0+w1)/2
    for su in (-1,1):
        for sv in (-1,1):
            a=np.array([su*SLOT[0]/2,sv*SLOT[0]/2,wc]); b=np.array([su*SLOT[1]/2,sv*SLOT[1]/2,wc])
            for p in (a,b): out.append(cylinder(radius=SLOT_W/2,height=h,transform=trimesh.transformations.translation_matrix(p)))
            d=(b-a)/np.linalg.norm(b-a); T=np.eye(4); T[:3,0]=d; T[:3,1]=[-d[1],d[0],0]; T[:3,3]=(a+b)/2
            out.append(box(extents=(np.linalg.norm(b-a),SLOT_W,h),transform=T))
    return out

def cable_notch():
    """2026-10-16 (owner): the cable opening is a notch open to the case's BOTTOM edge (the D-C edge, toward
    the hand plate) beside corner D -- seen from behind, just right of the bottom-left screw slot -- through
    the back wall and the rim, so the cable lies in it. Case frame: the bottom edge is -v and corner D is +u
    (behind, the viewer's left is +u). CABLE[0] long along u, CABLE[1] deep from the edge, 1.5 mm from the slot."""
    o=OUTER/2
    u1=SLOT[0]/2-SLOT_W/2-1.5               # 1.5 mm in from the corner-D slot, running toward C
    return lbox((u1-CABLE[0],-o-1,-WALL-1),(u1,-o+CABLE[1],BOARD_T+1))

def back_piece(T):
    """Back wall + rim in the case frame, then the leaning support down to the plate."""
    o=OUTER/2; i=CAVITY/2
    wall=lbox((-o,-o,-WALL),(o,o,0))
    rim=trimesh.boolean.difference([lbox((-o,-o,0),(o,o,BOARD_T)),lbox((-i,-i,-1),(i,i,BOARD_T+1))],engine='manifold')
    cuts=[lbox((-POCKET[0]/2,-POCKET[1]/2,-POCKET[2]),(POCKET[0]/2,POCKET[1]/2,1)),
          cable_notch()]+slots(-WALL-1,1)
    case=trimesh.boolean.difference([trimesh.boolean.union([wall,rim],engine='manifold'),*cuts],engine='manifold')
    case.apply_transform(T)
    # support: the wall's bottom strip, run straight down to the plate
    corners=[T@np.array([uu,-o,ww,1]) for uu in (-o,o) for ww in (-WALL,0)]
    xs=[p[0] for p in corners]; zb=min(p[2] for p in corners)
    sec=Polygon([(min(xs),3.0),(max(xs),3.0),(max(xs),zb+1),(min(xs),zb+1)])
    foot=extrude_polygon(sec,OUTER); foot.apply_transform(np.array([[1,0,0,0],[0,0,1,24.15-OUTER/2],[0,1,0,0],[0,0,0,1]],float))
    if foot.volume<0: foot.invert()
    return trimesh.boolean.union([case,foot],engine='manifold')

def cap(T=None):
    o=OUTER/2; i=CAVITY/2; z0=BOARD_T; z1=BOARD_T+CAP_IN; z2=z1+CAP_FRONT
    shell=trimesh.boolean.difference([lbox((-o,-o,z0),(o,o,z2)),lbox((-i,-i,z0-1),(i,i,z1))],engine='manifold')
    b=BOSS
    bosses=[lbox((su*i-(b if su>0 else 0),sv*i-(b if sv>0 else 0),z0),(su*i+(0 if su>0 else b),sv*i+(0 if sv>0 else b),z1))
            for su in (-1,1) for sv in (-1,1)]
    c=trimesh.boolean.union([shell,*bosses],engine='manifold')
    lens=cylinder(radius=LENS_HOLE/2,height=CAP_FRONT*3,transform=trimesh.transformations.translation_matrix((0,0,z2-CAP_FRONT/2)))
    c=trimesh.boolean.difference([c,lens,*slots(z0-1,z2+1)],engine='manifold')
    if T is not None: c.apply_transform(T)
    return c

def build():
    T=frame()
    plate=trimesh.load(SRC)
    back=trimesh.boolean.union([plate,back_piece(T)],engine='manifold')
    back.export(OUT)
    capw=cap(T)                                   # in place, for the clearance checks
    flat=cap(); flat.apply_translation(-flat.bounds[0]); flat.export(OUT_CAP)
    clash=trimesh.boolean.intersection([capw,plate],engine='manifold').volume
    screws=[(9.01,3.97),(9.01,44.26),(33.02,43.46),(33.02,4.84),(44.34,32.13),(44.34,16.13)]
    blocked=[]
    for x,y in screws:
        shaft=cylinder(radius=2.0,height=80,transform=trimesh.transformations.translation_matrix((x,y,43)))
        if trimesh.boolean.intersection([shaft,trimesh.boolean.union([back,capw],engine='manifold')],engine='manifold').volume>0.5:
            blocked.append((x,y))
    print(f'back+plate: {back.extents.round(1)} mm, watertight {back.is_watertight}; cap: {flat.extents.round(1)} mm, watertight {flat.is_watertight}')
    print(f'cap overlaps the plate by {clash:.2f} mm3; screwdriver blocked at {blocked or "none"}')
    print(f'lowest point of the cap above the plate face: {capw.bounds[0][2]-3.0:.1f} mm')
    return back,flat

if __name__=='__main__':
    build()
