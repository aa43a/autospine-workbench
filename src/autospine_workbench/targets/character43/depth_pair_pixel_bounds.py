"""Barycentric interval bounds on one triangle's native pixel centres."""
import numpy as np


def bounds(vertices,values,rect):
    a,b,c=np.asarray([(p[0],-p[1]) for p in vertices]);x,y,w,h=rect
    det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(det)<1e-12:return None
    px,py=np.meshgrid(np.arange(x,x+w)+.5,np.arange(y,y+h)+.5)
    u=((b[1]-c[1])*(px-c[0])+(c[0]-b[0])*(py-c[1]))/det
    v=((c[1]-a[1])*(px-c[0])+(a[0]-c[0])*(py-c[1]))/det
    weights=np.maximum(np.stack([u,v,1-u-v]),0)
    weights/=weights.sum(axis=0)
    return tuple(sum(weights[j]*values[j][bound] for j in range(3)) for bound in (0,1))
