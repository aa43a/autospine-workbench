"""Finite ordinary-sleeve weight hypotheses with four-track nonregression gates."""
from copy import deepcopy
from collections import Counter
import math

from .ordinary_sleeve import build as envelope, track, MOTIONS
from .component_distal_guard import gate, inventory
from .sleeve_boundary import reweight as cuff_transition
from .sleeve_hand_rigidity import reweight as hand_boundary
from .sleeve_helpers import frames
from ..joints.mesh_weights import _deform, _rotate
from ...resolved_project import canonical_sha256

SCHEMA = 'autospine.ordinary-sleeve-repair/v1'
PROFILE = 'cuff-graph64-hand-boundary-three-trials-four-track129-v1'


def _roles(mesh, assignments):
    roles = [set() for _ in mesh['vertices_xy']]
    for tri, item in zip(mesh['triangles'], assignments):
        for i in tri: roles[i].add(item['role'])
    return roles


def _rigid(mesh, assignments, chain):
    result = deepcopy(mesh)
    _, selected = hand_boundary(mesh['vertices_xy'], mesh['weights'], mesh['triangles'], assignments, chain[2])
    roles = _roles(mesh, assignments)
    # Keep the existing three-influence inventory, including zero-weight entries.
    for i in selected:
        if roles[i] == {'hand'}: continue
        p = mesh['vertices_xy'][i]
        result['weights'][i] = [dict(bone_id=b['id'], weight=1. if b['id'] == chain[2]['id'] else 0.,
            local_xy=_rotate([p[k]-b['head_xy'][k] for k in (0, 1)], -b['world_rotation_degrees'])) for b in chain]
    return result


def _score(tracks):
    return (sum(t['failed_ticks'] for t in tracks),
            sum(q['inversions'] for t in tracks for q in t['qa']),
            sum(len(q['bad_triangles']) for t in tracks for q in t['qa']),
            max(q['max_edge_stretch'] for t in tracks for q in t['qa']))


def _protected(before, trial, roles):
    """Unknown and pure hand remain exact; pure sleeve cannot gain hand influence."""
    reasons = []
    for a, b, r in zip(before['weights'], trial['weights'], roles):
        if ('unknown' in r or r == {'hand'}) and a != b:
            reasons.append('protected_vertex_changed')
        if r == {'sleeve'} and b[2]['weight'] > a[2]['weight']:
            reasons.append('sleeve_hand_influence_increased')
    return sorted(set(reasons))


def build(source, draft, skeleton):
    baseline = envelope(source, draft, skeleton)
    sources = inventory(source['records']); labels = inventory(draft['records'])
    bones = {b['id']: b for b in skeleton['bones']}; records = []
    for original in baseline['records']:
        key = original['layer_id'], original['component_id']
        record = dict(layer_id=key[0], component_id=key[1], selected=False, selected_trial=None,
                      before=deepcopy(original), trials=[], selected_row=deepcopy(original))
        records.append(record)
        if 'tracks' not in original or 'ownership_review_required' in original['reason_codes']:
            record['reason_codes'] = ['ordinary_repair_source_review_required']; continue
        if not any(t['failed_ticks'] for t in original['tracks']):
            record['reason_codes'] = ['ordinary_repair_already_passed']; continue
        mesh = sources[key]['mesh']; assignments = labels[key]['assignments']
        chain = [bones[b] for b in mesh['bone_ids']]; roles = _roles(mesh, assignments)
        counts = Counter(assignments[i]['role'] for t in original['tracks'] for q in t['qa'] for i in q['bad_triangles'])
        record['failure_role_counts'] = dict(counts)
        graph, _ = cuff_transition(mesh, assignments)
        rigid = _rigid(mesh, assignments, chain)
        combined, _ = cuff_transition(rigid, assignments)
        best = _score(original['tracks'])
        for name, trial in [('cuff_graph', graph), ('hand_shared_boundary', rigid), ('hand_boundary_cuff_graph', combined)]:
            changed = [i for i, (a, b) in enumerate(zip(mesh['weights'], trial['weights'])) if a != b]
            evidence = dict(id=name, changed_vertices=changed, selected=False, reason_codes=[])
            record['trials'].append(evidence)
            if not changed:
                evidence['reason_codes'] = ['no_weight_change']; continue
            reasons = _protected(mesh, trial, roles)
            tracks = [track(trial, chain, n, amplitudes) for n, amplitudes in MOTIONS]
            improved = False
            for old, new in zip(original['tracks'], tracks):
                rejected, gain = gate(old['qa'], new['qa']); reasons.extend(rejected); improved |= gain
            restored = _deform(trial['weights'], frames(chain, {}))
            setup_error = max(math.dist(a, b) for a, b in zip(mesh['vertices_xy'], restored))
            sum_error = max(abs(sum(w['weight'] for w in row)-1) for row in trial['weights'])
            if setup_error > 1e-7: reasons.append('setup_reconstruction_failure')
            if sum_error > 1e-9: reasons.append('weight_sum_failure')
            if any(t['loop_error'] > 1e-7 for t in tracks): reasons.append('loop_failure')
            evidence.update(reason_codes=sorted(set(reasons)) or (['sampled_improvement'] if improved else ['no_sampled_gain']),
                            tracks=tracks, setup_error=setup_error, weight_sum_error=sum_error)
            score = _score(tracks)
            if reasons or not improved or score >= best: continue
            for item in record['trials']: item['selected'] = False
            evidence['selected'] = True; best = score
            row = deepcopy(original); failed = any(t['failed_ticks'] for t in tracks)
            row.update(weights=deepcopy(trial['weights']), tracks=tracks,
                       setup_error=setup_error, weight_sum_error=sum_error,
                       status='blocked' if failed else 'candidate_requires_review',
                       reason_codes=['motion_envelope_geometry_failure'] if failed else ['runtime_and_alpha_contact_required'])
            row['motion_envelope']['geometry_pass'] = not failed
            record.update(selected=True, selected_trial=name, selected_row=row)
        record['reason_codes'] = ['bounded_candidate_improvement'] if record['selected'] else ['keep_original_weights']
    return dict(schema=SCHEMA, profile=PROFILE, project_id=source['project_id'],
                source_sha256=canonical_sha256(source), draft_sha256=canonical_sha256(draft),
                skeleton_sha256=canonical_sha256(skeleton), baseline_sha256=canonical_sha256(baseline),
                records=records, authority='none', production_authorized=False,
                runtime_status='not_evaluated', global_replacement_authorized=False)
