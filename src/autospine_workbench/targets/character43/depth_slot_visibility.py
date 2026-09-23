"""Validate and sample binary stepped visibility used by material candidates."""
import math


def sample(document, animation, time):
    error = 'depth_overlap_attachment_unsupported'
    if type(time) not in (int, float) or not math.isfinite(time) or time < 0:
        raise ValueError('depth_overlap_time_invalid')
    known = {slot['name'] for slot in document['slots']}
    result = {slot['name']: 0 for slot in document['slots'] if slot.get('color') == 'ffffff00'}
    for name, tracks in document['animations'][animation].get('slots', {}).items():
        if name not in known or not isinstance(tracks, dict) or set(tracks) != {'alpha'}:
            raise ValueError(error)
        keys = tracks['alpha']
        if not isinstance(keys, list) or not keys:
            raise ValueError(error)
        previous = -1
        value = result.get(name, 1)
        for key in keys:
            if not isinstance(key, dict) or set(key) - {'time', 'value', 'curve'}:
                raise ValueError(error)
            tick = key.get('time', 0)
            alpha = key.get('value')
            if (type(tick) not in (int, float) or not math.isfinite(tick)
                    or tick < 0 or tick <= previous or key.get('curve') != 'stepped'
                    or type(alpha) not in (int, float) or alpha not in (0, 1)):
                raise ValueError(error)
            previous = tick
            if tick <= time:
                value = alpha
        result[name] = value
    return result
