"""Necessary constraints at one observed pose, never a complete repair proof."""
import numpy as np


def inspect(setup, posed, triangles, reference_setup, reference_pose, reference_triangles, regions):
    rest, points = np.asarray(setup, float), np.asarray(posed, float)
    source, target = np.asarray(reference_setup, float), np.asarray(reference_pose, float)
    if (rest.ndim != 2 or rest.shape[1] != 2 or points.shape != rest.shape
            or source.ndim != 2 or source.shape[1] != 2 or target.shape != source.shape
            or not all(np.isfinite(a).all() for a in (rest, points, source, target))):
        raise ValueError('contact_constraint_points_invalid')
    flat = list(triangles); other = list(reference_triangles)
    if (len(flat)%3 or len(other)%3 or any(type(v) is not int or not 0<=v<len(rest) for v in flat)
            or any(type(v) is not int or not 0<=v<len(source) for v in other)):
        raise ValueError('contact_constraint_triangles_invalid')
    if not {'fixed','sliding','free'} <= set(regions) <= {'fixed','sliding','free','transition','occlusion'}:
        raise ValueError('contact_constraint_regions_invalid')
    regions={'transition':[],'occlusion':[],**regions}
    selected = set(); vertices = {}
    for name, ids in regions.items():
        if (not isinstance(ids,list) or len(set(ids))!=len(ids) or selected.intersection(ids)
                or any(type(i) is not int or not 0<=i<len(flat)//3 for i in ids)):
            raise ValueError('contact_constraint_regions_invalid')
        selected.update(ids)
        vertices[name] = {v for i in ids for v in flat[i*3:i*3+3]}
    unknown = sorted(set(range(len(flat)//3))-selected)
    vertices['unknown'] = {v for i in unknown for v in flat[i*3:i*3+3]}
    # Coverage allows relative motion; it supplies no material-point target.
    preserved = vertices['free'] | vertices['unknown'] | vertices['occlusion']
    shared = vertices['fixed'] & preserved
    mappings, unsupported, ambiguous, conflicts = [], [], [], []
    for v in sorted(vertices['fixed']):
        mapped = []
        for offset in range(0,len(other),3):
            ids = other[offset:offset+3]; a,b,c = source[ids]
            matrix = np.column_stack((b-a,c-a))
            if abs(np.linalg.det(matrix))<1e-12:continue
            uv = np.linalg.solve(matrix,rest[v]-a)
            weights = np.array([1-uv.sum(),*uv])
            if np.min(weights)>=-1e-9:mapped.append(weights@target[ids])
        if not mapped:
            unsupported.append(v);continue
        if any(np.linalg.norm(p-mapped[0])>1e-6 for p in mapped[1:]):
            ambiguous.append(v);continue
        error = float(np.linalg.norm(mapped[0]-points[v]))
        mappings.append(dict(vertex=v,target=mapped[0].tolist(),displacement_px=error))
        if v in shared and error>1e-6:
            conflicts.append(dict(vertex=v,required_displacement_px=error,
                preserved_by=sorted(k for k in ('free','unknown','occlusion') if v in vertices[k])))
    reasons=[]
    if unsupported:reasons.append('reference_support_missing')
    if ambiguous:reasons.append('reference_mapping_ambiguous')
    if conflicts:reasons.append('shared_vertex_motion_conflict')
    if vertices['sliding']:reasons.append('sliding_constraints_not_implemented')
    if vertices['transition']:reasons.append('transition_constraints_not_implemented')
    return dict(status='requires_changes' if reasons else 'no_local_counterexample', reasons=reasons,
        vertex_roles={k:sorted(v) for k,v in vertices.items()}, unknown_triangles=unknown,
        shared_preserved_vertices=sorted(shared), fixed_targets=mappings, conflicts=conflicts,
        transition_preserved_vertices=sorted(vertices['transition'] & preserved),
        transition_only_vertices=sorted(vertices['transition']-preserved-vertices['fixed']-vertices['sliding']),
        unsupported_vertices=unsupported, ambiguous_vertices=ambiguous,
        occlusion_review=dict(required=bool(vertices['occlusion']),
            status='rendered_overlap_not_checked' if vertices['occlusion'] else 'not_requested',
            preserves_original_motion=True, material_correspondence_required=False),
        selected=False, authority='none', sufficient_for_repair=False,
        scope='single_pose_geometric_mapping_not_texture_contact_or_whole_animation')
