"""Rigid 3D dual-quaternion comparison, scalar-first quaternion convention.

Approximate DQ blending (Kavan et al. 2008); not a no-fold or contact guarantee.
Exactly ambiguous half-turn blends are rejected, not silently assigned a branch.
"""
import numpy as np


def multiply(a,b):
    return np.r_[a[0]*b[0]-a[1:]@b[1:],a[0]*b[1:]+b[0]*a[1:]+np.cross(a[1:],b[1:])]


def deform(points,influences,quaternions,translations):
    p,q,t=(np.asarray(x,float) for x in (points,quaternions,translations))
    if (p.ndim!=2 or p.shape[1]!=3 or q.ndim!=2 or q.shape[1]!=4 or not len(q) or
            t.shape!=(len(q),3) or len(influences)!=len(p) or
            not all(np.isfinite(x).all() for x in (p,q,t)) or
            np.max(abs(np.linalg.norm(q,axis=1)-1))>1e-5):
        raise ValueError('dq_input')
    q=q/np.linalg.norm(q,axis=1)[:,None]
    dual=np.array([.5*multiply(np.r_[0.,v],r) for r,v in zip(q,t)])
    result=[]
    for point,row in zip(p,influences):
        if (not row or any(type(i) is not int or not 0<=i<len(q) or not np.isfinite(w) or w<=0
                           for i,w in row) or abs(sum(w for _,w in row)-1)>1e-6):
            raise ValueError('dq_weights')
        anchor=q[max(row,key=lambda x:x[1])[0]]; real=np.zeros(4); d=np.zeros(4)
        for i,w in row:
            dot=float(anchor@q[i])
            if abs(dot)<1e-8:raise ValueError('dq_half_turn_ambiguous')
            sign=1 if dot>0 else -1
            real+=sign*w*q[i];d+=sign*w*dual[i]
        length=np.linalg.norm(real)
        if length<1e-8:raise ValueError('dq_degenerate_blend')
        real/=length;d/=length;d-=real*(real@d)
        conjugate=real*np.array([1,-1,-1,-1])
        result.append((multiply(multiply(real,np.r_[0.,point]),conjugate)+
                       2*multiply(d,conjugate))[1:])
    return np.array(result)
