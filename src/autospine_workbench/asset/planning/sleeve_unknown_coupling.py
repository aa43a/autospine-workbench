"""Locate unresolved ownership that pins garment vertices to a hand driver."""
from collections import defaultdict
import math


def analyze(triangles, assignments, weights, hand_id, bad_triangles):
    if len(triangles) != len(assignments): raise ValueError('sleeve_coupling_inventory')
    roles=defaultdict(set); touching=defaultdict(set)
    for index,(tri,assignment) in enumerate(zip(triangles,assignments)):
        if assignment['triangle_id'] != index: raise ValueError('sleeve_coupling_order')
        if len(tri)!=3 or any(type(v)!=int or not 0<=v<len(weights) for v in tri):
            raise ValueError('sleeve_coupling_vertex')
        for vertex in tri:
            roles[vertex].add(assignment['role']);touching[vertex].add(index)
    bad=set(bad_triangles)
    if any(type(i)!=int or not 0<=i<len(triangles) for i in bad): raise ValueError('sleeve_coupling_bad_triangle')
    rows=[]
    for vertex,labels in sorted(roles.items()):
        if 'unknown' not in labels or not labels.intersection({'sleeve','cuff','hanging_cloth'}): continue
        values=[w['weight'] for w in weights[vertex] if w['bone_id']==hand_id]
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values):
            raise ValueError('sleeve_coupling_weight')
        influence=sum(values)
        if influence<=1e-12: continue
        rows.append(dict(vertex_id=vertex,hand_weight=influence,roles=sorted(labels),
            unknown_triangles=sorted(i for i in touching[vertex] if assignments[i]['role']=='unknown'),
            adjacent_failed_triangles=sorted(touching[vertex]&bad)))
    return dict(vertices=rows,unknown_triangles=sorted({i for r in rows for i in r['unknown_triangles']}),
        failed_triangle_roles={role:sum(assignments[i]['role']==role for i in bad)
            for role in sorted({assignments[i]['role'] for i in bad})},
        reason_code='unknown_hand_garment_coupling' if rows else 'no_unknown_hand_garment_coupling',
        scope='shared_vertex_influence_not_causal_proof',authority='none',production_authorized=False)
