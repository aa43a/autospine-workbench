"""Bounded whole-root correction of ankle proxies; never claims sole locking."""
from copy import deepcopy
import math

from .motionir_candidate import sample
from ..spine43.continuous_pose import interpolate


def build(document, name, contacts, *, reference_length, max_ratio=.15,
          max_residual_px=1., release_seconds=.08, samples=257):
    if not all(math.isfinite(x) and x > 0 for x in (reference_length, max_ratio, release_seconds)):
        raise ValueError('contact_root_limits_invalid')
    if not math.isfinite(max_residual_px) or max_residual_px < 0 or type(samples) is not int or samples < 3:
        raise ValueError('contact_root_limits_invalid')
    animation = document['animations'][name]
    root = next(b for b in document['bones'] if b['name'] == 'root')
    if root.get('parent'):
        raise ValueError('contact_root_parent_unsupported')
    keys = animation['bones'].get('root', {}).get('translate')
    if not keys or not contacts:
        raise ValueError('contact_root_sources_missing')
    duration = keys[-1]['time']
    if any(c['limb'] not in ('leg.left', 'leg.right') or
           not 0 <= c['start'] < c['end'] <= duration for c in contacts):
        raise ValueError('contact_root_interval_invalid')
    ordered = sorted(contacts, key=lambda c: (c['start'], c['limb']))
    for i, c in enumerate(ordered):
        if any(c['limb'] == p['limb'] and c['start'] < p['end'] for p in ordered[:i]):
            raise ValueError('contact_root_same_limb_overlap')
    anchors = []
    for c in ordered:
        bone = 'foot_'+('l' if c['limb'] == 'leg.left' else 'r')
        anchors.append(dict(c, bone=bone, anchor=sample(document, name, c['start'])[1][bone][:2]))
    times = {duration*i/(samples-1) for i in range(samples)}
    times.update(k['time'] for k in keys)
    for c in anchors:
        times.update((c['start'], c['end'], min(duration, c['end']+release_seconds)))
    output = []; rows = []; last = (0., 0.); last_time = 0.; active_before = False
    release_from = (0., 0.); release_at = -release_seconds
    for time in sorted(times):
        active = [c for c in anchors if c['start'] <= time <= c['end']]
        if active:
            pose = sample(document, name, time)[1]
            offsets = [(c['anchor'][0]-pose[c['bone']][0], c['anchor'][1]-pose[c['bone']][1]) for c in active]
            correction = tuple(sum(p[i] for p in offsets)/len(offsets) for i in (0, 1))
            residual = max(math.dist(correction, p) for p in offsets)
        else:
            if active_before:
                release_from, release_at = last, last_time
            t = min(1., max(0., (time-release_at)/release_seconds))
            weight = 1-t*t*(3-2*t)
            correction = tuple(v*weight for v in release_from)
            residual = 0.
        magnitude = math.hypot(*correction)
        rows.append(dict(time=time, correction=list(correction), residual_px=residual,
                         within_limit=magnitude <= reference_length*max_ratio and residual <= max_residual_px))
        base = interpolate([dict(time=k['time'], vertices=[k['x'], k['y']]) for k in keys], time, 'vertices')
        output.append(dict(time=time, x=base[0]+correction[0], y=base[1]+correction[1]))
        last, last_time, active_before = correction, time, bool(active)
    passed = all(r['within_limit'] for r in rows)
    evidence = dict(profile='bounded-ankle-proxy-root-v1', authority='none', selected=False,
                    status='candidate' if passed else 'blocked', scope='ankle_proxy_not_sole_lock',
                    max_correction_px=max(math.hypot(*r['correction']) for r in rows),
                    max_residual_px=max(r['residual_px'] for r in rows), rows=rows,
                    limits=dict(max_ratio=max_ratio, max_residual_px=max_residual_px, release_seconds=release_seconds))
    if not passed:
        return None, evidence
    result = deepcopy(document)
    result['animations'][name]['bones']['root']['translate'] = output
    return result, evidence
