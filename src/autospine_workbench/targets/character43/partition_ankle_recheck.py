"""Re-measure moving ankle evidence after representation-only edits."""
from copy import deepcopy
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes


def apply(source, output, document, animation, times, evidence):
    raw = source.get('motion-moving-ankles.json')
    if raw is None:
        # Older partitions may already have lost the bound report. Do not infer
        # its identity from an embedded historical copy.
        return
    report = json.loads(raw)
    digest = sha256(source['skeleton.json']).hexdigest()
    if report.get('final_check', {}).get('skeleton_sha256') != digest:
        raise ValueError('partition_ankle_source_identity')
    from ...automation.motion_moving_ankles import check
    measured = check(document, animation, report, times, evidence['reference_length_px'])
    report = deepcopy(report)
    report['parent_final_check'] = report['final_check']
    report['final_check'] = measured
    report['representation_recheck'] = dict(source_report_sha256=sha256(raw).hexdigest(),
        source_skeleton_sha256=digest, scope='fresh_fk_on_preserved_source_trajectory')
    output['motion-moving-ankles.json'] = canonical_bytes(report)
    evidence['moving_ankles'] = report
    if not measured['passed']:
        issue = dict(stage='contact', reason_code='motion_moving_ankle_tracking_failed')
        if issue not in evidence.setdefault('issues', []):
            evidence['issues'].append(issue)
