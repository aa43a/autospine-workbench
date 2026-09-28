"""Create an isolated two-key order window from verified whole-frame trial evidence."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes


def compile_window(document, region, after, start, end):
    if not all(math.isfinite(t) for t in (start,end)) or not 0 <= start < end: raise ValueError('order_window_times')
    animation = document['animations']['external-motion']
    if animation.get('drawOrder'): raise ValueError('order_window_existing_order')
    slots = [s['name'] for s in document['slots']]
    if region == after or region not in slots or after not in slots: raise ValueError('order_window_slots')
    order = list(slots); order.remove(region); order.insert(order.index(after)+1, region)
    result = deepcopy(document)
    result['animations']['external-motion']['drawOrder'] = [
        dict(time=start,offsets=[dict(slot=s,offset=order.index(s)-i) for i,s in enumerate(slots)]),
        dict(time=end,offsets=[])]
    return result


def run(sequence, fixture_path, output, start, end):
    if output.exists(): raise ValueError('output_exists')
    raw = sequence.read_bytes(); trial = json.loads(raw)
    fixture_raw = fixture_path.read_bytes(); fixture = json.loads(fixture_raw)
    if (trial['fixture_sha256'] != sha256(fixture_raw).hexdigest() or not trial.get('whole_frame_trial')
            or trial.get('negative_controls') != dict(order=True,image=True)
            or [r['time'] for r in trial['rows']] != [r['time'] for r in fixture['rows']]):
        raise ValueError('order_window_evidence_identity')
    if any(r.get('reference_scope') != 'whole_frame' or r['prior_frame_max_channel_delta'] > 1
           or not r['counterfactual']['restored_full_frame'] for r in trial['rows']):
        raise ValueError('order_window_frame_unverified')
    boundaries = [next((r for r in trial['rows'] if r['time']==t),None) for t in (start,end)]
    if any(r is None or r['counterfactual']['full_frame_changed_pixels'] for r in boundaries):
        raise ValueError('order_window_boundary_not_equal')
    region = trial['rows'][0]['region']; after = trial['counterfactual']['after_slot']
    selected = [r for r in trial['rows'] if start <= r['time'] < end]
    if not selected or any(r['region'] != region for r in trial['rows']): raise ValueError('order_window_region')
    for row in selected:
        for crossed in row['counterfactual']['crossed_visibility']:
            if crossed['slot'] != after and crossed['changed_marginal_contribution_pixels']:
                raise ValueError('order_window_other_surface_regression')
    candidate = compile_window(fixture['skeleton'], region, after, start, end)
    candidate_raw = canonical_bytes(candidate)
    output.mkdir(parents=True,exist_ok=False); (output/'skeleton.json').write_bytes(candidate_raw)
    receipt = dict(source_artifact_sha256=fixture['source_artifact_sha256'],
        parent_skeleton_sha256=fixture['skeleton_sha256'],skeleton_sha256=sha256(candidate_raw).hexdigest(),
        sequence_report_sha256=sha256(raw).hexdigest(),fixture_sha256=sha256(fixture_raw).hexdigest(),
        window=dict(start=start,end=end,region=region,after_slot=after),selected=False,authority='none',
        candidate_status='diagnostic_requires_switch_capture_and_inherited_geometry_failures_remain',
        changed_source_samples=sum(r['counterfactual']['full_frame_changed_pixels']>0 for r in selected),
        original_depth_uncertainty_preserved=True,scope='order_only_window_not_geometry_or_visual_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(receipt));print(json.dumps(receipt))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('sequence','fixture','output'):p.add_argument(name,type=Path)
    p.add_argument('--start',type=float,required=True);p.add_argument('--end',type=float,required=True)
    a=p.parse_args();run(a.sequence,a.fixture,a.output,a.start,a.end)
