"""Extract exact positive piecewise-linear depth regions on an existing mesh."""
import math


def extract(points, triangles, values):
    if len(points)!=len(values) or len(triangles)%3 or any(
            len(p)!=2 or any(not math.isfinite(x) for x in p) for p in points):
        raise ValueError('depth_contour_geometry_invalid')
    if any(v is None or not math.isfinite(v) for v in values):
        raise ValueError('depth_contour_unknown_vertex')
    if any(type(i) is not int or not 0<=i<len(points) for i in triangles):
        raise ValueError('depth_contour_indices_invalid')
    nodes={};edges={}
    def vertex(i):
        key=('v',i);nodes[key]=list(points[i]);return key
    def crossing(a,b):
        if values[a]==0:return vertex(a)
        if values[b]==0:return vertex(b)
        a,b=sorted((a,b));key=('e',a,b)
        t=values[a]/(values[a]-values[b])
        nodes[key]=[points[a][j]+t*(points[b][j]-points[a][j]) for j in (0,1)]
        return key
    for offset in range(0,len(triangles),3):
        tri=triangles[offset:offset+3];poly=[]
        for a,b in zip(tri,tri[1:]+tri[:1]):
            if values[a]>0:poly.append(vertex(a))
            if (values[a]>0)!=(values[b]>0):poly.append(crossing(a,b))
        poly=[p for i,p in enumerate(poly) if p!=poly[i-1]]
        if len(poly)<3:continue
        for a,b in zip(poly,poly[1:]+poly[:1]):
            if (b,a) in edges:del edges[b,a]
            elif (a,b) in edges:raise ValueError('depth_contour_duplicate_directed_edge')
            else:edges[a,b]=True
    following={};incoming={}
    for a,b in edges:
        if a in following or b in incoming:raise ValueError('depth_contour_branching_boundary')
        following[a]=b;incoming[b]=a
    if set(following)!=set(incoming):raise ValueError('depth_contour_open_boundary')
    loops=[]
    while following:
        start=min(following);key=start;loop=[]
        while True:
            loop.append(key);key=following.pop(key)
            if key==start:break
        polygon=[nodes[k] for k in loop]
        area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1]))/2
        if abs(area)>1e-10:loops.append(dict(points=polygon,signed_area=area,vertex_keys=[list(k) for k in loop]))
    return dict(loops=loops,scope='piecewise_linear_depth_proxy_not_observed_surface',authority='none',selected=False)
