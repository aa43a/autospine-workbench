"""Freeze a supported diagnostic animation at an exact time, without changing its rig."""
from copy import deepcopy
import math

from .continuous_pose import interpolate, world


def freeze(doc, animation, time):
    if not math.isfinite(time) or time < 0:
        raise ValueError('inspection_time')
    source = doc['animations'][animation]
    if set(source)-{'bones', 'attachments'}:
        raise ValueError('inspection_unsupported_timeline')
    frozen = deepcopy(source)

    def keys_at(keys, field):
        if (not keys or any(set(k)-{'time', field} for k in keys)
                or any(a['time'] >= b['time'] for a, b in zip(keys, keys[1:]))
                or not keys[0]['time'] <= time <= keys[-1]['time']):
            raise ValueError('inspection_unsupported_keys')
        value = interpolate(keys, time, field)
        return [dict(time=t, **{field: deepcopy(value)}) for t in (0., 1.)]

    for timelines in frozen.get('bones', {}).values():
        if set(timelines)-{'rotate'}:
            raise ValueError('inspection_unsupported_bone_timeline')
        if 'rotate' in timelines:
            timelines['rotate'] = keys_at(timelines['rotate'], 'value')
    for slots in frozen.get('attachments', {}).values():
        for attachments in slots.values():
            for timelines in attachments.values():
                if set(timelines)-{'deform'}:
                    raise ValueError('inspection_unsupported_attachment_timeline')
                if 'deform' in timelines:
                    timelines['deform'] = keys_at(timelines['deform'], 'vertices')
    result = deepcopy(doc)
    result['animations'] = {'inspection': frozen}
    expected = world(dict(doc, animations={animation: source}), time)
    errors = [math.dist(a, b) for t in (0., .5, 1.) for name, points in world(result, t).items()
              for a, b in zip(points, expected[name])]
    if not errors or max(errors) > 1e-7:
        raise ValueError('inspection_pose_mismatch')
    return result, max(errors)
