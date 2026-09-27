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
        cycle = None
        if pair is None and row.get('reason_code') == 'visible_unmapped_order_conflict':
            conflict = row.get('conflict', {})
            cycle, edges = conflict.get('slots'), conflict.get('edges')
            if (not isinstance(cycle, list) or not 3 <= len(cycle) <= len(slots)+1
                    or any(not isinstance(s, str) or s not in slots for s in cycle)
                    or cycle[0] != cycle[-1] or len(set(cycle[:-1])) != len(cycle)-1
                    or not isinstance(edges, list) or len(edges) != len(cycle)-1
                    or any(not isinstance(e, dict) or (e.get('back'),e.get('front')) != (a,b)
                           for e,a,b in zip(edges,cycle,cycle[1:]))):
                raise ValueError('motion_related_depth_failure_location')
            pair = cycle[:2]  # Compatibility location; the complete cycle is retained below.
        if pair is None and row.get('reason_code') == 'depth_overlap_pixel_budget':
            budget = row.get('raster_budget', {})
            if budget.get('time') != time:
                raise ValueError('motion_related_depth_failure_location')
            pair = budget.get('pair')
        if (type(time) not in (int, float) or not math.isfinite(time) or not 0 <= time <= duration
                or not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(s, str) or s not in slots for s in pair)
                or not isinstance(row.get('reason_code'), str)):
            raise ValueError('motion_related_depth_failure_location')
        location = dict(time=time, pair=pair, reason_code=row['reason_code'])
        if cycle is not None:location.update(location_kind='order_cycle',conflict_slots=list(cycle))
        rows.append(location)
    coverage = depth.get('target_overlap')
    if coverage is not None:
        keys = ('visible_pair_samples', 'ambiguous_visible_pair_samples',
                'order_mismatch_pair_samples', 'unmeasured_pair_samples')
        if not isinstance(coverage, dict) or any(type(coverage.get(k)) is not int or coverage[k] < 0 for k in keys):
            raise ValueError('motion_related_depth_coverage')
        coverage = {k: coverage[k] for k in keys}
    return dict(artifact_sha256=value['candidate_sha256'], audit_sha256=canonical_sha256(audit),
                status='needs_changes' if rows else 'requires_review', failures=rows, coverage=coverage,
                scope='supplemental_source_depth_and_cpu_overlap_not_full_render_acceptance',
                authority='none', selected=False)
