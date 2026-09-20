"""Versioned automatic candidate selection with source and target QA gates."""
from copy import deepcopy
from hashlib import sha256

from ...automation.storage_io import canonical_bytes
from ...motion2d.stationary_support import inspect as inspect_source
from .stationary_ankle_candidate import build
from .affine_pose import sample
from .numeric_reference import write
from .deformation_qa import inspect

LEGACY_PROFILE = 'external-stationary-contact-auto-v1'
PROFILE = 'external-stationary-contact-auto-v2'


def select(document, name, motion, times, reference_length, report, bvh, mapping, *, enabled=True, clip_bounds=None, profile=PROFILE):
    report = deepcopy(report)
    if profile not in (PROFILE, LEGACY_PROFILE):
        raise ValueError('stationary_contact_profile_unsupported')
    report['policy_id'] = profile
    report['enabled'] = enabled
    if not enabled or clip_bounds is not None or report['status'] != 'inferred_proxy_drift':
        return document, report
    source = inspect_source(bvh, mapping, report['hypothesis'])
    report['stationary_source'] = source
    if not source['eligible']:
        report['reason_codes'] = [source['reason']]
        return document, report
    probe = deepcopy(motion)
    probe['markers'] = deepcopy(report['hypothesis']['markers'])
    if probe['ticks_per_second'] != report['hypothesis']['ticks_per_second']:
        raise ValueError('stationary_contact_tick_rate_mismatch')
    candidate, evidence = build(document, name, probe, times, reference_length)
    report['stationary_attempt'] = evidence
    if candidate is None:
        report['reason_codes'] = ['stationary_target_limits_failed']
        return document, report
    checked_times = sorted(set(times) | {s['time'] for r in evidence['after']['intervals'] for s in r['samples']})
    raw = canonical_bytes(candidate)
    files = write({'skeleton.json': raw}, dict(skeleton_sha256=sha256(raw).hexdigest(),
        animations={name: [dict(time=t, vertices=sample(candidate, name, t)[0]) for t in checked_times]}))
    geometry = inspect(files)
    report['stationary_geometry'] = dict(passed=geometry['passed'], samples=len(checked_times))
    if not geometry['passed']:
        report['reason_codes'] = ['stationary_target_geometry_failed']
        return document, report
    report.update(selected=True, status='inferred_proxy_corrected', after=evidence['after'],
                  output_skeleton_sha256=sha256(raw).hexdigest(), reason_codes=[],
                  scope='source_stationary_ankle_preservation_not_floor_or_sole_lock')
    return candidate, report
