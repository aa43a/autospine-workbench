"""Source-qualified joint-support adoption with strict fallback."""
from copy import deepcopy
from hashlib import sha256

from ...automation.storage_io import canonical_bytes
from ...motion2d.phase_support import inspect as source_support
from .stationary_contact_policy import select as stationary_select
from .support_timeline import build
from .motion_contacts import analyze, schedule
from .affine_pose import sample
from .numeric_reference import write
from .deformation_qa import inspect

PROFILE = 'external-phase-contact-auto-v1'


def select(document, name, motion, times, reference_length, report, bvh, mapping, *,
           enabled=True, clip_bounds=None, setup_vertices=None):
    if any(m['kind'] == 'contact' for m in motion['markers']):
        raise ValueError('phase_contact_source_labels_preserved')
    kept, report = stationary_select(document, name, motion, times, reference_length, report,
                                     bvh, mapping, enabled=enabled, clip_bounds=clip_bounds)
    report = deepcopy(report); report['policy_id'] = PROFILE
    if report['selected'] or not enabled or clip_bounds is not None or report['status'] != 'inferred_proxy_drift':
        return kept, report
    support = source_support(bvh, mapping, report['hypothesis'])
    report['phase_source'] = support
    eligible = {(r['limb'], r['start_tick'], r['end_tick']) for r in support['records'] if r['eligible']}
    if not eligible:
        report['reason_codes'] = ['phase_contact_no_stable_intervals']
        return document, report
    qualified = deepcopy(motion)
    qualified['markers'] = [deepcopy(m) for m in report['hypothesis']['markers']
                             if (m['limb'], m['start_tick'], m['end_tick']) in eligible]
    if qualified['ticks_per_second'] != report['hypothesis']['ticks_per_second']:
        raise ValueError('phase_contact_tick_rate_mismatch')
    try:
        candidate, attempt = build(document, name, qualified, times, reference_length)
    except ImportError:
        report['reason_codes'] = ['phase_contact_solver_unavailable']
        return document, report
    except ValueError as exc:
        report['reason_codes'] = ['phase_contact_solver_failed']; report['phase_failure'] = str(exc)
        return document, report
    report['phase_attempt'] = attempt
    if candidate is None:
        report['reason_codes'] = ['phase_contact_timeline_limits_failed']
        return document, report
    all_windows = deepcopy(motion); all_windows['markers'] = deepcopy(report['hypothesis']['markers'])
    checked_times = schedule(all_windows, [r['time'] for r in attempt['rows']])
    report['phase_sampling'] = dict(input_samples=len(times), solver_samples=len(attempt['rows']),
                                   required_check_samples=len(checked_times), maximum_check_samples=1025,
                                   geometry_evaluated=False)
    if len(checked_times) > 1025:
        report['reason_codes'] = ['phase_contact_sample_limit']
        return document, report
    after = analyze(candidate, name, qualified, checked_times, reference_length)
    report['phase_qualified_after'] = after
    if not after['passed']:
        report['reason_codes'] = ['phase_contact_dense_drift']
        return document, report
    raw = canonical_bytes(candidate)
    files = write({'skeleton.json': raw}, dict(skeleton_sha256=sha256(raw).hexdigest(),
        animations={name: [dict(time=t, vertices=sample(candidate, name, t)[0]) for t in checked_times]}))
    geometry = inspect(files, setup_vertices=setup_vertices)
    report['phase_sampling']['geometry_evaluated'] = True
    report['phase_geometry'] = dict(passed=geometry['passed'], samples=len(checked_times))
    if not geometry['passed']:
        report['reason_codes'] = ['phase_contact_geometry_failed']
        return document, report
    # Keep before/after inventories aligned, including unqualified windows.
    all_after = analyze(candidate, name, all_windows, checked_times, reference_length)
    skipped = [r for r in support['records'] if not r['eligible']]
    report.update(selected=True, after=all_after, output_skeleton_sha256=sha256(raw).hexdigest(),
                  status='inferred_partial_corrected' if skipped else 'inferred_proxy_corrected',
                  reason_codes=['phase_contact_unqualified_intervals_preserved'] if skipped else [],
                  scope='source_qualified_ankle_intervals_not_floor_or_sole_lock', phase_checked_times=checked_times)
    return candidate, report
