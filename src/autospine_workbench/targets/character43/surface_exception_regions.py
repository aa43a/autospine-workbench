"""Area-based surface exceptions; no automatic acceptance by small affected area."""
from collections import defaultdict
import numpy as np


def summarize(rest,triangles,roles,evidence,influences,bone_names):
    points=np.asarray(rest,float);tri=np.asarray(triangles)
    rows=evidence['triangles']
    if (points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all() or
            tri.ndim!=2 or tri.shape[1]!=3 or not tri.size or
            not np.issubdtype(tri.dtype,np.integer) or tri.min()<0 or tri.max()>=len(points) or
            len(roles)!=len(tri) or len(rows)!=len(tri) or len(influences)!=len(points) or
            [r['triangle'] for r in rows]!=list(range(len(tri)))):
        raise ValueError('surface_exception_input')
    areas=np.linalg.norm(np.cross(points[tri[:,1]]-points[tri[:,0]],points[tri[:,2]]-points[tri[:,0]]),axis=1)/2
    groups=defaultdict(list);totals=defaultdict(float)
    for i,(face,role,row) in enumerate(zip(tri,roles,rows)):
        totals[role]+=float(areas[i])
        if row.get('intrinsic_gate_passed',False):continue
        bones=tuple(sorted({bone_names[b] for v in face for b,w in influences[v] if w>.01}))
        groups[(role,bones)].append(i)
    output=[]
    for (role,bones),ids in sorted(groups.items()):
        # Report separate components even when their material and bone sets agree.
        pending=set(ids);vertex_faces=defaultdict(set)
        for i in ids:
            for v in tri[i]:vertex_faces[int(v)].add(i)
        while pending:
            queue=[min(pending)];component=set(queue);pending.remove(queue[0])
            while queue:
                for v in tri[queue.pop()]:
                    for j in vertex_faces[int(v)]&pending:
                        component.add(j);pending.remove(j);queue.append(j)
            selected=sorted(component);vertices=np.unique(tri[selected]);subset=points[vertices]
            affected=float(areas[selected].sum())
            output.append(dict(material_role=role,bones=list(bones),triangles=selected,
                rest_area=affected,role_rest_area=totals[role],
                fraction_of_role_area=affected/totals[role] if totals[role]>0 else None,
                bounds=[subset.min(axis=0).tolist(),subset.max(axis=0).tolist()],
                accepted=False,visible=None))
    return dict(regions=output,role_rest_areas=dict(totals),accepted=False,
                limitations=['bone_set_uses_weight_over_0.01_not_causality',
                             'rest_area_not_screen_visibility','small_area_does_not_waive_failure'])
