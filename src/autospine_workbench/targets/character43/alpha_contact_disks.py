"""Conservative disks wholly inside supplied native-pixel alpha support."""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt


def disks(contact, points, maximum_distance):
    pixels=np.asarray(contact,float);points=np.asarray(points,float)
    if (pixels.ndim!=2 or pixels.shape[1]!=2 or not len(pixels) or points.ndim!=2 or points.shape[1]!=2
            or not np.isfinite(pixels).all() or not np.isfinite(points).all()
            or not np.isfinite(maximum_distance) or maximum_distance<=0
            or not np.allclose(pixels,np.round(pixels),atol=1e-8,rtol=0)):
        raise ValueError('alpha_contact_disk_input')
    lo=pixels.min(axis=0).astype(int)-2;hi=pixels.max(axis=0).astype(int)+2
    if np.prod(hi-lo+1)>4_194_304:raise ValueError('alpha_contact_disk_budget')
    mask=np.zeros(tuple(hi-lo+1),dtype=bool);indices=(pixels-lo).astype(int);mask[indices[:,0],indices[:,1]]=True
    # Subtract a pixel diagonal to stay inside the union of opaque pixel cells.
    distance=distance_transform_edt(mask)[indices[:,0],indices[:,1]]-math.sqrt(2)
    result=[]
    for p in points:
        d=np.linalg.norm(pixels-p,axis=1);eligible=np.where((d<=maximum_distance)&(distance>0))[0]
        if not len(eligible):raise ValueError('alpha_contact_disk_no_supported_interior')
        i=min(eligible,key=lambda j:(-distance[j],d[j],pixels[j,0],pixels[j,1]))
        result.append(dict(center=pixels[i].tolist(),radius=float(distance[i])))
    return result
