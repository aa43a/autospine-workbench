"""Exact compatibility for an additive, empty projection diagnostic extension."""
from copy import deepcopy
from ..resolved_project import canonical_sha256


def match(current, report, digest):
    if not current:
        return 'no_review'
    if current['artifact_sha256'] != report['artifact_sha256']:
        return 'artifact_changed'
    if current['evidence_sha256'] == digest:
        return 'exact'
    if report.get('profile') != 'external-motion-readiness-v1':
        return 'evidence_changed'
    legacy = deepcopy(report)
    rows = [r for r in legacy.get('stages', []) if r.get('stage') == '投影']
    defaults = {'unreliable_frames': [], 'failures': [], 'pose_profile': None}
    if len(rows) != 1 or any(key not in rows[0] or rows[0][key] != value for key, value in defaults.items()):
        return 'evidence_changed'
    # Preserve every other byte-significant field, including scope, text and checks.
    # The transformed report must match the historical human record's exact hash.
    for key in defaults:
        del rows[0][key]
    if canonical_sha256(legacy) == current['evidence_sha256']:
        return 'legacy_empty_projection_fields'
    return 'evidence_changed'
