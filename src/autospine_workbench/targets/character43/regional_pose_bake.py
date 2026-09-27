"""Bake isolated world-space garment poses as additive, linear deform keys."""
from copy import deepcopy
import math
from .affine_pose import matrices, sample
from .deform_addition import entries, local_delta, runtime_union_times, value


def bake(document, name, slot, poses, interval):
    start, end = interval
    if not poses or not math.isfinite(start+end) or not 0 <= start < end:
        raise ValueError('regional_bake_interval')
    if any(not start < t < end for t in poses):
        raise ValueError('regional_bake_pose_outside_interval')
    result = deepcopy(document)
    mesh = document['skins'][0]['attachments'][slot][slot]
    influences = entries(mesh); size = 2*sum(map(len, influences))
    correction = [dict(time=start, vertices=[0.]*size)]
    for time, points in sorted(poses.items()):
        original = sample(document, name, time)[0][slot]
        if len(points) != len(original) or any(len(p) != 2 for p in points):
            raise ValueError('regional_bake_pose_shape')
        correction.append(dict(time=time, vertices=local_delta(
            document, influences, matrices(document, name, time), original, points)))
    correction.append(dict(time=end, vertices=[0.]*size))
    tracks = result['animations'][name].setdefault('attachments', {}).setdefault('default', {})
    channels = tracks.setdefault(slot, {}).setdefault(slot, {})
    original = channels.get('deform', [])
    # Keep every original breakpoint, while avoiding added Float32 time aliases.
    times = runtime_union_times(original, correction)
    channels['deform'] = [dict(time=t, vertices=[a+b for a,b in zip(
        value(original,t,size), value(correction,t,size), strict=True)]) for t in times]
    return result
