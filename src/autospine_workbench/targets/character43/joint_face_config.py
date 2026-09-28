"""Bounded, deterministic authoring controls for source-art facial motion."""
from copy import deepcopy
import math
import struct

GROUPS = {
    'blink': {'value': (0, 1)}, 'gaze': {'x': (-1, 1), 'y': (-1, 1)},
    'brows': {'lift': (-1, 1), 'tilt': (-1, 1)},
    'mouth': {'open': (0, 1), 'wide': (-1, 1)},
    'turn': {'yaw': (-1, 1), 'pitch': (-1, 1)},
}


def defaults():
    return dict(enabled=False,
        blink=dict(enabled=True, value=0., period=3.6, duration=.18, phase=.5, keys=[]),
        gaze=dict(enabled=True, x=0., y=0., keys=[]),
        brows=dict(enabled=True, lift=0., tilt=0., keys=[]),
        mouth=dict(enabled=True, open=0., wide=0., template_enabled=False, template_image=None, keys=[]),
        turn=dict(enabled=True, yaw=0., pitch=0., keys=[]), anchors={})


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('joint_face_number_out_of_range')
    return float(value)


def normalize(config, duration):
    number(duration, 0, 86400)
    if not isinstance(config, dict) or set(config) - set(defaults()):
        raise ValueError('joint_face_config_invalid')
    result = defaults()
    for field in config:
        if field in GROUPS:
            if not isinstance(config[field], dict) or set(config[field]) - set(result[field]):
                raise ValueError('joint_face_channel_invalid')
            result[field].update(deepcopy(config[field]))
        else:
            result[field] = deepcopy(config[field])
    if type(result['enabled']) is not bool:
        raise ValueError('joint_face_enabled_invalid')
    for group, fields in GROUPS.items():
        row = result[group]
        if type(row['enabled']) is not bool:
            raise ValueError('joint_face_enabled_invalid')
        for field, bounds in fields.items():
            row[field] = number(row[field], *bounds)
        keys = row['keys']
        if not isinstance(keys, list) or len(keys) > 256:
            raise ValueError('joint_face_keys_invalid')
        previous = -1
        previous_stored = -1
        for i, key in enumerate(keys):
            if not isinstance(key, dict) or set(key) - ({'time'} | set(fields)) or 'time' not in key:
                raise ValueError('joint_face_key_invalid')
            time = number(key['time'], 0, duration)
            if time <= previous:
                raise ValueError('joint_face_key_order')
            stored = struct.unpack('<f', struct.pack('<f', time))[0]
            if stored <= previous_stored:
                raise ValueError('joint_face_key_runtime_collapse')
            previous = time
            previous_stored = stored
            keys[i] = dict(time=time, **{f: number(key.get(f, row[f]), *b) for f, b in fields.items()})
    blink = result['blink']
    if type(result['mouth']['template_enabled']) is not bool:
        raise ValueError('joint_face_mouth_template_enabled_invalid')
    from .joint_face_mouth_upload import normalize as normalize_image
    result['mouth']['template_image'] = normalize_image(result['mouth']['template_image'])
    for field, bounds in {'period': (.3, 60), 'duration': (.06, .8), 'phase': (0, 60)}.items():
        blink[field] = number(blink[field], *bounds)
    if blink['duration'] >= blink['period']:
        raise ValueError('joint_face_blink_period')
    anchors = result['anchors']
    if not isinstance(anchors, dict) or len(anchors) > 64:
        raise ValueError('joint_face_anchors_invalid')
    for slot, value in anchors.items():
        if not isinstance(slot, str) or len(slot) > 256 or not isinstance(value, list) or len(value) != 2:
            raise ValueError('joint_face_anchor_invalid')
        anchors[slot] = [number(v, -8192, 8192) for v in value]
    return result


def values(row, time, fields):
    """Explicit keys take complete ownership over automatic/default values."""
    if not row['enabled']:
        return {field: 0. for field in fields}
    keys = row['keys']
    if not keys:
        return {field: row[field] for field in fields}
    if time <= keys[0]['time']:
        return {field: keys[0][field] for field in fields}
    if time >= keys[-1]['time']:
        return {field: keys[-1][field] for field in fields}
    for a, b in zip(keys, keys[1:]):
        if a['time'] <= time <= b['time']:
            u = (time-a['time'])/(b['time']-a['time'])
            return {f: a[f]+u*(b[f]-a[f]) for f in fields}
    raise ValueError('joint_face_key_sampling')


def blink_value(config, time):
    row = config['blink']
    if not row['enabled'] or row['keys']:
        return values(row, time, ('value',))['value']
    if time < row['phase']:
        return row['value']
    phase = (time-row['phase']) % row['period']
    if phase >= row['duration']:
        return row['value']
    u = phase/row['duration']
    # A short fully-closed hold gives an observable closed frame even at 30 fps.
    auto = min(1., u/.4, (1-u)/.4)
    return max(row['value'], auto)


def sample_times(config, times):
    if not times or any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times):
        raise ValueError('joint_face_times_invalid')
    duration = max(times)
    grid = {0., duration, *times}
    # Match the secondary solver's even-index grid exactly. Tiny stored-duration
    # rounding must not create two interleaved sets of nominal 60 Hz keys.
    if duration > 120:
        raise ValueError('joint_face_sample_budget')
    if duration:
        from .joint_spring import grid as secondary_grid
        grid.update(secondary_grid(duration, hz=60))
    for name in GROUPS:
        grid.update(k['time'] for k in config[name]['keys'])
    row = config['blink']
    if row['enabled'] and not row['keys']:
        start = row['phase']
        while start <= duration:
            grid.update(start+row['duration']*v for v in (0, .32, .4, .6, .68, 1)
                        if start+row['duration']*v <= duration)
            start += row['period']
    # Native/key/uniform grids can differ below Float32 time precision. Keep
    # one facial sample for each representable Runtime time, never equal keys.
    stored = {struct.pack('<f', t): t for t in sorted(grid)}
    return sorted(stored.values())
