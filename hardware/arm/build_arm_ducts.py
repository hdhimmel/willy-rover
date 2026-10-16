import trimesh,numpy as np
from trimesh.creation import cylinder,icosphere,box
def capsule_path(pts,r,sections=48):
    parts=[]
    for a,b in zip(pts[:-1],pts[1:]):
        parts.append(cylinder(radius=r,segment=[a,b],sections=sections))
    for p in pts: parts.append(icosphere(subdivisions=3,radius=r).apply_translation(p))
    return trimesh.boolean.union(parts,engine='manifold')

# ---------- upper arm (Alt_Kol / Arm.stl): 18 mm duct ----------
up=trimesh.load(r"C:\Users\himme\Downloads\Arm.stl")
S=np.array([160.13,160.13,27.51]);E=np.array([21.18,21.18,65.25])
n=np.array([-0.70710678,0.70710678,0.0])          # +n face = elbow horn-recess face (servo side)
u=(E-S)/np.linalg.norm(E-S); v=np.cross(n,u)
P=lambda a,b,c=0: S+u*a+v*b+n*c
A=(45,-10); B=(168,-38)
d=np.array(B)-np.array(A); d=d/np.linalg.norm(d)
Q1=np.array(A)+25*d; Q2=np.array(B)-25*d
up_path=[P(*A,22),P(*Q1),P(*Q2),P(*B,22)]
up_cut=capsule_path(up_path,9.0)
# fill the I-beam face grooves along the duct run (web is only 20 mm thick)
a3,b3=P(*Q1),P(*Q2); ax_=(b3-a3)/np.linalg.norm(b3-a3); L=np.linalg.norm(b3-a3)+50
Tb=np.eye(4); Tb[:3,0]=ax_; Tb[:3,1]=np.cross(n,ax_); Tb[:3,2]=n; Tb[:3,3]=(a3+b3)/2
slab=box(extents=[L,30,40],transform=Tb)
seg=trimesh.boolean.intersection([up,slab],engine='manifold')
upfill=trimesh.boolean.intersection([seg.convex_hull,slab],engine='manifold')
up=trimesh.boolean.union([up,upfill],engine='manifold')
up2=trimesh.boolean.difference([up,up_cut],engine='manifold')
up2.export(r"C:\Users\himme\Downloads\Alt_Kol_duct18.stl")
print("upper: vol",round(up.volume),"->",round(up2.volume),"watertight",up2.is_watertight)
# wall check: min distance from duct axis to original surface along the inner segment
from trimesh.proximity import closest_point
for t in np.linspace(0,1,9):
    p=P(*Q1)+(P(*Q2)-P(*Q1))*t
    _,dist,_=closest_point(up,[p]); print(f"  upper inner t={t:.2f} wall={dist[0]-9:.1f} mm")

# ---------- forearm (On_Kol / Arm B.stl): 10 mm duct, top by wrist -> +Y side by elbow ----------
# 2026-10-14: STRETCHED to FOREARM_PIVOT_MM. The original is 140.1 mm elbow hub -> wrist axle and
# cannot reach the floor past the front wheels (arm_ik.solve); Willie runs a 220 mm forearm. The
# part is cut through the plain middle of the tongue (x = CUT_X), the elbow end is moved out, and
# the gap is filled with that cross-section, so both ends are unchanged.
import math,os
from trimesh.creation import extrude_polygon
FOREARM_PIVOT_MM=float(os.environ.get("FOREARM_PIVOT_MM","220"))   # 265 for the new body (2026-10-15)
FOREARM_DUCT_MM=float(os.environ.get("FOREARM_DUCT_MM","10"))     # 14 for the new body (owner, 2026-10-16)
FR=FOREARM_DUCT_MM/2
WRIST_AXLE=np.array([12.4,0,12.5]); ELBOW_HUB=np.array([152.3,0,20.0])   # hole centres (y = hole axis)
CUT_X=60.0
fa0=trimesh.load(os.path.expanduser('~/Downloads/Arm B.stl'))
dz=ELBOW_HUB[2]-WRIST_AXLE[2]
S=math.sqrt(FOREARM_PIVOT_MM**2-dz**2)-(ELBOW_HUB[0]-WRIST_AXLE[0])
left=fa0.slice_plane([CUT_X,0,0],[-1,0,0],cap=True)
right=fa0.slice_plane([CUT_X,0,0],[1,0,0],cap=True); right.apply_translation([S,0,0])
sec=fa0.section(plane_origin=[CUT_X,0,0],plane_normal=[1,0,0])
TO3D=np.array([[0,0,1,CUT_X],[1,0,0,0],[0,1,0,0],[0,0,0,1]],float)   # 2D (y,z) + extrude along x
poly,_=sec.to_2D(to_2D=np.linalg.inv(TO3D))
bridge=trimesh.util.concatenate([extrude_polygon(pg,S) for pg in poly.polygons_full])
bridge.apply_transform(TO3D)
if bridge.volume<0: bridge.invert()
fa=trimesh.boolean.union([left,bridge,right],engine='manifold')
# fill the I-beam side recesses over the duct run so the walls are solid
clip=box(bounds=[[30,0,0],[95+S,56,40]])
seg=trimesh.boolean.intersection([fa,clip],engine='manifold')
fill=trimesh.boolean.intersection([seg.convex_hull,box(bounds=[[30,18.5,0],[95+S,37.5,40]])],engine='manifold')
fa_f=trimesh.boolean.union([fa,fill],engine='manifold')
# 2026-10-16 (owner): with a big duct (18 mm, like the upper arm) the 20 mm-wide forearm would keep 1 mm
# walls, so widen it to FOREARM_WIDE_MM from just behind the wrist joint to the elbow fork -- the arm's own
# section spread sideways (corner chamfers kept), hulled ring to ring so the rising top edge is followed.
# The wrist hub and the elbow fork are untouched, so both joints still fit.
FOREARM_WIDE_MM=float(os.environ.get("FOREARM_WIDE_MM","0"))      # 0 = original width
WIDE_X0,WIDE_X1=26.0,36.0            # taper from the arm's width (behind the wrist hub) to full width
WIDE_X3=225.0+S-125.0                # elbow end of the widening: where the fork already starts to widen
if FOREARM_WIDE_MM>0:
    YC=28.0
    def ring(x,w=None):
        v=fa_f.section(plane_origin=[x,0,0],plane_normal=[1,0,0]).vertices.copy()
        if w is not None:
            grow=max(0.0,(w-np.ptp(v[:,1]))/2)
            v[:,1]=np.where(v[:,1]<YC,v[:,1]-grow,v[:,1]+grow)
        return v
    xs=[WIDE_X0,WIDE_X1]+list(np.arange(WIDE_X1+20,WIDE_X3-10,20))+[WIDE_X3-10,WIDE_X3]
    rings=[ring(WIDE_X0)]+[ring(x,FOREARM_WIDE_MM) for x in xs[1:-1]]+[ring(xs[-1],FOREARM_WIDE_MM)]
    hulls=[trimesh.Trimesh(np.vstack([a,b])).convex_hull for a,b in zip(rings[:-1],rings[1:])]
    fa_f=trimesh.boolean.union([fa_f]+hulls,engine='manifold')
EXIT_DX=float(os.environ.get('FOREARM_EXIT_DX','12'))   # exit run along x from the straight to the side
EXIT_X=float(os.environ.get('FOREARM_EXIT_X','98'))   # 92 for the 18 mm duct: 98 breaks into the elbow servo's screw hole
fa_path=[np.array(p,float) for p in [(36,28,36),(56,28,14),(EXIT_X+S,28,14),(EXIT_X+EXIT_DX+S,64,14)]]
fa_cut=capsule_path(fa_path,FR)
fa2=trimesh.boolean.difference([fa_f,fa_cut],engine='manifold')
out=os.path.expanduser('~/Downloads/On_Kol_duct%g_%d.stl'%(FOREARM_DUCT_MM,round(FOREARM_PIVOT_MM)))
fa2.export(out)
hub=ELBOW_HUB+np.array([S,0,0])
print(f"fore: stretched {S:.1f} mm -> pivots {np.linalg.norm(hub-WRIST_AXLE):.1f} mm; length {fa2.extents[0]:.1f} mm; "
      f"vol {round(fa0.volume)} -> {round(fa2.volume)}; watertight {fa2.is_watertight}; wrote {out}")
for t in np.linspace(0,1,7):
    p=fa_path[1]+(fa_path[2]-fa_path[1])*t
    _,dist,_=closest_point(fa_f,[p]); print(f"  fore inner x={p[0]:.0f} wall={dist[0]-FR:.1f} mm")
seg2=np.array(fa_path[3])-np.array(fa_path[2])
for sc in ([116.9+S,53.2,13.2],[117.4+S,53.2,23.1]):
    p=np.array(sc); t=np.clip(np.dot(p-fa_path[2],seg2)/np.dot(seg2,seg2),0,1)
    print("  screw hole",np.round(sc,1),"clearance to duct edge",round(np.linalg.norm(p-(fa_path[2]+t*seg2))-FR-1.5,1),"mm")
