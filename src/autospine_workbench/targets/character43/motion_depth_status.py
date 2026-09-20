"""Read-only operator diagnostics; does not change stage-review evidence."""
from collections import Counter
from hashlib import sha256
import json
import math

RESOURCE={'depth_overlap_pixel_budget','depth_overlap_tile_limit','depth_overlap_frame_limit'}
CONFLICT={'visible_depth_straddle','visible_unmapped_order_conflict'}


def build(files,artifact):
    digest=sha256(files['skeleton.json']).hexdigest()
    depth=json.loads(files.get('motion-depth.json',b'{}'))
    if depth and depth.get('skeleton_sha256')!=digest:
        raise ValueError('motion_depth_status_identity')
    order=depth.get('order',{}); rows=[]; counts=Counter()
    for failure in order.get('failures',[]):
        reason=failure.get('reason_code','unknown')
        category=('resource_limit' if reason in RESOURCE else
                  'depth_conflict' if reason in CONFLICT else 'unsupported_check')
        counts[category]+=1
        time=failure.get('time')
        if not isinstance(time,(int,float)) or not math.isfinite(time) or time<0:
            raise ValueError('motion_depth_status_time')
        row=dict(time=time,reason_code=reason,category=category)
        if failure.get('pair'): row['pair']=failure['pair']
        if failure.get('raster_budget'): row['raster_budget']=failure['raster_budget']
        rows.append(row)
    overlap=depth.get('target_overlap',{})
    unmeasured=overlap.get('unmeasured_pair_samples')
    ambiguous=overlap.get('ambiguous_visible_pair_samples',0)
    conflict=bool(counts['depth_conflict'] or ambiguous)
    incomplete=bool(counts['resource_limit'] or counts['unsupported_check'] or unmeasured is None or unmeasured)
    passed=(not conflict and not incomplete and (order.get('status')=='no_visible_order_change' or
        order.get('status')=='candidate' and depth.get('selected') is True))
    state=('needs_changes' if conflict else 'evidence_incomplete' if incomplete else
           'sampled_candidate' if passed and depth.get('selected') else 'sampled_no_change' if passed else 'not_evaluated')
    return dict(profile='external-motion-depth-operator-status-v1',artifact_sha256=artifact,
        skeleton_sha256=digest,status=state,selected=depth.get('selected') is True,
        failure_record_counts=dict(counts),failure_records=len(rows),records=rows[:100],
        records_truncated=len(rows)>100,unmeasured_pair_samples=unmeasured,
        ambiguous_visible_pair_samples=ambiguous,has_incomplete_checks=incomplete,
        authority='none',production_authorized=False,
        scope='diagnostic_records_not_error_rate_or_visual_acceptance')
