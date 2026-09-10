"""Conditional candidate selection; reviewed ownership is evidence, never approval."""
from copy import deepcopy
import math
from .component_distal_guard import gate, inventory
from .component_temporal_qa import passed
from ...resolved_project import canonical_sha256

PROFILE = 'conditional-hand-repair-v1'


def eligible(row, assignments):
    """Only hand-owned failed triangles justify changing protected hand weights."""
    if not row.get('tracks'):return False
    if len(assignments) != len(row['triangles']):
        raise ValueError('sleeve_policy_inventory')
    bad = {i for t in row.get('tracks', []) for q in t['qa'] for i in q['bad_triangles']}
    return any(assignments[i]['role'] == 'hand' for i in bad)


def select(baseline, trial, eligible_keys):
    for document in (baseline, trial):
        if document.get('authority') != 'none' or document.get('production_authorized') is not False:
            raise ValueError('sleeve_policy_authority')
    for key in ('schema', 'project_id', 'skeleton_sha256'):
        if baseline[key] != trial[key]:
            raise ValueError('sleeve_policy_source')
    old, new = inventory(baseline['records']), inventory(trial['records'])
    if old.keys() != new.keys():
        raise ValueError('sleeve_policy_inventory')
    result = deepcopy(baseline); evidence = []; selected = []
    for key, before in old.items():
        after = new[key]
        for field in ('triangles', 'setup_vertices', 'helper'):
            if before.get(field) != after.get(field):
                raise ValueError('sleeve_policy_geometry')
        reasons = []; gain = False
        if key in eligible_keys:
            a, b = before['tracks'], after['tracks']
            if len(a) != 7 or len(b) != 7:
                raise ValueError('sleeve_policy_tracks')
            for left, right in zip(a, b):
                if any(left[f] != right[f] for f in ('bone_id', 'amplitudes', 'drivers')):
                    raise ValueError('sleeve_policy_tracks')
                rejected, improved = gate(left['qa'], right['qa'])
                reasons.extend(rejected); gain |= improved
                if not all(passed(q) for q in right['qa']):reasons.append('hand_trial_incomplete')
                if any(not math.isfinite(right[f]) or right[f] > 1e-7 for f in ('anchor_displacement', 'loop_error')):
                    reasons.append('hand_trial_connection_failure')
            if not after['setup_error'] <= 1e-7 or not after['weight_sum_error'] <= 1e-9:
                reasons.append('hand_trial_setup_failure')
        keep = key in eligible_keys and gain and not reasons
        selected.append(deepcopy(after if keep else before))
        evidence.append(dict(layer_id=key[0], component_id=key[1], selected=keep,
            reason_codes=sorted(set(reasons)) or ['sampled_improvement' if keep else 'baseline_retained']))
    if not any(r['selected'] for r in evidence):return deepcopy(baseline), evidence
    result.update(profile=PROFILE, source_sha256=canonical_sha256(baseline), records=selected)
    # Per-selected-row provenance leaves unselected rows byte-identical.
    for row, decision in zip(result['records'], evidence):
        if decision['selected']:
            row['repair_policy'] = dict(profile=PROFILE, baseline_sha256=canonical_sha256(baseline),
                trial_sha256=canonical_sha256(trial), authority='none')
    return result, evidence
