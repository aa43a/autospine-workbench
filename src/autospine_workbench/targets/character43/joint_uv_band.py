"""Bounded source-UV experiment; no authority or default rig mutation."""
import numpy as np


def contract(uvs, triangles, size, pivot, axis, radius, *, strength=.4, limit=16.):
    size=np.asarray(size,float)
    if size.shape!=(2,) or not np.isfinite(size).all() or np.any(size<=0):
        raise ValueError('joint_uv_band_input')
    points=np.asarray(uvs,float).reshape(-1,2)*size
    pivot=np.asarray(pivot,float);axis=np.asarray(axis,float)
    triangles=np.asarray(triangles,int).reshape(-1,3)
    if (pivot.shape!=(2,) or axis.shape!=(2,) or not len(points) or not len(triangles) or
            triangles.min()<0 or triangles.max()>=len(points) or
            not all(np.isfinite(v).all() for v in (points,pivot,axis,[radius,strength,limit])) or
            not 0<strength<1 or not 0<limit<=32 or radius<=0 or np.linalg.norm(axis)<1e-8):
        raise ValueError('joint_uv_band_input')
    axis=axis/np.linalg.norm(axis);normal=np.array([-axis[1],axis[0]])
    delta=points-pivot;along=delta@axis;across=delta@normal
    envelope=np.maximum(0,1-(along/radius)**2)**2
    shift=np.clip(-across*strength*envelope,-limit,limit)
    changed=points+shift[:,None]*normal
    def winding(p):
        t=p[triangles];a=t[:,1]-t[:,0];b=t[:,2]-t[:,0]
        return a[:,0]*b[:,1]-a[:,1]*b[:,0]
    before,after=winding(points),winding(changed)
    if np.any(before*after<=0):raise ValueError('joint_uv_band_orientation')
    if np.any(changed<0) or np.any(changed>np.asarray(size)):
        raise ValueError('joint_uv_band_bounds')
    return (changed/np.asarray(size)).ravel().tolist(),dict(
        radius=radius,strength=strength,limit_px=limit,maximum_displacement_px=float(abs(shift).max()),
        moved_vertices=int(np.count_nonzero(abs(shift)>1e-8)),
        minimum_uv_area_ratio=float(np.min(after/before)),
        scope='static_pose_material_probe_not_setup_preserving_animation',selected=False)
