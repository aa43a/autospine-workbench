"""Continuous, unwrapped horizontal camera track shared by preview and baking."""
from copy import deepcopy
import math

PROFILE = 'continuous-yaw-source-camera-v1'


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate(keys, duration):
    if (not _number(duration) or duration <= 0 or not isinstance(keys, list)
            or not 1 <= len(keys) <= 256):
        raise ValueError('camera_track_invalid')
    previous = -1
    for key in keys:
        if (not isinstance(key, dict) or set(key) != {'time', 'yaw'}
                or not _number(key['time']) or not 0 <= key['time'] <= duration
                or key['time'] <= previous or not _number(key['yaw']) or abs(key['yaw']) > 3600):
            raise ValueError('camera_track_key_invalid')
        previous = key['time']
    if keys[0]['time'] != 0:
        raise ValueError('camera_track_start_invalid')
    return deepcopy(keys)


def sample(keys, time):
    """Caller supplies validated keys; do not collapse full turns modulo 360."""
    if not _number(time):
        raise ValueError('camera_track_time_invalid')
    if time <= keys[0]['time']:
        return keys[0]['yaw']
    for first, last in zip(keys, keys[1:]):
        if time <= last['time']:
            fraction = (time-first['time'])/(last['time']-first['time'])
            return first['yaw']+fraction*(last['yaw']-first['yaw'])
    return keys[-1]['yaw']


def at_times(keys, times, duration):
    keys = validate(keys, duration)
    if (not isinstance(times, (list, tuple)) or len(times) < 2 or times[0] != 0
            or any(not _number(t) or not 0 <= t <= duration for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError('camera_sample_times_invalid')
    return [sample(keys, t) for t in times]
