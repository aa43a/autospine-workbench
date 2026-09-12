"""Subtract triangle coverage from a unit texel; overlaps never count twice."""
import math


def area(poly):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1])))/2


def side(p,a,b):
    return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])


def clip(poly,a,b,positive):
    result=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        dp,dq=side(p,a,b),side(q,a,b)
        ip,iq=(dp>=0,dq>=0) if positive else (dp<=0,dq<=0)
        if ip:result.append(p)
        if ip!=iq:
            t=dp/(dp-dq)
            result.append([p[k]+t*(q[k]-p[k]) for k in (0,1)])
    return result


def covered(corners,triangles):
    """Require uncovered area <= 1e-9 texels, independent of canvas scale."""
    origin=corners[0];u=[corners[1][k]-origin[k] for k in (0,1)]
    v=[corners[3][k]-origin[k] for k in (0,1)];det=u[0]*v[1]-u[1]*v[0]
    if not math.isfinite(det) or abs(det)<1e-14:return False
    def local(p):
        x,y=p[0]-origin[0],p[1]-origin[1]
        return [(x*v[1]-y*v[0])/det,(u[0]*y-u[1]*x)/det]
    if math.dist(local(corners[2]),[1,1])>1e-8:return False
    remaining=[[[0,0],[1,0],[1,1],[0,1]]]
    for triangle in triangles:
        t=[local(p) for p in triangle]
        if not all(math.isfinite(x) for p in t for x in p):return False
        if max(p[0] for p in t)<0 or min(p[0] for p in t)>1 or max(p[1] for p in t)<0 or min(p[1] for p in t)>1:continue
        signed=side(t[2],t[0],t[1])
        if abs(signed)<1e-14:continue
        if signed<0:t.reverse()
        outside=[]
        for poly in remaining:
            inside=poly
            for a,b in zip(t,t[1:]+t[:1]):
                piece=clip(inside,a,b,False)
                if len(piece)>=3 and area(piece)>1e-14:outside.append(piece)
                inside=clip(inside,a,b,True)
                if len(inside)<3:break
        remaining=outside
        if not remaining:return True
    return sum(area(p) for p in remaining)<=1e-9
