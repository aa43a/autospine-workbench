"""Explicit target-time samples mapped to unchanged source clip time."""
import math


def select(samples, times):
    if not samples or not isinstance(times, (list, tuple)) or not times or len(times) > 2049:
        raise ValueError('local_depth_sample_times_invalid')
    ticks = [s['tick'] for s in samples]
    if any(not math.isfinite(t) for t in ticks) or any(a >= b for a,b in zip(ticks,ticks[1:])):
        raise ValueError('local_depth_source_times_invalid')
    offset = samples[0]['source_tick'] - ticks[0]
    if any(s['source_tick']-s['tick'] != offset for s in samples):
        raise ValueError('local_depth_source_time_mapping_changed')
    if any(type(t) not in (int,float) or not math.isfinite(t) for t in times):
        raise ValueError('local_depth_sample_time_outside_clip')
    # Remove only seconds-to-ticks floating roundoff; do not clamp outside times.
    converted = [round(t*1e6) if abs(t*1e6-round(t*1e6)) < 1e-6 else t*1e6 for t in times]
    if any(not ticks[0] <= tick <= ticks[-1] for tick in converted):
        raise ValueError('local_depth_sample_time_outside_clip')
    return [dict(tick=tick,source_tick=tick+offset) for tick in sorted(set(converted))]


def repair_times(document, animation, depth):
    """Source keys, interval midpoints and both sides of every visibility switch."""
    ticks = sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    if not ticks:
        return None
    times = {t/1e6 for t in ticks}
    times.update((a+b)/2e6 for a,b in zip(ticks,ticks[1:]))
    for key in document['animations'][animation].get('drawOrder', []):
        t = key.get('time', 0)
        times.update(v for v in (t-1e-4,t,t+1e-4) if ticks[0]/1e6 <= v <= ticks[-1]/1e6)
    for tracks in document['animations'][animation].get('slots',{}).values():
        for key in tracks.get('alpha',[]):
            t = key.get('time',0)
            times.update(v for v in (t-1e-4,t,t+1e-4) if ticks[0]/1e6 <= v <= ticks[-1]/1e6)
    if len(times)>2049:
        raise ValueError('local_depth_sample_times_invalid')
    return sorted(times)
