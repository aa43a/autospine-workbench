"""Experimental positive-stretch rotation blend about a shared material pivot.

Positive per-vertex frames do not guarantee a nonfolding mesh: spatially varying
weights and joint centers still require independent triangle/edge validation.
"""
import math
import numpy as np
from .transverse_frame import without_inherited_shear


def blend(point, pivot, transforms, weights):
    point, pivot = np.asarray(point, float), np.asarray(pivot, float)
    weights = np.asarray(weights, float)
    if (point.shape != (2,) or pivot.shape != (2,) or weights.shape != (len(transforms),)
            or not len(weights) or not np.isfinite([*point,*pivot,*weights]).all()
            or np.any(weights < 0) or abs(weights.sum()-1) > 1e-6):
        raise ValueError('pivot_blend_input')
    rotation = np.zeros(2); stretch = np.zeros((2,2)); center = np.zeros(2)
    for transform, weight in zip(transforms, weights, strict=True):
        if len(transform) != 6 or not all(math.isfinite(v) for v in transform):
            raise ValueError('pivot_blend_transform')
        a,b,c,d,x,y = transform; matrix = np.array([[a,b],[c,d]])
        if np.linalg.det(matrix) <= 1e-10: raise ValueError('pivot_blend_orientation')
        u, singular, vt = np.linalg.svd(matrix)
        r = u @ vt
        rotation += weight*r[:,0]
        stretch += weight*(vt.T @ np.diag(singular) @ vt)
        center += weight*(matrix @ pivot + [x,y])
    norm = np.linalg.norm(rotation)
    if norm < .2: raise ValueError('pivot_blend_rotation_ambiguous')
    cosine, sine = rotation/norm
    return (center + np.array([[cosine,-sine],[sine,cosine]]) @ stretch @ (point-pivot)).tolist()


def weighted_points(attachment, bones, rest, current, selected):
    frames = {}; origins = {}
    for bone in bones:
        name = bone['name']; m = current[name]
        if name in selected: m,_ = without_inherited_shear(rest[name],m)
        a,b,c,d,x,y = m; ra,rb,rc,rd,rx,ry = rest[name]
        base = np.array([[ra,rb],[rc,rd]])
        if np.linalg.det(base) <= 1e-10: raise ValueError('pivot_blend_setup')
        linear = np.array([[a,b],[c,d]]) @ np.linalg.inv(base)
        shift = np.array([x,y])-linear @ [rx,ry]
        frames[name] = (*linear.flatten(),*shift)
        origins[name] = (base,np.array([rx,ry]))
    data=attachment['vertices']; cursor=0; result=[]
    while cursor < len(data):
        count=data[cursor]; cursor+=1
        if type(count) is not int or count < 1 or cursor+4*count > len(data):
            raise ValueError('pivot_blend_weights')
        points=[]; transforms=[]; weights=[]; names=[]
        for _ in range(count):
            index,x,y,weight=data[cursor:cursor+4]; cursor+=4
            if type(index) is not int or not 0 <= index < len(bones):raise ValueError('pivot_blend_weights')
            name=bones[index]['name']; base,origin=origins[name]
            points.append(base @ [x,y]+origin); transforms.append(frames[name]); weights.append(weight)
            names.append(name)
        if max(np.linalg.norm(p-points[0]) for p in points)>1e-4:
            raise ValueError('pivot_blend_inconsistent_bind')
        active={n for n,w in zip(names,weights) if w>0}
        children=[b['name'] for b in bones if b['name'] in active and b.get('parent') in active]
        if len(active)>1 and (len(active)!=2 or len(children)!=1):
            raise ValueError('pivot_blend_requires_adjacent_pair')
        pivot=rest[children[0]][4:] if children else points[0]
        result.append(blend(points[0],pivot,transforms,weights))
    return result
