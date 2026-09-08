"""Joint-specific deformation probes and raster support for partition meshes."""
import math
from .mesh_weights import _rotate, _deform, _area


def evaluate(vertices,triangles,weights,bones):
    if not 3<=len(vertices)<=4096 or len(weights)!=len(vertices) or not 1<=len(triangles)<=8192:
        raise ValueError('partition_mesh_shape_invalid')
    allowed={b['id'] for b in bones}
    if any(not row or len(row)>3 or len({i['bone_id'] for i in row})!=len(row) or
           any(i['bone_id'] not in allowed or not math.isfinite(i['weight']) or not 0<=i['weight']<=1 for i in row) for row in weights):
        raise ValueError('partition_mesh_influence_invalid')
    sums=max(abs(sum(i['weight'] for i in row)-1) for row in weights)
    setup={b['id']:(b['head_xy'],b['world_rotation_degrees']) for b in bones}
    restored=_deform(weights,setup)
    error=max(math.dist(a,b) for a,b in zip(vertices,restored))
    areas=[_area(vertices,t) for t in triangles]
    if any(abs(a)<1e-9 for a in areas):raise ValueError('partition_mesh_degenerate')
    edges=sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    lengths=[math.dist(vertices[a],vertices[b]) for a,b in edges]
    probes=[]
    for joint in range(len(bones)):
        for angle in (-90,-60,-30,-15,0,15,30,60,90):
            pivot=bones[joint]['head_xy'];frames={}
            for index,bone in enumerate(bones):
                head,rotation=setup[bone['id']]
                if index>=joint:
                    delta=_rotate([head[k]-pivot[k] for k in (0,1)],angle)
                    head=[pivot[k]+delta[k] for k in (0,1)];rotation+=angle
                frames[bone['id']]=(head,rotation)
            moved=_deform(weights,frames)
            ratios=[_area(moved,t)/a for t,a in zip(triangles,areas)]
            stretch=max(math.dist(moved[a],moved[b])/length for (a,b),length in zip(edges,lengths))
            probes.append({'id':bones[joint]['id']+f'_{angle:+d}','inversions':sum(r<=0 for r in ratios),
                           'min_area_ratio':min(ratios),'max_area_ratio':max(ratios),'max_edge_stretch':stretch})
    passed=error<=1e-7 and sums<=1e-9 and all(p['inversions']==0 and p['min_area_ratio']>=.5 and
               p['max_area_ratio']<=2 and p['max_edge_stretch']<=2 for p in probes)
    return {'passed':passed,'setup_max_error':error,'weight_sum_max_error':sums,'probes':probes}


def raster_support(alpha,width,height,vertices,triangles,offset):
    points=[[v[k]-offset[k] for k in (0,1)] for v in vertices];covered=bytearray(width*height)
    for triangle in triangles:
        a,b,c=[points[i] for i in triangle]
        area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        for y in range(max(0,math.floor(min(a[1],b[1],c[1]))),min(height,math.ceil(max(a[1],b[1],c[1])))):
            for x in range(max(0,math.floor(min(a[0],b[0],c[0]))),min(width,math.ceil(max(a[0],b[0],c[0])))):
                px,py=x+.5,y+.5
                u=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area
                v=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area
                if u>=-1e-9 and v>=-1e-9 and u+v<=1+1e-9:covered[y*width+x]=1
    missing=[a for a,c in zip(alpha,covered) if a and not c]
    return {'uncovered_alpha_pixels':len(missing),'uncovered_alpha_sum':sum(missing)}
