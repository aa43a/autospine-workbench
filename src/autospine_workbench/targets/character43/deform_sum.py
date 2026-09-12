"""Exact sum of finite, dense, piecewise-linear deform channels on their key union."""
import math
from ..spine43.continuous_pose import interpolate


def combine(original, delta):
    width = None
    for keys in (original, delta):
        if not keys or keys[0]['time'] != 0: raise ValueError('cloth_deform_setup_missing')
        previous = -1
        for key in keys:
            if key.get('curve', 'linear') != 'linear': raise ValueError('cloth_deform_curve_unsupported')
            time = key['time']; values = key['vertices']
            if not math.isfinite(time) or time <= previous: raise ValueError('cloth_deform_time')
            if width is None: width = len(values)
            if not width or len(values) != width or not all(math.isfinite(v) for v in values):
                raise ValueError('cloth_deform_inventory')
            previous = time
    return [dict(time=time, vertices=[a+b for a, b in zip(
        interpolate(original, time, 'vertices'), interpolate(delta, time, 'vertices'))])
        for time in sorted({k['time'] for k in original+delta})]
