"""Source-label ankle-proxy QA and reversible, bounded root correction."""
from hashlib import sha256
import json
import math

from .affine_pose import matrices
from .contact_root_candidate import build as root_candidate

POLICY = 'external-motion-ankle-contact-v1'
MAX_CORRECTION_RATIO = .15
MAX_DRIFT_RATIO = .01
MAX_CORRECTION_SPEED_RATIO = 2.
RELEASE_SECONDS = .08


def _identity(document):
    return sha256(json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _intervals(motion):
    rate = motion['ticks_per_second']
    return [dict(limb=m['limb'], start=m['start_tick']/rate, end=m['end_tick']/rate)
            for m in motion['markers'] if m['kind'] == 'contact']


def schedule(motion, times):
    """Measure at both sides of half-open contact boundaries and between samples."""
    duration = motion['duration_ticks']/motion['ticks_per_second']
    selected = set(times)
    for c in _intervals(motion):
        selected.update((c['start'], c['end'], math.nextafter(c['end'], c['start']),
                         min(duration, c['end']+RELEASE_SECONDS)))
    base = sorted(selected)
    selected.update((a+b)/2 for a, b in zip(base, base[1:]) if b-a > 1e-9)
    if len(selected) > 4096:
        raise ValueError('motion_contact_sample_limit')
    return sorted(selected)


def analyze(document, name, motion, times, reference_length):
    intervals = _intervals(motion)
    limit = reference_length*MAX_DRIFT_RATIO
    rows = []
    # Cache FK once per time. Skinning pixels is unnecessary for ankle proxies.
    poses = {t: matrices(document, name, t) for t in times}
    for interval in intervals:
        bone = 'foot_'+('l' if interval['limb'] == 'leg.left' else 'r')
        anchor = matrices(document, name, interval['start'])[bone][4:6]
        samples = []
        for t, pose in poses.items():
            if not interval['start'] <= t < interval['end']:
                continue
            point = pose[bone][4:6]
            samples.append(dict(time=t, x=point[0], y=point[1], drift_px=math.dist(anchor, point),
                                horizontal_px=abs(point[0]-anchor[0]), vertical_px=abs(point[1]-anchor[1])))
        worst = max(samples, key=lambda s: s['drift_px'])
        rows.append(dict(**interval, bone=bone, anchor=list(anchor), samples=samples,
                         max_drift_px=worst['drift_px'], worst_time=worst['time'],
                         passed=worst['drift_px'] <= limit))
    return dict(status=('unavailable_no_labels' if not rows else
                        'ankle_proxy_passed' if all(r['passed'] for r in rows) else 'needs_changes'),
                passed=all(r['passed'] for r in rows) if rows else None,
                intervals=rows, max_drift_px=max((r['max_drift_px'] for r in rows), default=None),
                drift_limit_px=limit, samples=len(times))


def apply(document, name, motion, times, reference_length, *, enabled=True):
    """Keep original when limits or post-correction QA fail; never amend the rig."""
    if not math.isfinite(reference_length) or reference_length <= 0:
        raise ValueError('motion_contact_reference_invalid')
    checked_times = schedule(motion, times)
    before = analyze(document, name, motion, checked_times, reference_length)
    report = dict(schema='autospine.external-motion-contact/v1', policy_id=POLICY,
                  authority='none', scope='source_label_ankle_proxy_not_sole_or_floor',
                  source_motion_sha256=_identity(motion), input_skeleton_sha256=_identity(document),
                  enabled=enabled, selected=False, before=before, after=before,
                  status=before['status'], reason_codes=[],
                  limits=dict(max_correction_ratio=MAX_CORRECTION_RATIO, drift_ratio=MAX_DRIFT_RATIO,
                              correction_speed_ratio=MAX_CORRECTION_SPEED_RATIO, release_seconds=RELEASE_SECONDS))
    if before['status'] != 'needs_changes':
        return document, report
    if not enabled:
        report['reason_codes'] = ['motion_contact_correction_disabled']
        return document, report
    candidate, evidence = root_candidate(document, name, _intervals(motion),
        reference_length=reference_length, max_ratio=MAX_CORRECTION_RATIO,
        max_residual_px=reference_length*MAX_DRIFT_RATIO, release_seconds=RELEASE_SECONDS, samples=257)
    # Keyframe correction speed protects contact entry and release from snapping.
    rows = evidence['rows']
    speed = max((math.dist(a['correction'], b['correction'])/(b['time']-a['time'])
                 for a, b in zip(rows, rows[1:]) if b['time'] > a['time']), default=0.)
    report['correction'] = dict(max_correction_px=evidence['max_correction_px'],
                              max_residual_px=evidence['max_residual_px'],
                              max_speed_px_per_second=speed, solver_status=evidence['status'])
    if candidate is None:
        report['reason_codes'] = ['motion_contact_correction_limit_or_conflict']
        return document, report
    if speed > reference_length*MAX_CORRECTION_SPEED_RATIO:
        report['reason_codes'] = ['motion_contact_transition_too_fast']
        return document, report
    final_times = schedule(motion, sorted(set(times) | {r['time'] for r in rows}))
    after = analyze(candidate, name, motion, final_times, reference_length)
    report['attempt'] = after
    if not after['passed']:
        report['reason_codes'] = ['motion_contact_residual_after_correction']
        return document, report
    report.update(selected=True, after=after, status='ankle_proxy_corrected',
                  output_skeleton_sha256=_identity(candidate))
    return candidate, report
