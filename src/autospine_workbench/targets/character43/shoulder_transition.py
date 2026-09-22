"""Opt-in proximal arm/chest weight transition, preserving setup world positions."""
from copy import deepcopy
import math
from .affine_pose import matrices, sample


def propose(document, *, band_ratio=.5):
    if not math.isfinite(band_ratio) or not 0 < band_ratio <= .5:
        raise ValueError('shoulder_transition_band_invalid')
    setup = dict(document, animations={'setup': {}})
    pose = matrices(setup, 'setup', 0)
    points, _ = sample(setup, 'setup', 0)
    bones = document['bones']; indices = {b['name']: i for i, b in enumerate(bones)}
    if 'chest' not in indices:
        raise ValueError('shoulder_transition_chest_missing')
    a, b, c, d, tx, ty = pose['chest']; det = a*d-b*c
    if det <= 1e-10:
        raise ValueError('shoulder_transition_chest_singular')
    result = deepcopy(document); records = []
    for slot in document['slots']:
        name = slot['name']; attachment = slot['attachment']
        mesh = document['skins'][0]['attachments'][name][attachment]
        raw = mesh.get('vertices', [])
        if mesh.get('type') != 'mesh' or len(raw) == len(mesh.get('uvs', [])):
            continue
        entries = []; cursor = 0
        while cursor < len(raw):
            count = raw[cursor]; cursor += 1
            entries.append([raw[j:j+4] for j in range(cursor, cursor+4*count, 4)])
            cursor += 4*count
        owners = {bones[e[0]]['name'] for row in entries for e in row if e[3] > 0}
        side = next((s for s in ('l', 'r') if owners <= {'upperarm_'+s, 'forearm_'+s, 'hand_'+s}
                     and 'upperarm_'+s in owners), None)
        if side is None:
            continue
        upper = 'upperarm_'+side; lower = 'forearm_'+side
        origin, end = pose[upper][4:], pose[lower][4:]
        dx, dy = end[0]-origin[0], end[1]-origin[1]; length2 = dx*dx+dy*dy
        if length2 <= 1e-10:
            raise ValueError('shoulder_transition_chain_degenerate')
        for animation in document['animations'].values():
            if animation.get('deform') or animation.get('attachments', {}).get('default', {}).get(name):
                raise ValueError('shoulder_transition_existing_deform')
        changed = []; output = []
        for vertex, (point, row) in enumerate(zip(points[name], entries)):
            t = ((point[0]-origin[0])*dx+(point[1]-origin[1])*dy)/length2
            # Only proximal, pure upper-arm vertices may gain torso influence.
            eligible = {bones[e[0]]['name'] for e in row if e[3] > 0} == {upper}
            weight = 0.
            if eligible and 0 <= t < band_ratio:
                u = t/band_ratio; weight = 1-u*u*(3-2*u)
            if weight > 1e-8:
                x, y = point[0]-tx, point[1]-ty
                row = [[i, lx, ly, w*(1-weight)] for i, lx, ly, w in row if w*(1-weight) > 0]
                row.append([indices['chest'], (d*x-b*y)/det, (-c*x+a*y)/det, weight])
                changed.append(dict(vertex=vertex, chest_weight=weight, axis_fraction=t))
            output.extend([len(row), *(v for e in row for v in e)])
        if changed:
            result['skins'][0]['attachments'][name][attachment]['vertices'] = output
            records.append(dict(slot=name, side=side, changed=changed))
    actual, _ = sample(dict(result, animations={'setup': {}}), 'setup', 0)
    error = max((math.dist(p, q) for name in points for p, q in zip(points[name], actual[name])), default=0)
    if error > 1e-6:
        raise ValueError('shoulder_transition_setup_changed')
    return result, dict(profile='proximal-arm-chest-transition-v1-experiment', records=records,
                        band_ratio=band_ratio, setup_max_error_px=error, authority='none', selected=False,
                        limitation='candidate_weights_require_geometry_contact_and_runtime_validation')
