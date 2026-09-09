"""Conservative sleeve-interior influence candidates from exact supplied drafts."""
from copy import deepcopy
from collections import Counter
from .sleeve_regions import build as regions, validate
from .component_distal_guard import inventory, gate
from .component_mesh_tracks import tracks
from .component_axial_correction import evaluate as dense
from ..joints.partition_mesh_qa import evaluate
from ...resolved_project import canonical_sha256


def reweight(mesh, assignments):
    if len(assignments) != len(mesh['triangles']): raise ValueError('sleeve_weight_inventory')
    incident = [set() for _ in mesh['vertices_xy']]
    for triangle, item in zip(mesh['triangles'], assignments):
        for vertex in triangle: incident[vertex].add(item['role'])
    result = deepcopy(mesh); changed = []; boundary = []; changed_roles = Counter()
    for i, roles in enumerate(incident):
        if len(roles) > 1: boundary.append(i)
        if roles not in ({'sleeve'}, {'hanging_cloth'}): continue
        row = result['weights'][i]
        if [w['bone_id'] for w in row] != mesh['bone_ids']: raise ValueError('sleeve_weight_order')
        if row[2]['weight'] > 0:
            row[1]['weight'] += row[2]['weight']; row[2]['weight'] = 0.; changed.append(i)
            changed_roles[next(iter(roles))] += 1
    return result, dict(changed_vertices=changed, mixed_boundary_vertices=boundary,
                        role_triangle_counts=dict(Counter(a['role'] for a in assignments)),
                        vertex_roles=[sorted(r) for r in incident], changed_role_counts=dict(changed_roles))


def build(source, candidate, draft, skeleton):
    if candidate != regions(source, skeleton): raise ValueError('sleeve_weight_candidate_mismatch')
    draft = validate(draft, candidate); labels = inventory(draft['records'])
    rows = deepcopy(source['records']); evidence = []; bones = {b['id']:b for b in skeleton['bones']}
    for row in rows:
        key = row['layer_id'], row['component_id']
        if key not in labels: continue
        before = row['mesh']; trial, info = reweight(before, labels[key]['assignments'])
        chain = [bones[b] for b in trial['bone_ids']]
        trial['qa'] = evaluate(trial['vertices_xy'], trial['triangles'], trial['weights'], chain)
        # Source corrections refer to old weights. Compare fresh raw FK on both sides.
        comparisons = []
        for oldtrack, newtrack in zip(tracks(before,skeleton), tracks(trial,skeleton)):
            oldqa, newqa = dense(before,chain,oldtrack), dense(trial,chain,newtrack)
            reasons, improved = gate(oldqa,newqa)
            comparisons.append(dict(bone_id=oldtrack['bone_id'], before=oldqa, after=newqa,
                                    regression_reasons=reasons, sampled_improvement=improved))
        reasons = ['garment_weight_candidate_not_adopted']
        counts = info['role_triangle_counts']
        if info['mixed_boundary_vertices']: reasons.append('semantic_boundary_transition_required')
        for role, reason in [('cuff','cuff_contact_constraint_required'),('hanging_cloth','cloth_helper_chain_required'),('unknown','ownership_review_required')]:
            if counts.get(role): reasons.append(reason)
        if any(c['regression_reasons'] for c in comparisons): reasons.append('dense_fk_regression')
        if not trial['qa']['passed']: reasons.append('partition_deformation_qa_failed')
        trial.update(status='blocked',reason_codes=reasons)
        row.update(mesh=trial,status='blocked',reason_codes=reasons)
        evidence.append(dict(layer_id=key[0],component_id=key[1],**info,comparisons=comparisons,reason_codes=reasons))
    return dict(schema='autospine.sleeve-weights/v1',profile='unanimous-garment-interior-hand-zero-v1',
                project_id=source['project_id'],source_sha256=canonical_sha256(source),candidate_sha256=canonical_sha256(candidate),
                draft_sha256=canonical_sha256(draft),skeleton_sha256=canonical_sha256(skeleton),records=rows,evidence=evidence,
                authority='none',production_authorized=False,corrective_status='not_reused',runtime_status='not_evaluated')
