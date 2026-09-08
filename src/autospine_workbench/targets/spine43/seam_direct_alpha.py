"""Direct world point -> deformed triangle -> UV -> bilinear texture alpha."""
import numpy as np


def sample(attachment, vertices, alpha, points):
    points=np.asarray(points,dtype=float); vertices=np.asarray(vertices,dtype=float)
    alpha=np.asarray(alpha,dtype=float)
    if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all():
        raise ValueError('direct_alpha_points')
    if not np.isfinite(vertices).all() or not np.isfinite(alpha).all(): raise ValueError('direct_alpha_nonfinite')
    result=np.zeros(len(points)); covered=np.zeros(len(points),dtype=bool)
    uv=np.asarray(attachment['uvs']).reshape(-1,2);flat=attachment['triangles'];h,w=alpha.shape
    for offset in range(0,len(flat),3):
        indices=flat[offset:offset+3];a,b,c=vertices[indices]
        det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(det)<1e-12: continue
        u=((b[1]-c[1])*(points[:,0]-c[0])+(c[0]-b[0])*(points[:,1]-c[1]))/det
        v=((c[1]-a[1])*(points[:,0]-c[0])+(a[0]-c[0])*(points[:,1]-c[1]))/det;t=1-u-v
        inside=(u>=-1e-9)&(v>=-1e-9)&(t>=-1e-9);covered|=inside
        tex=u[:,None]*uv[indices[0]]+v[:,None]*uv[indices[1]]+t[:,None]*uv[indices[2]]
        x=tex[:,0]*w-.5;y=tex[:,1]*h-.5;ix=np.floor(x).astype(int);iy=np.floor(y).astype(int)
        values=np.zeros(len(points))
        for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
            xx,yy=ix+dx,iy+dy;valid=(xx>=0)&(xx<w)&(yy>=0)&(yy<h)
            weight=(x-ix if dx else 1-x+ix)*(y-iy if dy else 1-y+iy)
            values+=np.where(valid,alpha[np.clip(yy,0,h-1),np.clip(xx,0,w-1)]*weight,0)
        np.maximum(result,np.where(inside,values,0),out=result)
    return result,covered


def patch(point, attachments, poses, textures, resolution):
    if resolution not in (8,16): raise ValueError('direct_alpha_resolution')
    offsets=(np.arange(resolution)+.5)/resolution-.5
    points=[[point[0]+x,point[1]-y] for y in offsets for x in offsets]
    values=[sample(a,p,t,points)[0] for a,p,t in zip(attachments,poses,textures)]
    union=255*(1-(1-values[0]/255)*(1-values[1]/255))
    return dict(resolution=resolution,sample_count=len(points),
                both_below8=int(((values[0]<8)&(values[1]<8)).sum()),
                union_below8=int((union<8).sum()),mean_union_alpha=float(union.mean()),
                min_union_alpha=float(union.min()),max_union_alpha=float(union.max())),union.reshape(resolution,resolution)
