"""Locate actual opaque blockers that contradict same-frame source depth proxies.

Proxy contradictions remain diagnostics, never permission to change draw order.
Partial alpha, absent measurements and fully hidden material stay explicit.
"""
from collections import Counter


def build(rows, checks):
    lookup = {}
    for check in checks:
        key = (check['arm'], check['body'], check['time'])
        if key in lookup: raise ValueError('visibility_depth_duplicate_evidence')
        lookup[key] = check
    result = []
    for row in rows:
        region = row['region']; points = []
        if row['prior_frame_max_channel_delta'] > 1 or row.get('restored') is not True:
            raise ValueError('visibility_depth_frame_unverified')
        for point in row['points']:
            support = point['support']; names = [s['slot'] for s in support]
            if len(names) != len(set(names)): raise ValueError('visibility_depth_duplicate_support')
            if region not in names:
                points.append(dict(x=point['x'], y=point['y'], status='target_not_rasterized', blockers=[]))
                continue
            target = names.index(region); blockers = []
            for layer in support[target+1:]:
                evidence = lookup.get((region, layer['slot'], row['time']))
                status = evidence['status'] if evidence else 'missing_evidence'
                if status == 'no_overlap' and layer['rgba'][3] >= 8 and support[target]['rgba'][3] >= 8:
                    status = 'cpu_gpu_support_disagreement'
                blockers.append(dict(slot=layer['slot'], alpha=layer['rgba'][3],
                                     depth_status=status, opaque=layer['rgba'][3] == 255))
            hidden = point['hide_deltas'][region] <= 1
            contrary = [b['slot'] for b in blockers if b['opaque'] and b['depth_status'] == 'uniform_front_proxy']
            nearest = next((b for b in reversed(blockers) if b['opaque']), None)
            visible_conflict = bool(nearest and nearest['depth_status'] == 'uniform_front_proxy')
            # Do not promote a partly transparent contributor to a proven opaque blocker.
            # A conflict buried under another opaque layer is not a visible leg conflict.
            state = ('opaque_blocker_proxy_conflict' if hidden and visible_conflict else
                     'hidden_depth_unresolved' if hidden else 'target_has_visible_contribution')
            points.append(dict(x=point['x'], y=point['y'], status=state, blockers=blockers,
                               contrary_opaque_slots=contrary, target_alpha=support[target]['rgba'][3],
                               nearest_opaque_blocker=nearest,
                               hide_delta=point['hide_deltas'][region], source_marker=point['kind']))
        result.append(dict(time=row['time'], region=region, points=points,
                           counts=dict(Counter(p['status'] for p in points))))
    return dict(profile='runtime-visible-blocker-source-depth-v1', rows=result,
                counts=dict(Counter(p['status'] for r in result for p in r['points'])),
                scope='selected_gpu_pixels_vs_source_proxy_not_surface_truth_or_adoption',
                authority='none', selected=False)
