"""Explicit half-open order intervals; no pose or depth inference."""
import math

PROFILE = 'selected-region-interval-order-v1'


def duration(value):
    """Find source timeline duration without adding order keys to the source."""
    times = [0.0]
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'time':
                if type(child) not in (int, float) or not math.isfinite(child) or child < 0:
                    raise ValueError('region_order_source_time_invalid')
                times.append(child)
            else:
                times.append(duration(child))
    elif isinstance(value, list):
        times.extend(duration(child) for child in value)
    return max(times)


def apply(candidate, original_slots, desired_slots, animation, interval):
    if not isinstance(animation, str) or animation not in candidate['animations']:
        raise ValueError('region_order_animation_invalid')
    motion = candidate['animations'][animation]
    if (not isinstance(interval, (list, tuple)) or len(interval) != 2
            or any(type(t) not in (int, float) or not math.isfinite(t) for t in interval)
            or not 0 <= interval[0] < interval[1] <= duration(motion)):
        raise ValueError('region_order_interval_invalid')
    names = [s['name'] for s in original_slots]
    desired = [s['name'] for s in desired_slots]
    candidate['slots'] = original_slots
    motion['drawOrder'] = [
        dict(time=interval[0], offsets=[dict(slot=name, offset=desired.index(name)-i)
                                      for i, name in enumerate(names)]),
        dict(time=interval[1], offsets=[])]
    return dict(profile=PROFILE, animation=animation, interval=list(interval),
                interval_semantics='start_inclusive_end_exclusive',
                setup_order=names, active_order=desired,
                scope='interval_order_candidate_requires_visual_and_runtime_review')
