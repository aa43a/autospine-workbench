"""Causal contact-entry anchors and continuous release for root candidates."""
from copy import deepcopy
import math

from .affine_pose import matrices
from .motion_contacts import analyze, schedule
from ..spine43.continuous_pose import interpolate


def build(document, name, motion, times, reference_length, *, release_seconds=.08):
    if not math.isfinite(reference_length) or reference_length <= 0 or not math.isfinite(release_seconds) or release_seconds <= 0:
        raise ValueError('contact_phase_limits_invalid')
    root = next(b for b in document['bones'] if b['name'] == 'root')
    if root.get('parent'):
        raise ValueError('contact_phase_root_parent_unsupported')
    rate = motion['ticks_per_second']
    duration = motion['duration_ticks']/rate
    contacts = sorted([dict(limb=m['limb'], start=m['start_tick']/rate, end=m['end_tick']/rate)
                       for m in motion['markers'] if m['kind'] == 'contact'], key=lambda r: (r['start'], r['limb']))
    for i, row in enumerate(contacts):
        if row['limb'] not in ('leg.left', 'leg.right') or not 0 <= row['start'] < row['end'] <= duration:
            raise ValueError('contact_phase_interval_invalid')
        if any(p['limb'] == row['limb'] and row['start'] < p['end'] for p in contacts[:i]):
            raise ValueError('contact_phase_interval_overlap')
    keys = document['animations'][name]['bones'].get('root', {}).get('translate')
    if not contacts or not keys:
        raise ValueError('contact_phase_sources_missing')
    if any('curve' in k for row in document['animations'][name]['bones'].values() for track in row.values() for k in track):
        raise ValueError('contact_phase_linear_timeline_required')
    knots = {duration*i/256 for i in range(257)} | set(times) | {k['time'] for k in keys}
    for row in contacts:
        knots.update((row['start'], row['end'], min(duration, row['end']+release_seconds)))
    if len(knots) > 2048 or any(not math.isfinite(t) or not 0 <= t <= duration for t in knots):
        raise ValueError('contact_phase_sample_limit')
    anchors, rows, output = [], [], []
    for t in sorted(knots):
        pose = matrices(document, name, t)
        weighted = []
        active = []
        for anchor in anchors:
            if anchor.get('retired'):
                continue
            if t >= anchor['end'] and 'release_offset' not in anchor:
                at_end = matrices(document, name, anchor['end'])[anchor['bone']][4:6]
                anchor['release_offset'] = [anchor['point'][i]-at_end[i] for i in (0, 1)]
            if t < anchor['end']:
                offset = [anchor['point'][i]-pose[anchor['bone']][i+4] for i in (0, 1)]
                weighted.append((1., offset)); active.append(offset)
            elif t < anchor['end']+release_seconds:
                u = (t-anchor['end'])/release_seconds
                weighted.append((1-u*u*(3-2*u), anchor['release_offset']))
        total = max(1., sum(w for w, _ in weighted))
        carry = [sum(w*p[i] for w, p in weighted)/total for i in (0, 1)]
        entering = [c for c in contacts if c['start'] == t]
        if entering and not active:
            # A new support takes over the current released pose without blending
            # the same old release a second time into its freshly latched anchor.
            for anchor in anchors:
                if anchor['end'] <= t:
                    anchor['retired'] = True
            weighted = []
        for contact in entering:
            bone = 'foot_'+('l' if contact['limb'] == 'leg.left' else 'r')
            anchors.append(dict(contact, bone=bone, point=[pose[bone][i+4]+carry[i] for i in (0, 1)]))
            weighted.append((1., carry)); active.append(carry)
        total = max(1., sum(w for w, _ in weighted))
        correction = [sum(w*p[i] for w, p in weighted)/total for i in (0, 1)]
        residual = max((math.dist(correction, p) for p in active), default=0.)
        base = interpolate([dict(time=k['time'], vertices=[k['x'], k['y']]) for k in keys], t, 'vertices')
        output.append(dict(time=t, x=base[0]+correction[0], y=base[1]+correction[1]))
        rows.append(dict(time=t, correction=correction, residual_px=residual, active_contacts=len(active)))
    candidate = deepcopy(document)
    candidate['animations'][name]['bones']['root']['translate'] = output
    max_shift = max(math.hypot(*r['correction']) for r in rows)
    max_speed = max((math.dist(a['correction'], b['correction'])/(b['time']-a['time'])
                     for a, b in zip(rows, rows[1:])), default=0.)
    checked = analyze(candidate, name, motion, schedule(motion, sorted(knots)), reference_length)
    reasons = []
    if max_shift > .15*reference_length: reasons.append('phase_root_displacement_limit')
    if max_speed > 2*reference_length: reasons.append('phase_root_speed_limit')
    if not checked['passed']: reasons.append('phase_contact_residual')
    report = dict(profile='causal-contact-entry-release-v1', authority='none', selected=False,
        status='blocked' if reasons else 'candidate', reason_codes=reasons, anchors=anchors, rows=rows,
        max_correction_px=max_shift, max_speed_px_per_second=max_speed, after=checked,
        limits=dict(root_ratio=.15, speed_ratio=2., drift_ratio=.01, release_seconds=release_seconds))
    return (None if reasons else candidate), report
