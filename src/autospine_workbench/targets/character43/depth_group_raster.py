"""Crop classification masks to conservative triangle and opaque-common bounds."""
import math
import numpy as np
from ..spine43.seam_raster import mask


def raster(attachment, points, texture, rect, common, charge):
    output=np.zeros_like(common,dtype=bool)
    indices=attachment['triangles']
    if not indices or not common.any():return output
    if len(indices)%3 or any(type(i) is not int or not 0<=i<len(points) for i in indices):
        raise ValueError('depth_overlap_triangle_indices_invalid')
    x,y,w,h=rect
    if common.shape != (h,w):raise ValueError('depth_group_common_shape')
    rows,cols=np.nonzero(common)
    vertices=[points[i] for i in indices]
    left=max(x+int(cols.min()),math.floor(min(p[0] for p in vertices)))
    right=min(x+int(cols.max())+1,math.ceil(max(p[0] for p in vertices)))
    top=max(y+int(rows.min()),math.floor(min(-p[1] for p in vertices)))
    bottom=min(y+int(rows.max())+1,math.ceil(max(-p[1] for p in vertices)))
    if right<=left or bottom<=top:return output
    charge((right-left)*(bottom-top))
    output[top-y:bottom-y,left-x:right-x]=mask(
        attachment,points,texture,[left,top,right-left,bottom-top])>=8
    return output
