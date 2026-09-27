"""Batched per-triangle maximum bilinear alpha; not framebuffer compositing."""
import numpy as np


def sample(mesh, points, alpha, queries):
    ids=np.asarray(mesh['triangles'],dtype=int).reshape(-1,3)
    vertices=np.asarray(points,float)[ids]; uv=np.asarray(mesh['uvs']).reshape(-1,2)[ids]
    q=np.asarray(queries,float).reshape(-1,2)
    if not len(q):return []
    if not len(ids):return [0.]*len(q)
    a=vertices[:,0]; b=vertices[:,1]-a; c=vertices[:,2]-a
    determinant=b[:,0]*c[:,1]-b[:,1]*c[:,0]
    valid=np.abs(determinant)>=1e-12
    divisor=np.where(valid,determinant,1.)
    offset=q[:,None,:]-a
    v=(offset[:,:,0]*c[:,1]-offset[:,:,1]*c[:,0])/divisor
    w=(b[:,0]*offset[:,:,1]-b[:,1]*offset[:,:,0])/divisor
    weights=np.stack((1-v-w,v,w),axis=-1)
    inside=valid & (weights.min(axis=-1)>=-1e-8)
    tex=np.einsum('qti,tij->qtj',weights,uv)
    height,width=alpha.shape
    x=tex[:,:,0]*width-.5; y=tex[:,:,1]*height-.5
    ix=np.floor(x).astype(int); iy=np.floor(y).astype(int); fx=x-ix; fy=y-iy
    values=np.zeros_like(x)
    for dx,dy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
        values+=weight*alpha[np.clip(iy+dy,0,height-1),np.clip(ix+dx,0,width-1)]
    return np.where(inside,values,0).max(axis=1).tolist()
