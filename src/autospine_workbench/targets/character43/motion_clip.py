"""Frame-aligned clipping preserves source-relative pose and half-open contacts."""
from bisect import bisect_right
from copy import deepcopy

from ...motion_validation import require_motion_ir, motion_ir_sha256


def validate(selection, count):
    if (not isinstance(selection, dict) or set(selection) != {'start_frame', 'end_frame'}
            or any(type(selection[k]) is not int for k in selection)
            or not 0 <= selection['start_frame'] < selection['end_frame'] < count):
        raise ValueError('motion_clip_range_invalid')
    return dict(selection)


def boundaries(selection, ticks):
    if selection is None:
        return None
    validate(selection, len(ticks))
    return ticks[selection['start_frame']], ticks[selection['end_frame']]


def value_at(keys, time, time_key, field):
    i = max(0, bisect_right([k[time_key] for k in keys], time)-1)
    a, b = keys[i], keys[min(i+1, len(keys)-1)]
    ratio = 0 if a[time_key] == b[time_key] else (time-a[time_key])/(b[time_key]-a[time_key])
    left, right = a[field], b[field]
    if isinstance(left, list):
        return [x+(y-x)*ratio for x, y in zip(left, right)]
    return left+(right-left)*ratio


def keys_between(keys, start, end, time_key, fields):
    times = [start] + [k[time_key] for k in keys if start < k[time_key] < end] + [end]
    return [dict({time_key: t-start}, **{f: value_at(keys, t, time_key, f) for f in fields}) for t in times]


def clip_motion(motion, bounds):
    if bounds is None:
        return motion
    require_motion_ir(motion)
    start, end = bounds
    if not 0 <= start < end <= motion['duration_ticks']:
        raise ValueError('motion_clip_range_invalid')
    result = deepcopy(motion)
    result.update(clip_id='clip.'+motion_ir_sha256(motion)[:24]+f'.{start}.{end}',
                  duration_ticks=end-start, loop=False)
    for track in result['tracks']:
        track['keys'] = keys_between(track['keys'], start, end, 'tick', ['value'])
    result['markers'] = [dict(m, start_tick=max(start, m['start_tick'])-start,
                             end_tick=min(end, m['end_tick'])-start)
                         for m in result['markers'] if max(start, m['start_tick']) < min(end, m['end_tick'])]
    result['markers'].sort(key=lambda m: (m['start_tick'], m['end_tick'], m['limb']))
    require_motion_ir(result)
    return result


def clip_animation(document, name, bounds):
    if bounds is None:
        return document
    result = deepcopy(document)
    animation = result['animations'][name]
    if set(animation) != {'bones'}:
        raise ValueError('motion_clip_timeline_unsupported')
    start, end = (tick/1_000_000 for tick in bounds)
    for tracks in animation['bones'].values():
        for prop, keys in tracks.items():
            if prop not in ('rotate', 'translate', 'scale') or any('curve' in key for key in keys):
                raise ValueError('motion_clip_timeline_unsupported')
            tracks[prop] = keys_between(keys, start, end, 'time', ['value'] if prop == 'rotate' else ['x', 'y'])
    return result


def selected_ratios(values, times, time_range=None):
    indices = [i for i, t in enumerate(times) if time_range is None or time_range[0] <= t <= time_range[1]]
    if values[0] < .2 or not indices or any(values[i] < .2 for i in indices):
        raise ValueError('character_length_projection_collapsed')
    chosen = [values[i]/values[0] for i in indices]
    if min(chosen) < .5 or max(chosen) > 1.5:
        raise ValueError('character_length_ratio_outside_preview_range')
    return chosen, [times[i] for i in indices]
