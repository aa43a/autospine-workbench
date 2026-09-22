"""C1 longitudinal material strip between two explicit affine bone frames."""
import math
import numpy as np


def map_points(points, center, axis, half_span, proximal, distal, *, follow_curve=False):
    p=np.asarray(points,float);center=np.asarray(center,float);axis=np.asarray(axis,float)
    if (p.ndim!=2 or p.shape[1]!=2 or center.shape!=(2,) or axis.shape!=(2,)
            or not np.isfinite(p).all() or not np.isfinite([*center,*axis,half_span]).all()
            or half_span<=0 or np.linalg.norm(axis)<=1e-10):raise ValueError('joint_strip_input')
    axis=axis/np.linalg.norm(axis);normal=np.array([-axis[1],axis[0]])
    frames=[]
    for m in (proximal,distal):
        if len(m)!=6 or not all(math.isfinite(v) for v in m):raise ValueError('joint_strip_frame')
        a,b,c,d,x,y=m;A=np.array([[a,b],[c,d]])
        if np.linalg.det(A)<=1e-10:raise ValueError('joint_strip_orientation')
        frames.append((A,np.array([x,y])))
    (A,x),(B,y)=frames; c0=A@(center-half_span*axis)+x;c1=B@(center+half_span*axis)+y
    tangent0=2*half_span*(A@axis);tangent1=2*half_span*(B@axis)
    n0,n1=A@normal,B@normal;w0,w1=np.linalg.norm(n0),np.linalg.norm(n1)
    angle0=math.atan2(n0[1],n0[0]);delta=(math.atan2(n1[1],n1[0])-angle0+math.pi)%(2*math.pi)-math.pi
    if abs(delta)>math.radians(170):raise ValueError('joint_strip_turn_ambiguous')
    def wrap(a):return (a+math.pi)%(2*math.pi)-math.pi
    offset0=wrap(angle0-math.atan2(tangent0[1],tangent0[0])-math.pi/2)
    offset1=wrap(angle0+delta-math.atan2(tangent1[1],tangent1[0])-math.pi/2)
    out=[]
    for point in p:
        s=float((point-center)@axis);v=float((point-center)@normal)
        if s<=-half_span:target=A@point+x
        elif s>=half_span:target=B@point+y
        else:
            u=(s+half_span)/(2*half_span);u2=u*u;u3=u2*u
            path=(2*u3-3*u2+1)*c0+(u3-2*u2+u)*tangent0+(-2*u3+3*u2)*c1+(u3-u2)*tangent1
            smooth=3*u2-2*u3;angle=angle0+delta*smooth;width=w0+(w1-w0)*smooth
            if follow_curve:
                # Quintic endpoint position/tangent interpolation with zero
                # endpoint curvature keeps material normals C1 at the joins.
                u4=u3*u;u5=u4*u
                path=(1-10*u3+15*u4-6*u5)*c0+(u-6*u3+8*u4-3*u5)*tangent0
                path+=(10*u3-15*u4+6*u5)*c1+(-4*u3+7*u4-3*u5)*tangent1
                derivative=(-30*u2+60*u3-30*u4)*c0+(1-18*u2+32*u3-15*u4)*tangent0
                derivative+=(30*u2-60*u3+30*u4)*c1+(-12*u2+28*u3-15*u4)*tangent1
                if np.linalg.norm(derivative)<=1e-10:raise ValueError('joint_strip_centerline_cusp')
                angle=math.atan2(derivative[1],derivative[0])+math.pi/2+offset0+wrap(offset1-offset0)*smooth
            target=path+v*width*np.array([math.cos(angle),math.sin(angle)])
        out.append(target.tolist())
    return out


def relative(rest,current):
    a,b,c,d,x,y=rest;u,v,w,z,tx,ty=current
    base=np.array([[a,b],[c,d]]);now=np.array([[u,v],[w,z]])
    if np.linalg.det(base)<=1e-10:raise ValueError('joint_strip_setup')
    matrix=now@np.linalg.inv(base);shift=np.array([tx,ty])-matrix@[x,y]
    return (*matrix.flatten(),*shift)


def jacobian_samples(points, center, axis, half_span, proximal, distal, *, follow_curve=False):
    """Two-step finite differences distinguish mapping folds from coarse triangles.

    This is a sampled diagnostic, not an interval proof of global injectivity.
    """
    rows=[]
    for point in points:
        determinants=[]
        for step in (half_span*1e-5,half_span*5e-6):
            x,y=point
            mapped=map_points([[x+step,y],[x-step,y],[x,y+step],[x,y-step]],
                center,axis,half_span,proximal,distal,follow_curve=follow_curve)
            dx=(np.array(mapped[0])-mapped[1])/(2*step)
            dy=(np.array(mapped[2])-mapped[3])/(2*step)
            determinants.append(float(dx[0]*dy[1]-dx[1]*dy[0]))
        rows.append(dict(determinants=determinants,negative_at_both_steps=max(determinants)<-1e-6))
    return rows
