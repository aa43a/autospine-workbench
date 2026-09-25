"""Exact signed-area extrema only for linearly moving world-space vertices."""
import math


def signed_area(points):
    a,b,c=points
    return .5*((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))


def extrema(setup,start,end):
    for points in (setup,start,end):
        if len(points)!=3 or any(len(p)!=2 or any(not math.isfinite(x) for x in p) for p in points):
            raise ValueError('linear_triangle_interval_points')
    reference=signed_area(setup)
    if abs(reference)<1e-10:raise ValueError('linear_triangle_interval_degenerate')
    at0=signed_area(start)/reference;at1=signed_area(end)/reference
    middle=[[(a+b)/2 for a,b in zip(p,q)] for p,q in zip(start,end)]
    half=signed_area(middle)/reference
    quadratic=2*(at1+at0-2*half);linear=at1-at0-quadratic
    times=[0.,1.]
    if abs(quadratic)>1e-14:
        stationary=-linear/(2*quadratic)
        if 0<stationary<1:times.append(stationary)
    values=[dict(u=t,area_ratio=at0+linear*t+quadratic*t*t) for t in sorted(times)]
    return dict(scope='linear_world_vertices_only',coefficients=[at0,linear,quadratic],
                minimum=min(values,key=lambda x:x['area_ratio']),
                maximum=max(values,key=lambda x:x['area_ratio']))
