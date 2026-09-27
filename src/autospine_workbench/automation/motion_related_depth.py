"""Read immutable supplemental diagnostics without rewriting historical evidence."""
import json
import math
from hashlib import sha256
from ..resolved_project import canonical_sha256


def summary(value, files):
    audit = value['receipt'].get('depth_audit')
    if audit is None:
        return None
    depth, order = audit.get('depth', {}), audit.get('order', {})
    identity = value['receipt']['source_identity']
    if (audit.get('candidate_bundle_sha256') != value['candidate_sha256']
            or audit.get('skeleton_sha256') != sha256(files['skeleton.json']).hexdigest()
            or not identity.get('raw_bvh_sha256') or not identity.get('bvh_map_sha256')
            or depth.get('source_sha256') != identity['raw_bvh_sha256']
            or depth.get('map_sha256') != identity['bvh_map_sha256']
            or depth.get('profile') != 'external-arm-torso-depth-review-v1'
            or order.get('profile') != 'external-overlap-guarded-draw-order-v1'):
        raise ValueError('motion_related_depth_identity')
    if any(x.get('authority') != 'none' or x.get('selected') is not False
           for x in (audit, depth, order)):
        raise ValueError('motion_related_depth_authority')
    slots = {s['name'] for s in json.loads(files['skeleton.json'])['slots']}
    duration = max(r['time'] for r in value['runtime']['results'])
    failures = order.get('failures')
    if not isinstance(failures, list) or len(failures) > 100000:
        raise ValueError('motion_related_depth_failures')
    rows = []
    for row in failures:
        time, pair = row.get('time'), row.get('pair')
        if (type(time) not in (int, float) or not math.isfinite(time) or not 0 <= time <= duration
                or not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(s, str) or s not in slots for s in pair)
                or not isinstance(row.get('reason_code'), str)):
            raise ValueError('motion_related_depth_failure_location')
        rows.append(dict(time=time, pair=pair, reason_code=row['reason_code']))
    return dict(artifact_sha256=value['candidate_sha256'], audit_sha256=canonical_sha256(audit),
                status='needs_changes' if rows else 'requires_review', failures=rows,
                scope='supplemental_source_depth_and_cpu_overlap_not_full_render_acceptance',
                authority='none', selected=False)
