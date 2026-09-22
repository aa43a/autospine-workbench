"""Experimental cylindrical front surface; source depth is evidence, radius is a hypothesis."""
import math
import numpy as np


def rotation(a, b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    if a.shape!=(3,) or b.shape!=(3,) or not np.isfinite([a,b]).all() or min(np.linalg.norm(a),np.linalg.norm(b))<1e-10:
        raise ValueError('surface_proxy_axis')
    a=a/np.linalg.norm(a);b=b/np.linalg.norm(b);c=float(a@b)
    if c < -1+1e-8:raise ValueError('surface_proxy_half_turn_ambiguous')
    v=np.cross(a,b);x,y,z=v;K=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    return np.eye(3)+K+K@K/(1+c)


def point(u,v,rest,current,source_vector,radius,front_sign):
    if (len(rest)!=6 or len(current)!=6 or len(source_vector)!=3 or
        not all(math.isfinite(x) for x in [u,v,*rest,*current,*source_vector,radius]) or radius<=0 or front_sign not in (-1,1)):
        raise ValueError('surface_proxy_input')
    ra,rb,rc,rd,_,_=rest;a,b,c,d,x,y=current
    rest_length=math.hypot(ra,rc);current_length=math.hypot(a,c)
    source_length=math.hypot(*source_vector);visible=math.hypot(*source_vector[:2])
    if min(rest_length,current_length,source_length,visible)<1e-8:raise ValueError('surface_proxy_unobservable_axis')
    axis=np.array([ra,rc,0.])/rest_length;normal=np.array([-axis[1],axis[0],0.])
    transverse=(ra*rd-rb*rc)/rest_length
    if transverse<=0:raise ValueError('surface_proxy_reflected_setup')
    target=np.array([a/current_length*visible,c/current_length*visible,source_vector[2]])/source_length
    R=rotation(axis,target)
    width=v*transverse;depth=front_sign*math.sqrt(max(0.,radius*radius-width*width))
    # Preserve current axis/endpoint mapping, replace its cross section only.
    axial=u+(ra*rb+rc*rd)/(rest_length*rest_length)*v
    cross=R@(normal*width+np.array([0.,0.,depth]))
    return [float(x+a*axial+cross[0]),float(y+c*axial+cross[1])]
