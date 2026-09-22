"""Clip material triangles into disjoint bands with interpolated texture UVs."""
import math


def partition(points, uvs, triangles, center, axis, cuts):
    if (not points or len(points)!=len(uvs) or len(center)!=2 or len(axis)!=2
            or any(len(p)!=2 for p in [*points,*uvs])
            or any(not math.isfinite(v) for p in [*points,*uvs,center,axis,cuts] for v in p)
            or not cuts or any(b<=a for a,b in zip(cuts,cuts[1:]))):
        raise ValueError('material_band_input')
    length=math.hypot(*axis)
    if length<=1e-10:raise ValueError('material_band_axis')
    axis=[v/length for v in axis]
    source=[[*p,*uv,sum((p[k]-center[k])*axis[k] for k in (0,1))] for p,uv in zip(points,uvs)]
    bounds=[None,*cuts,None];parts=[]
    def clip(poly,bound,greater):
        if bound is None or not poly:return poly
        result=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            inside_a=a[4]>=bound if greater else a[4]<=bound
            inside_b=b[4]>=bound if greater else b[4]<=bound
            if inside_a:result.append(a)
            if inside_a!=inside_b:
                t=(bound-a[4])/(b[4]-a[4]);result.append([x+t*(y-x) for x,y in zip(a,b)])
        return result
    for low,high in zip(bounds,bounds[1:]):
        output=dict(points=[],uvs=[],triangles=[],source_triangles=[])
        for index,triangle in enumerate(triangles):
            if len(triangle)!=3 or any(type(i) is not int or not 0<=i<len(points) for i in triangle):
                raise ValueError('material_band_triangles')
            polygon=clip(clip([source[i] for i in triangle],low,True),high,False)
            for i in range(1,len(polygon)-1):
                a,b,c=polygon[0],polygon[i],polygon[i+1]
                area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                if abs(area)<=1e-10:continue
                start=len(output['points'])
                for p in (a,b,c):
                    output['points'].append([float(v) for v in p[:2]])
                    output['uvs'].append([float(v) for v in p[2:4]])
                output['triangles'].append([start,start+1,start+2]);output['source_triangles'].append(index)
        parts.append(output)
    return parts
