"""Conservative reachability of bilinear alpha support under bounded vertex motion.

Texture/UV/topology stay fixed. A material point moves by a convex combination of
its triangle's vertex offsets, hence by no more than their common budget. Alpha
cells with any corner above threshold over-approximate all possible support.
This bounds per-triangle alpha, not framebuffer compositing or cloth semantics.
"""
import math
import numpy as np


def clip(poly,axis,bound,keep_greater):
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        ina=a[axis]>=bound if keep_greater else a[axis]<=bound
        inb=b[axis]>=bound if keep_greater else b[axis]<=bound
        if ina:result.append(a)
        if ina!=inb:
            t=(bound-a[axis])/(b[axis]-a[axis]);result.append(a+t*(b-a))
    return result


def nearest(poly,query):
    edges=list(zip(poly,poly[1:]+poly[:1]))
    cross=[(b[0]-a[0])*(query[1]-a[1])-(b[1]-a[1])*(query[0]-a[0]) for a,b in edges]
    area=sum(a[0]*b[1]-a[1]*b[0] for a,b in edges)
    if len(poly)>=3 and abs(area)>1e-12 and (min(cross)>=0 or max(cross)<=0):return query
    options=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        d=b-a;den=float(d@d);t=0 if den<=1e-20 else float(np.clip((query-a)@d/den,0,1))
        options.append(a+t*d)
    return min(options,key=lambda p:float(np.linalg.norm(p-query)))


def alpha_at(alpha,p):
    h,w=alpha.shape;x,y=p;ix,iy=math.floor(x),math.floor(y);fx,fy=x-ix,y-iy
    return sum(weight*alpha[min(h-1,max(0,iy+dy)),min(w-1,max(0,ix+dx))]
               for dx,dy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)))


def inspect(mesh,points,alpha,query,*,budget=8.,threshold=8.,cell_limit=100000):
    points=np.asarray(points,float);uv=np.asarray(mesh['uvs'],float).reshape(-1,2)
    alpha=np.asarray(alpha,float);query=np.asarray(query,float)
    if (not math.isfinite(budget) or budget<=0 or not math.isfinite(threshold) or not 0<threshold<=255 or
        points.shape!=uv.shape or query.shape!=(2,) or alpha.ndim!=2 or min(alpha.shape)<1 or
        not all(np.isfinite(v).all() for v in (points,uv,alpha,query)) or
        np.any((uv<0)|(uv>1)) or np.any((alpha<0)|(alpha>255))):
        raise ValueError('material_reachability_input')
    h,w=alpha.shape;tex=uv*[w,h]-.5;search=budget*2
    closest=search;witness=None;visited=0;potential=0;unknown=[]
    for index,ids in enumerate(np.asarray(mesh['triangles']).reshape(-1,3)):
        world=points[ids];distance=np.maximum(np.maximum(world.min(0)-query,query-world.max(0)),0)
        if np.linalg.norm(distance)>search:continue
        a,b,c=world;basis=np.column_stack((b-a,c-a));ta,tb,tc=tex[ids];tbasis=np.column_stack((tb-ta,tc-ta))
        if abs(np.linalg.det(basis))<1e-12 or abs(np.linalg.det(tbasis))<1e-12:
            unknown.append(index);continue
        to_tex=tbasis@np.linalg.inv(basis);to_world=basis@np.linalg.inv(tbasis)
        corners=np.asarray([ta+to_tex@(query+[dx,dy]-a) for dx in (-search,search) for dy in (-search,search)])
        lo=np.maximum(np.maximum(corners.min(0),tex[ids].min(0)),[-1,-1])
        hi=np.minimum(np.minimum(corners.max(0),tex[ids].max(0)),[w-1,h-1])
        if np.any(hi<lo):continue
        for y in range(math.floor(lo[1]),math.floor(hi[1])+1):
            for x in range(math.floor(lo[0]),math.floor(hi[0])+1):
                visited+=1
                if visited>cell_limit:raise ValueError('material_reachability_cell_budget')
                if max(alpha[min(h-1,max(0,y+dy)),min(w-1,max(0,x+dx))] for dx in (0,1) for dy in (0,1))<threshold:continue
                poly=list(tex[ids])
                for axis,bound,greater in ((0,x,True),(0,x+1,False),(1,y,True),(1,y+1,False)):
                    poly=clip(poly,axis,bound,greater)
                    if not poly:break
                if not poly:continue
                potential+=1;wp=[a+to_world@(p-ta) for p in poly];near=nearest(wp,query)
                distance=float(np.linalg.norm(near-query));closest=min(closest,distance)
                # An actual alpha witness proves only single-point material reachability,
                # not joint geometry feasibility. Over-approximation alone proves neither.
                tnear=ta+to_tex@(near-a)
                for test in [tnear,*poly]:
                    if alpha_at(alpha,test)<threshold:continue
                    high=test.copy();low=tnear.copy()
                    if alpha_at(alpha,low)<threshold:
                        for _ in range(30):
                            mid=(low+high)/2
                            if alpha_at(alpha,mid)>=threshold:high=mid
                            else:low=mid
                    else:high=low
                    point=a+to_world@(high-ta);dist=float(np.linalg.norm(point-query))
                    if witness is None or dist<witness['distance_px']:
                        weights=np.linalg.solve(tbasis,high-ta);weights=np.r_[1-weights.sum(),weights]
                        witness=dict(triangle=index,vertices=ids.tolist(),weights=weights.tolist(),
                            texture_point=high.tolist(),world=point.tolist(),alpha=float(alpha_at(alpha,high)),distance_px=dist)
    status=('unmeasured_degenerate_triangles' if unknown else 'outside_vertex_budget'
            if closest>budget+1e-7 else 'material_witness_within_budget'
            if witness and witness['distance_px']<=budget else 'not_ruled_out')
    return dict(status=status,conservative_distance_lower_bound_px=None if unknown else closest,
        witness=witness,degenerate_triangles=unknown,visited_cells=visited,potential_cells=potential,
        budget_px=budget,threshold=threshold,search_radius_px=search,authority='none',selected=False,
        assumptions=['fixed_texture_uv_topology','each_vertex_offset_at_most_budget',
                     'bilinear_clamp_alpha','maximum_triangle_alpha_not_framebuffer_composite'])
