"""Whole-clip trial of a pinned cloth solver with unchanged non-cloth vertices."""
from hashlib import sha256
from ...automation.storage_io import canonical_bytes
from ...asset.planning.cloth_shape_solver import solve
from ...asset.planning.component_local_solver import metrics
from .affine_pose import sample
from .drape_direction import apply


def probe(document, animation, helper, *, samples=33, constrained=False, on_frame=None, extra_times=(), temporal=False, exact_temporal=False, continuation=False, material=False, material_subframes=False, target_prior=0.):
    if type(samples) is not int or not 3 <= samples <= 513:
        raise ValueError('cloth_shape_probe_samples')
    if (temporal or exact_temporal) and not constrained: raise ValueError('cloth_shape_probe_temporal_requires_constraints')
    if continuation and not exact_temporal: raise ValueError('cloth_shape_probe_continuation_requires_exact')
    if material and not constrained: raise ValueError('cloth_shape_probe_material_requires_constraints')
    if material_subframes and not (material and exact_temporal): raise ValueError('cloth_material_subframe_options')
    if target_prior and not constrained: raise ValueError('cloth_target_prior_requires_constraints')
    held, _ = apply(document, animation, [helper])
    slot = helper.removeprefix('cloth-')
    attachment = document['skins'][0]['attachments'][slot][slot]
    data = attachment['vertices']; cursor = 0; index = 0; free = []
    while cursor < len(data):
        count = data[cursor]; cursor += 1; weight = 0.
        for _ in range(count):
            bone, _, _, w = data[cursor:cursor+4]; cursor += 4
            if document['bones'][bone]['name'] == helper: weight += w
        if weight > 1e-7: free.append(index)
        index += 1
    triangles = [attachment['triangles'][i:i+3] for i in range(0, len(attachment['triangles']), 3)]
    times = {k['time'] for tracks in document['animations'][animation]['bones'].values()
             for keys in tracks.values() for k in keys}
    duration = max(times); times = sorted(times | {duration*i/(samples-1) for i in range(samples)})
    import math
    if len(extra_times) > 1025 or any(type(t) not in (int, float) or not math.isfinite(t)
                                    or not 0 <= t <= duration for t in extra_times):
        raise ValueError('cloth_shape_probe_times')
    times = sorted(set(times) | set(extra_times))
    setup = sample(document, animation, 0)[0][slot]; seed = None; rows = []
    solver = solve
    if constrained:
        from ...asset.planning.cloth_shape_constraints import refine
        solver = refine
    previous_time = None
    for time in times:
        fixed = sample(document, animation, time)[0][slot]
        target = sample(held, animation, time)[0][slot]
        options = dict(seed=seed)
        if target_prior: options['target_prior'] = target_prior
        if temporal: options['temporal'] = True
        if continuation: options['continuation'] = True
        if material: options['material'] = True
        if material_subframes: options['material_subframes'] = True
        if exact_temporal and seed is not None:
            from .cloth_interval_map import build
            options['interval_maps'] = build(document, animation, slot, previous_time, time, seed)
        points, evidence = solver(setup, triangles, fixed, free, target, **options)
        seed = points
        previous_time = time
        if any(points[i] != p for i, p in enumerate(fixed) if i not in free):
            raise ValueError('cloth_shape_probe_fixed_changed')
        if on_frame is not None: on_frame(time, points, fixed)
        rows.append(dict(time=time, before=metrics(setup, target, triangles),
                         after=metrics(setup, points, triangles), solver=evidence))
    return dict(schema='autospine.cloth-shape-probe/v1', authority='none', selected=False,
                source_skeleton_sha256=sha256(canonical_bytes(document)).hexdigest(),
                helper=helper, animation=animation, sample_count=len(times), records=rows,
                free_vertex_source='existing_positive_cloth_helper_weight',
                limitation='sampled_shape_trial_not_gravity_or_contact_validation',
                runtime_status='not_evaluated')
