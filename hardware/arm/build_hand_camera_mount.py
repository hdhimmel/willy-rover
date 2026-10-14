"""Hand back plate with a mount for the InnoMaker U20CAM-1080P (2026-10-14).

Starts from the ORIGINAL back plate of the hand (`El.stl`, downloaded as `hand back.stl`; not
stored here -- MakerWorld Standard Digital File License, see README.md). Adds a leaning wall on the
outer face that holds the camera board looking past the ANGLED end of the plate (the end that
points at the fingertips, owner) and tilted CAM_TILT_DEG down, so the jaws sit in the middle of
the picture.

Camera (InnoMaker manual): 32 x 32 mm board, four 2.2 mm (M2) corner holes -- spacing NOT given,
so the holes are slots covering 26-30 mm; M12 lens holder. A pocket behind the board clears the
parts on its back. Screws: M2 x 8 with nuts on the back of the wall.

Plate frame: x along the plate (the angled end at x=50), y across, z up; the plate is z 0-3 and
the outer face is z=3 (assumed). Keeps clear of all six plate screws.
"""
import math,os,sys
import numpy as np,trimesh
from shapely.geometry import Polygon
from trimesh.creation import extrude_polygon,box,cylinder

SRC=os.path.expanduser(r'~/Downloads/hand back.stl')
OUT=os.path.expanduser(r'~/Downloads/hand_back_camera.stl')
CAM_TILT_DEG=20.0      # camera axis below the plate's direction (owner: my call -> 20: jaws mid-picture, floor ahead still in view)
BOARD=32.0             # board edge
WALL=5.0               # wall thickness behind the board
BOARD_CX,BOARD_CZ=28.0,19.5   # board centre (x along the plate, z above the plate bottom)
Y0,Y1=8.0,40.3         # wall width: clear of the screws at y 4-5 and 43-44
SLOT=(26.0,30.0)       # hole spacing range the slots cover
SLOT_W=2.4             # M2 clearance
POCKET=(24.0,24.0,2.5) # clearance behind the board for its parts (w, h, depth)

def build():
    plate=trimesh.load(SRC)
    t=math.radians(CAM_TILT_DEG)
    n=np.array([math.cos(t),0,-math.sin(t)])        # camera axis = board-face normal
    up=np.array([math.sin(t),0,math.cos(t)])        # up the board face
    c=np.array([BOARD_CX,0,BOARD_CZ])
    bot=c-up*BOARD/2; top=c+up*BOARD/2              # board's lower and upper edges (xz)
    bb=bot-n*WALL; tb=top-n*WALL                    # back of the wall
    # wall cross-section in the xz plane, run down to the plate's outer face
    sec=Polygon([(bot[0],3.0),(bot[0],bot[2]),(top[0],top[2]),(tb[0],tb[2]),(bb[0],3.0)]).convex_hull
    wall=extrude_polygon(sec,Y1-Y0)                  # extrudes along +z of its own frame
    # map (x, z-section) -> world: section x->x, section y->z, extrusion->y
    M=np.array([[1,0,0,0],[0,0,1,Y0],[0,1,0,0],[0,0,0,1]],float)
    wall.apply_transform(M)
    if wall.volume<0: wall.invert()
    yc=(Y0+Y1)/2
    # frame on the board face: u across (y), up along the face, n out of the face
    def at(u,v,dn=0.0): return c+np.array([0,u,0])+up*v+n*dn+np.array([0,yc,0])-np.array([0,0,0])
    def oriented_box(ext,centre):
        T=np.eye(4); T[:3,0]=[0,1,0]; T[:3,1]=up; T[:3,2]=n; T[:3,3]=centre
        return box(extents=ext,transform=T)
    cuts=[oriented_box((POCKET[0],POCKET[1],2*POCKET[2]),at(0,0,0))]
    for su in (-1,1):
        for sv in (-1,1):
            a=at(su*SLOT[0]/2,sv*SLOT[0]/2,-WALL/2); b=at(su*SLOT[1]/2,sv*SLOT[1]/2,-WALL/2)
            for p in (a,b):
                cuts.append(cylinder(radius=SLOT_W/2,height=WALL*3,transform=_axis(n,p)))
            mid=(a+b)/2; L=np.linalg.norm(b-a)
            d=(b-a)/L; T=np.eye(4); T[:3,0]=d; T[:3,2]=n; T[:3,1]=np.cross(n,d); T[:3,3]=mid
            cuts.append(box(extents=(L,SLOT_W,WALL*3),transform=T))
    wall=trimesh.boolean.difference([wall,*cuts],engine='manifold')
    part=trimesh.boolean.union([plate,wall],engine='manifold')
    part.export(OUT)
    lens_tip=c+n*25+np.array([0,yc,0])
    print(f'wrote {OUT}: {part.extents.round(1)} mm, watertight {part.is_watertight}, '
          f'volume {part.volume/1000:.1f} cm3 (plate {plate.volume/1000:.1f})')
    print(f'board bottom edge z {bot[2]:.1f} mm (plate face 3.0); 25 mm lens tip at x {lens_tip[0]:.1f} z {lens_tip[2]:.1f}')
    return part

def _axis(n,p):
    z=np.array([0,0,1.0]); v=np.cross(z,n); s=np.linalg.norm(v)
    R=np.eye(3) if s<1e-9 else trimesh.transformations.rotation_matrix(math.atan2(s,np.dot(z,n)),v)[:3,:3]
    T=np.eye(4); T[:3,:3]=R; T[:3,3]=p; return T

if __name__=='__main__':
    build()
