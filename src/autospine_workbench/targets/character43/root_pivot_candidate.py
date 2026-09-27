"""Explicit rotation-center experiment; preserves source orientation channels."""
from copy import deepcopy
import math
from .affine_pose import matrices
from ..spine43.continuous_pose import interpolate
from ...resolved_project import canonical_sha256


def build(document, animation, times, pivot='pelvis'):
    bones = {b['name']: b for b in document['bones']}
    if bones['root'].get('parent') or bones[pivot].get('parent') != 'root':
        raise ValueError('root_pivot_requires_direct_child')
    if (not 2 <= len(times) <= 4097 or times[0] != 0
            or any(not math.isfinite(t) for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError('root_pivot_times_invalid')
    root = document['animations'][animation]['bones']['root']
    if not root.get('rotate') or not root.get('translate'):
        raise ValueError('root_pivot_channels_missing')
    if any('curve' in k for keys in root.values() for k in keys):
        raise ValueError('root_pivot_requires_linear_channels')
    if any(k.get('time', 0) not in times for kind in ('rotate', 'translate') for k in root[kind]):
        raise ValueError('root_pivot_missing_source_knot')
    candidate = deepcopy(document)
    baseline = deepcopy(document)
    initial_rotation = interpolate(root['rotate'], 0, 'value')
    baseline['animations'][animation]['bones']['root']['rotate'] = [dict(time=0, value=initial_rotation)]
    keys = [dict(time=k['time'], vertices=[k['x'], k['y']]) for k in root['translate']]
    target = candidate['animations'][animation]['bones']['root']
    target['translate'] = []
    shifts = []
    for t in times:
        before = matrices(document, animation, t)[pivot][4:6]
        desired = matrices(baseline, animation, t)[pivot][4:6]
        shift = [b-a for a, b in zip(before, desired)]
        xy = interpolate(keys, t, 'vertices')
        target['translate'].append(dict(time=t, x=xy[0]+shift[0], y=xy[1]+shift[1]))
        shifts.append(math.hypot(*shift))
    samples = sorted(set(times) | {(a+b)/2 for a, b in zip(times, times[1:])})
    errors = [dict(time=t, error_px=math.dist(matrices(candidate, animation, t)[pivot][4:6],
                                           matrices(baseline, animation, t)[pivot][4:6])) for t in samples]
    return candidate, dict(profile='root-pelvis-pivot-experiment-v1', selected=False, authority='none',
        input_skeleton_sha256=canonical_sha256(document), skeleton_sha256=canonical_sha256(candidate),
        maximum_root_shift_px=max(shifts), pivot=pivot, samples=len(samples), worst=max(errors, key=lambda r:r['error_px']),
        scope='rotation_center_only_not_ankle_contact_geometry_or_visual_acceptance')
