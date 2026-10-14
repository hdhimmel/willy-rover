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
fa=trimesh.load(r"C:\Users\himme\Downloads\Arm B.stl")
# fill the I-beam side recesses over the duct run so the walls are solid
clip=box(bounds=[[30,0,0],[95,56,40]])
seg=trimesh.boolean.intersection([fa,clip],engine='manifold')
fill=trimesh.boolean.intersection([seg.convex_hull,box(bounds=[[30,18.5,0],[95,37.5,40]])],engine='manifold')
fa_f=trimesh.boolean.union([fa,fill],engine='manifold')
fa_path=[np.array(p,float) for p in [(36,28,36),(56,28,14),(98,28,14),(110,64,14)]]
fa_cut=capsule_path(fa_path,5.0)
fa2=trimesh.boolean.difference([fa_f,fa_cut],engine='manifold')
fa2.export(r"C:\Users\himme\Downloads\On_Kol_duct10.stl")
print("fore: vol",round(fa.volume),"->",round(fa2.volume),"(fill +",round(fa_f.volume-fa.volume),") watertight",fa2.is_watertight)
for t in np.linspace(0,1,7):
    p=fa_path[1]+(fa_path[2]-fa_path[1])*t
    _,dist,_=closest_point(fa_f,[p]); print(f"  fore inner x={p[0]:.0f} wall={dist[0]-5:.1f} mm")
_,dist,_=closest_point(fa,[[117,50,12.5],[117,50,22.5]])
seg2=np.array(fa_path[3])-np.array(fa_path[2])
for sc in ([116.9,53.2,13.2],[117.4,53.2,23.1]):
    p=np.array(sc); t=np.clip(np.dot(p-fa_path[2],seg2)/np.dot(seg2,seg2),0,1)
    print("  screw hole",sc,"clearance to duct edge",round(np.linalg.norm(p-(fa_path[2]+t*seg2))-5-1.5,1),"mm")
