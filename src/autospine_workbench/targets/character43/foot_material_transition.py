"""Explicit foot-material anchors with a fixed calf exterior; experimental only."""
import math
from statistics import median
from .deform_addition import entries
from .material_anchor_field import solve as harmonic
from .material_anchor_constraints import inspect_paths
from ...asset.planning.component_local_solver import metrics


def solve(mesh, setup, posed, foot_adjusted, foot_index, calf_index, *, refine_transition=False):
    owners=entries(mesh)
    if not len(owners)==len(setup)==len(posed)==len(foot_adjusted):
        raise ValueError('foot_transition_vertex_count')
    anchors=[];moving=[]
    for vertex,row in enumerate(owners):
        bones={i for i,w in row if w>0}
        if foot_index not in bones:continue
        if not bones<={foot_index,calf_index}:
            raise ValueError('foot_transition_unexpected_influence')
        moving.append(vertex)
        if bones=={foot_index}:anchors.append(vertex)
    if not anchors:raise ValueError('foot_transition_no_pure_foot_anchors')
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    targets={i:foot_adjusted[i] for i in anchors}
    constraints=inspect_paths(setup,posed,triangles,targets,moving)
    points,evidence=harmonic(setup,posed,triangles,targets,moving)
    # Restrict comparison to triangles touched by the foot transition. Existing
    # knee failures stay in the separate whole-attachment metrics.
    touched=[i for i,t in enumerate(triangles) if set(t)&set(moving)]
    local=[triangles[i] for i in touched]
    def quality(values):return metrics(setup,values,local)
    before=quality(posed);after=quality(points);hard=None
    if refine_transition and (after['bad_triangles'] or after['max_edge_stretch']>2):
        from .boundary_shape_feasible import refine
        from hashlib import sha256
        from pathlib import Path
        from . import boundary_shape_feasible
        free=sorted(set(moving)-set(anchors))
        edges={tuple(sorted((a,b))) for t in local for a,b in zip(t,t[1:]+t[:1])}
        budget=median(math.dist(setup[a],setup[b]) for a,b in edges)
        if free:
            regions=[dict(vertex=i,center=points[i],inverse=[[1.,0.],[0.,1.]],radius=budget) for i in free]
            points,hard=refine(setup,local,points,free,points,points,budget,regions=regions)
            hard['budget_px']=budget
            hard['solver_source_sha256']=sha256(Path(boundary_shape_feasible.__file__).read_bytes()).hexdigest()
            after=quality(points)
    return points,dict(authority='none',selected=False,
        scope='pose_only_weight_defined_foot_region_not_semantic_or_runtime_acceptance',
        anchors=anchors,moving=moving,transition_triangles=touched,
        constraints=constraints,solver=evidence,hard_refinement=hard,before=before,after=after,
        direct_foot_adjustment=quality(foot_adjusted),whole_attachment=metrics(setup,points,triangles),
        transition_passed=not after['bad_triangles'] and after['max_edge_stretch']<=2)
