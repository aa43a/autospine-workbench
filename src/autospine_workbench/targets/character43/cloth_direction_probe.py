"""Diagnostic sweep of direction compensation; never selects a production driver."""
from copy import deepcopy
from hashlib import sha256
from ...automation.storage_io import canonical_bytes
from .affine_pose import sample
from .drape_direction import apply
from .deformation_qa import inspect


def sweep(document, animation, helpers, *, samples=65):
    if type(samples) is not int or not 3 <= samples <= 513:
        raise ValueError('cloth_direction_probe_samples')
    compensated, evidence = apply(document, animation, helpers)
    tracks = compensated['animations'][animation]['bones']
    key_times = {k['time'] for row in tracks.values() for keys in row.values() for k in keys}
    duration = max(key_times)
    times = sorted(key_times | {duration*i/(samples-1) for i in range(samples)})
    # A standalone diagnostic includes only the requested clip, never other clips' references.
    records = []
    for fraction in (0., .25, .5, .75, 1.):
        candidate = deepcopy(compensated)
        candidate['animations'] = {animation: candidate['animations'][animation]}
        for helper in helpers:
            for key in candidate['animations'][animation]['bones'][helper]['rotate']:
                key['value'] *= fraction
        raw = canonical_bytes(candidate)
        frames = [dict(time=t, vertices=sample(candidate, animation, t)[0]) for t in times]
        reference = dict(skeleton_sha256=sha256(raw).hexdigest(), animations={animation: frames})
        qa = inspect({'skeleton.json': raw, 'numeric-reference.json': canonical_bytes(reference)})
        slots = []
        for helper in sorted(helpers):
            slot = helper.removeprefix('cloth-')
            row = next(r for r in qa['records'] if r['slot'] == slot)
            attachment = candidate['skins'][0]['attachments'][slot][slot]
            flat = attachment['vertices']; cursor = 0; cloth_vertices = []
            index = 0
            while cursor < len(flat):
                count = flat[cursor]; cursor += 1; weight = 0.
                for _ in range(count):
                    bone, _, _, w = flat[cursor:cursor+4]; cursor += 4
                    if candidate['bones'][bone]['name'] == helper:
                        weight += w
                if weight >= 1-1e-7:
                    cloth_vertices.append(index)
                index += 1
            # Report geometry separately: compensation is not proof that cloth looks natural.
            slots.append(dict(slot=slot, pure_cloth_vertices=len(cloth_vertices),
                              geometry=row, residual_ancestor_rotation_degrees=(1-fraction)*next(
                                  r['maximum_compensation_degrees'] for r in evidence['records']
                                  if r['bone'] == helper)))
        records.append(dict(compensation_fraction=fraction, geometry_passed=qa['passed'], slots=slots))
    return dict(schema='autospine.cloth-direction-probe/v1', authority='none',
                source_skeleton_sha256=sha256(canonical_bytes(document)).hexdigest(),
                animation=animation, sample_count=len(times), records=records,
                scope='sampled_direction_geometry_tradeoff', runtime_status='not_evaluated',
                selected=False, limitation='no_contact_or_visual_acceptance')
