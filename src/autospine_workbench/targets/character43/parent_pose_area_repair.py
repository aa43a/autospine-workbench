"""Single-pose parent-relative repair experiment; never grants animation acceptance."""
from copy import deepcopy
from hashlib import sha256
import math

from ...automation.storage_io import canonical_bytes
from .affine_pose import matrices, sample
from .area_projection import project
from .deform_addition import entries
from .projected_area_reference import reference
from .raw_compression_preservation import CONTRACT, floors
from ..spine43.continuous_pose import area


def verify_source(parent, candidate, name, slot):
    """Only the selected deform can differ; the comparison uses identical motion."""
    def stripped(document):
        value = deepcopy(document)
        animation = value['animations'][name]
        for skin in list(animation.get('attachments', {})):
            if skin == 'default':animation['attachments'][skin].pop(slot, None)
            if not animation['attachments'][skin]:del animation['attachments'][skin]
        if not animation.get('attachments'):animation.pop('attachments', None)
        return value
    if stripped(parent) != stripped(candidate):raise ValueError('parent_pose_unrelated_changes')
    if slot not in parent['skins'][0]['attachments']:raise ValueError('parent_pose_slot_missing')


def solve(context, origin, parent_points, setup_areas, *, protect_setup=False, local_refinement=False):
    """Keep the parent compression floor without changing fixed vertices or budgets."""
    trial = deepcopy(context)
    trial['minimum_ratios'] = floors(parent_points, trial['row']['triangles'], trial['areas'], setup_areas)
    protected = []
    if protect_setup:
        from .parent_setup_preservation import floors as joint_floors
        trial['minimum_ratios'], protected = joint_floors(parent_points, trial['row']['triangles'], trial['areas'], setup_areas)
    trial['area_floor_contract'] = CONTRACT
    from .area_budget_feasibility import inspect as budget_check
    feasibility = budget_check(trial, origin, trial['minimum_ratios'])
    from .fixed_boundary_area import inspect as boundary_check
    boundary = boundary_check(trial, origin, trial['minimum_ratios'])
    from .single_vertex_area_feasibility import inspect as shared_check
    shared = shared_check(trial, origin, trial['minimum_ratios'])
    corrected, evidence = project(trial, origin)
    if local_refinement and not evidence['converged']:
        from .local_area_constraints import refine
        corrected, refinement = refine(trial, origin, corrected, analytic=True, expanded=True,
                                       active_tolerance=1e-7,feasibility_first=True)
        evidence.update(projection_converged=False, refinement=refinement,
                        converged=refinement['status']=='candidate')
    return corrected, dict(evidence, parent_floors=trial['minimum_ratios'], setup_protected_triangles=protected,
                           budget_feasibility=feasibility,boundary_feasibility=boundary,
                           shared_vertex_feasibility=shared)


def compare(parent, candidate, name, slot, time, *, protect_setup=False, local_refinement=False):
    if local_refinement and not protect_setup:raise ValueError('parent_refinement_requires_joint_floors')
    verify_source(parent, candidate, name, slot)
    keys = [k['time'] for tracks in parent['animations'][name]['bones'].values() for values in tracks.values() for k in values]
    if not math.isfinite(time) or not 0 <= time <= max(keys):raise ValueError('parent_pose_time_invalid')
    rest = deepcopy(parent);rest['animations'] = {name: {'bones': {}}}
    setup = sample(rest, name, 0)[0][slot]
    previous = sample(parent, name, time)[0][slot]
    origin = sample(candidate, name, time)[0][slot]
    mesh = parent['skins'][0]['attachments'][slot][slot]
    triangles = [mesh['triangles'][i:i+3] for i in range(0, len(mesh['triangles']), 3)]
    influences = entries(mesh);bones = parent['bones']
    areas = [area(setup, t) for t in triangles]
    refs = reference(areas, triangles, influences, bones, matrices(rest, name, 0), matrices(parent, name, time))
    used = {bones[b]['name'] for row in influences for b,w in row if w > 0}
    lengths = [math.hypot(b['x'], b['y']) for b in bones if b['name'] in used and b.get('parent') in used]
    if not lengths or min(lengths) <= 0:raise ValueError('parent_pose_chain_missing')
    edges = sorted({tuple(sorted((t[i], t[(i+1)%3]))) for t in triangles for i in range(3)})
    context = dict(row={'triangles': triangles}, areas=refs, edges=edges,
        lengths=[math.dist(setup[a], setup[b]) for a,b in edges], budget=.1*min(lengths),
        free=[sum(w > 0 for _,w in row) > 1 for row in influences])
    parent_ratios = [area(previous,t)/a for t,a in zip(triangles, areas)]
    def metrics(points):
        ratios = [area(points,t)/a for t,a in zip(triangles, areas)]
        regressed = [i for i,(r,p) in enumerate(zip(ratios,parent_ratios)) if 0 < p < .5 and r < p-1e-7]
        return dict(minimum_setup_ratio=min(ratios), maximum_setup_ratio=max(ratios),
            inversions=sum(r<=0 for r in ratios), setup_failures=sum(not .5<=r<=2 for r in ratios),
            compressed_parent_regressions=regressed,
            movable_compression_regressions=[i for i in regressed if any(context['free'][v] for v in triangles[i])],
            fixed_compression_regressions=[i for i in regressed if not any(context['free'][v] for v in triangles[i])],
            newly_failed_healthy=[i for i,(r,p) in enumerate(zip(ratios,parent_ratios)) if .5<=p<=2 and not .5<=r<=2],
            maximum_edge_ratio=max(math.dist(points[a],points[b])/l for (a,b),l in zip(edges,context['lengths'])),
            maximum_shift=max(math.dist(a,b) for a,b in zip(points,origin)),
            fixed_shift=max([math.dist(a,b) for a,b,f in zip(points,origin,context['free']) if not f] or [0]),
            setup_ratios=ratios)
    baseline, baseline_solver = project(context, origin)
    corrected, solver = solve(context, origin, previous, areas)
    solver['floor_failures'] = [i for i,(t,r,f) in enumerate(zip(triangles,refs,solver['parent_floors']))
                                if area(corrected,t)/r < f-1e-7]
    result = dict(profile='parent-pose-area-repair-v1-experiment', time=time, slot=slot,
        parent_sha256=sha256(canonical_bytes(parent)).hexdigest(),
        candidate_sha256=sha256(canonical_bytes(candidate)).hexdigest(), budget_px=context['budget'],
        parent=metrics(previous), transverse=metrics(origin),
        projected_only=dict(metrics(baseline), solver=baseline_solver),
        parent_floor=dict(metrics(corrected), solver=solver),
        points=dict(parent=previous, transverse=origin, projected_only=baseline, parent_floor=corrected),
        triangles=triangles, selected=False, authority='none',
        scope='single_pose_cpu_experiment_not_continuous_or_runtime_acceptance')
    if protect_setup:
        joint, joint_solver = solve(context, origin, previous, areas, protect_setup=True, local_refinement=local_refinement)
        joint_solver['floor_failures'] = [i for i,(t,r,f) in enumerate(zip(triangles,refs,joint_solver['parent_floors']))
                                          if area(joint,t)/r < f-1e-7]
        result['parent_setup_floor'] = dict(metrics(joint), solver=joint_solver)
        result['points']['parent_setup_floor'] = joint
    return result
