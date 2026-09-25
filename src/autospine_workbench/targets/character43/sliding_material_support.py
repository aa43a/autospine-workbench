"""Find nearby opaque material in the current covering triangle, allowing slip."""
import math
import numpy as np


def targets(points,vertices,weights,fixed,delta,*,budget=8.):
    free=[(v,w) for v,w in zip(vertices,weights,strict=True) if v not in fixed]
    total=sum(w for v,w in free)
    if total<=1e-8:raise ValueError('sliding_material_fixed_support')
    displacement=np.asarray(delta)/total
    if not np.isfinite(displacement).all() or np.linalg.norm(displacement)>budget:
        raise ValueError('sliding_material_displacement_budget')
    return {v:(np.asarray(points[v])+displacement).tolist() for v,w in free}


def nearest(mesh,points,texture,query,*,pixel_radius=8,max_distance=8.):
    if (type(pixel_radius) is not int or not 1<=pixel_radius<=16 or
            not math.isfinite(max_distance) or max_distance<=0):
        raise ValueError('sliding_material_search_budget')
    uv=np.asarray(mesh['uvs']).reshape(-1,2);candidates=[]
    for index,ids in enumerate(np.asarray(mesh['triangles']).reshape(-1,3)):
        a,b,c=np.asarray(points)[ids];matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:continue
        w=np.linalg.solve(matrix,np.asarray(query)-a);w=np.r_[1-w.sum(),w]
        if min(w)<-1e-8:continue
        tex=w@uv[ids];cx=int(tex[0]*texture.width);cy=int(tex[1]*texture.height)
        ua,ub,uc=uv[ids];basis=np.column_stack((ub-ua,uc-ua))
        if abs(np.linalg.det(basis))<1e-12:continue
        for y in range(max(1,cy-pixel_radius),min(texture.height-1,cy+pixel_radius+1)):
            for x in range(max(1,cx-pixel_radius),min(texture.width-1,cx+pixel_radius+1)):
                if min(texture.getpixel((x+dx,y+dy))[3] for dx in (-1,0,1) for dy in (-1,0,1))<128:continue
                material=np.asarray([(x+.5)/texture.width,(y+.5)/texture.height])
                weights=np.linalg.solve(basis,material-ua);weights=np.r_[1-weights.sum(),weights]
                if min(weights)<-1e-8:continue
                point=weights@np.asarray(points)[ids];distance=float(np.linalg.norm(point-query))
                if distance<=max_distance:
                    candidates.append(dict(triangle=index,vertices=ids.tolist(),weights=weights.tolist(),
                        world=point.tolist(),pixel=[x,y],distance_px=distance))
    return min(candidates,key=lambda r:(r['distance_px'],r['triangle'],r['pixel'])) if candidates else None
