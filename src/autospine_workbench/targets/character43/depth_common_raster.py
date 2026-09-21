"""Native alpha queries restricted to already measured common pixel centres."""
import numpy as np


def raster(attachment, vertices, alpha, rect, common, charge):
    x,y,w,h=rect
    if common.shape!=(h,w):raise ValueError('depth_group_common_shape')
    flat=attachment['triangles'];points=np.asarray([(p[0],-p[1]) for p in vertices])
    if len(flat)%3 or any(type(i) is not int or not 0<=i<len(points) for i in flat):
        raise ValueError('depth_overlap_triangle_indices_invalid')
    result=np.zeros_like(common,dtype=bool)
    if not flat or not common.any():return result
    rows,cols=np.nonzero(common);px=cols+x+.5;py=rows+y+.5
    bounds=points[flat];lo=np.floor(bounds.min(axis=0));hi=np.ceil(bounds.max(axis=0))
    selected=(px>=lo[0])&(px<hi[0])&(py>=lo[1])&(py<hi[1])
    rows,cols,px,py=rows[selected],cols[selected],px[selected],py[selected]
    if not len(rows):return result
    charge(len(rows))
    values=np.zeros(len(rows));uvs=np.asarray(attachment['uvs']).reshape(-1,2)
    th,tw=alpha.shape
    for offset in range(0,len(flat),3):
        indices=flat[offset:offset+3];a,b,c=points[indices]
        det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(det)<1e-12:continue
        lo=np.floor(points[indices].min(axis=0));hi=np.ceil(points[indices].max(axis=0))
        selected=np.flatnonzero((px>=lo[0])&(px<hi[0])&(py>=lo[1])&(py<hi[1]))
        if not len(selected):continue
        sx,sy=px[selected],py[selected]
        u=((b[1]-c[1])*(sx-c[0])+(c[0]-b[0])*(sy-c[1]))/det
        v=((c[1]-a[1])*(sx-c[0])+(a[0]-c[0])*(sy-c[1]))/det;t=1-u-v
        inside=(u>=-1e-9)&(v>=-1e-9)&(t>=-1e-9)
        uv=u[:,None]*uvs[indices[0]]+v[:,None]*uvs[indices[1]]+t[:,None]*uvs[indices[2]]
        tx=uv[:,0]*tw-.5;ty=uv[:,1]*th-.5;ix=np.floor(tx).astype(int);iy=np.floor(ty).astype(int)
        sampled=np.zeros_like(tx)
        for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
            xx,yy=ix+dx,iy+dy;valid=(xx>=0)&(xx<tw)&(yy>=0)&(yy<th)
            weight=(tx-ix if dx else 1-tx+ix)*(ty-iy if dy else 1-ty+iy)
            sampled+=np.where(valid,alpha[np.clip(yy,0,th-1),np.clip(xx,0,tw-1)]*weight,0)
        values[selected]=np.maximum(values[selected],np.where(inside,sampled,0))
    result[rows,cols]=values>=8
    return result
