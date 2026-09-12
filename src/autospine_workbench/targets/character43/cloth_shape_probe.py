"""Whole-clip trial of a pinned cloth solver with unchanged non-cloth vertices."""
from hashlib import sha256
from ...automation.storage_io import canonical_bytes
from ...asset.planning.cloth_shape_solver import solve
from ...asset.planning.component_local_solver import metrics
from .affine_pose import sample
from .drape_direction import apply


def probe(document, animation, helper, *, samples=33):
    if type(samples) is not int or not 3 <= samples <= 513:
        raise ValueError('cloth_shape_probe_samples')
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
    setup = sample(document, animation, 0)[0][slot]; seed = None; rows = []
    for time in times:
        fixed = sample(document, animation, time)[0][slot]
        target = sample(held, animation, time)[0][slot]
        points, evidence = solve(setup, triangles, fixed, free, target, seed=seed)
        seed = points
        if any(points[i] != p for i, p in enumerate(fixed) if i not in free):
            raise ValueError('cloth_shape_probe_fixed_changed')
        rows.append(dict(time=time, before=metrics(setup, target, triangles),
                         after=metrics(setup, points, triangles), solver=evidence))
    return dict(schema='autospine.cloth-shape-probe/v1', authority='none', selected=False,
                source_skeleton_sha256=sha256(canonical_bytes(document)).hexdigest(),
                helper=helper, animation=animation, sample_count=len(times), records=rows,
                free_vertex_source='existing_positive_cloth_helper_weight',
                limitation='sampled_shape_trial_not_gravity_or_contact_validation',
                runtime_status='not_evaluated')
