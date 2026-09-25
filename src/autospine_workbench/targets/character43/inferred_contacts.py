"""Measure target drift against separate source hypotheses; never invent labels."""
from copy import deepcopy
from hashlib import sha256
import json

from .motion_contacts import apply
from .contact_windows import for_motion

PROFILE = 'external-inferred-contact-measurement-v1'


def measure(document, name, motion, times, reference_length, hypothesis, *, clip_bounds=None):
    if hypothesis['schema'] != 'autospine.source-contact-candidate/v1':
        raise ValueError('motion_contact_hypothesis_schema_invalid')
    probe = deepcopy(motion)
    if any(m['kind'] == 'contact' for m in motion['markers']):
        raise ValueError('motion_contact_source_labels_take_precedence')
    probe['markers'] = for_motion(motion, hypothesis, clip_bounds)
    kept, report = apply(document, name, probe, times, reference_length, enabled=False)
    report['measurement_windows_sha256'] = report['source_motion_sha256']
    # The probe only supplies measurement windows, not new MotionIR source labels.
    report.update(policy_id=PROFILE, scope='inferred_ankle_windows_not_verified_contact',
                  source_motion_sha256=sha256(json.dumps(motion, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
                  hypothesis=hypothesis, clip_bounds=clip_bounds,
                  status={'ankle_proxy_passed': 'inferred_proxy_passed',
                          'needs_changes': 'inferred_proxy_drift',
                          'insufficient_contact_samples': 'insufficient_contact_samples',
                          'unavailable_no_labels': 'inferred_support_unavailable'}[report['status']],
                  reason_codes=['inferred_contact_not_authorized_for_locking'])
    return kept, report
