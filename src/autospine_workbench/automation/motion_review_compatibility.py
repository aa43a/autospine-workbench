"""Exact compatibility for known additive, empty diagnostic extensions."""
from copy import deepcopy
from itertools import combinations
from ..resolved_project import canonical_sha256

COMPATIBLE_MATCHES = ('exact', 'legacy_empty_projection_fields', 'legacy_empty_diagnostic_fields')


def match(current, report, digest):
    if not current:
        return 'no_review'
    if current['artifact_sha256'] != report['artifact_sha256']:
        return 'artifact_changed'
    if current['evidence_sha256'] == digest:
        return 'exact'
    if report.get('profile') != 'external-motion-readiness-v1':
        return 'evidence_changed'
    extensions = []
    for stage, defaults in (
            ('投影', {'unreliable_frames': [], 'failures': [], 'pose_profile': None}),
            ('几何', {'repair_limits': []})):
        rows = [(i, r) for i, r in enumerate(report.get('stages', [])) if r.get('stage') == stage]
        if len(rows) == 1 and all(key in rows[0][1] and rows[0][1][key] == value
                                  for key, value in defaults.items()):
            extensions.append((rows[0][0], defaults, stage))
    # Try only known schema additions, separately or together. Preserve all
    # other fields (including text, failures, scope and Runtime sample counts).
    # A full historical digest match is required; no acceptance record is edited.
    for count in range(1, len(extensions) + 1):
        for subset in combinations(extensions, count):
            legacy = deepcopy(report)
            for index, defaults, _stage in subset:
                for key in defaults:
                    del legacy['stages'][index][key]
            if canonical_sha256(legacy) == current['evidence_sha256']:
                return ('legacy_empty_projection_fields' if count == 1 and subset[0][2] == '投影'
                        else 'legacy_empty_diagnostic_fields')
    return 'evidence_changed'
