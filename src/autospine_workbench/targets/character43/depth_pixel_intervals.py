"""Barycentric depth intervals at opaque native-pixel centres, not whole triangles."""
import numpy as np
from ..spine43.seam_raster import mask


def classify(mesh, positions, alpha, rect, common, intervals, margin, charge):
    x,y,w,h=rect
    points=np.asarray([(p[0],-p[1]) for p in positions])
    masks={k:np.zeros((h,w),dtype=bool) for k in ('front','back','ambiguous','unknown')}
    flat=mesh['triangles']
    for i in range(0,len(flat),3):
        indices=flat[i:i+3];a,b,c=points[indices]
        lo=np.maximum(np.floor(points[indices].min(axis=0)).astype(int),[x,y])
        hi=np.minimum(np.ceil(points[indices].max(axis=0)).astype(int),[x+w,y+h])
        if (hi<=lo).any():continue
        region=(slice(lo[1]-y,hi[1]-y),slice(lo[0]-x,hi[0]-x))
        if not common[region].any():continue
        box=[int(lo[0]),int(lo[1]),int(hi[0]-lo[0]),int(hi[1]-lo[1])]
        charge(2*box[2]*box[3])  # alpha raster plus interval evaluation
        opaque=(mask(dict(mesh,triangles=indices),positions,alpha,box)>=8)&common[region]
        if not opaque.any():continue
        values=[intervals[v] for v in indices]
        if any(v is None for v in values):
            masks['unknown'][region]|=opaque;continue
        det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(det)<1e-12:
            masks['unknown'][region]|=opaque;continue
        px,py=np.meshgrid(np.arange(lo[0],hi[0])+.5,np.arange(lo[1],hi[1])+.5)
        u=((b[1]-c[1])*(px-c[0])+(c[0]-b[0])*(py-c[1]))/det
        v=((c[1]-a[1])*(px-c[0])+(a[0]-c[0])*(py-c[1]))/det
        weights=np.maximum(np.stack([u,v,1-u-v]),0)
        weights/=weights.sum(axis=0)
        low=sum(weights[j]*values[j][0] for j in range(3))
        high=sum(weights[j]*values[j][1] for j in range(3))
        front=low>margin;back=high < -margin
        masks['front'][region]|=opaque&front
        masks['back'][region]|=opaque&back
        masks['ambiguous'][region]|=opaque&~(front|back)
    unknown=masks['unknown']|(common&~np.logical_or.reduce(list(masks.values())))
    ambiguous=(masks['ambiguous']|(masks['front']&masks['back']))&~unknown
    return {k:int(v.sum()) for k,v in dict(unknown=unknown,ambiguous=ambiguous,
        front=masks['front']&~unknown&~ambiguous,back=masks['back']&~unknown&~ambiguous).items()}
