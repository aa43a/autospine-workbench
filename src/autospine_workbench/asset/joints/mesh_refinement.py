"""Source-bound joint-plane refinement; baseline topology and evidence stay intact."""
from copy import deepcopy
from ...resolved_project import canonical_sha256
from ...benchmark.layer_binding_draft import validate_layer_binding_draft
from .joint_plane_weights import weights_for_vertices
from .mesh_weights import evaluate_mesh


def refine_mesh_weights(baseline,skeleton,bindings,draft):
    """Caller exact-replays baseline and its full source closure before refinement."""
    validate_layer_binding_draft(bindings,draft)
    if baseline.get('schema')!='autospine.weighted-mesh-candidates/v1' or baseline.get('profile')!='alpha-grid-three-bone-v1' \
       or baseline.get('authority')!='none' or baseline.get('production_authorized') is not False \
       or baseline.get('source_bindings_sha256')!=canonical_sha256(bindings) \
       or baseline.get('source_draft_sha256')!=canonical_sha256(draft) \
       or bindings['source_skeleton_sha256']!=canonical_sha256(skeleton):
        raise ValueError('mesh_refinement_source_mismatch')
    if [r['layer_id'] for r in baseline['layers']]!=[r['layer_id'] for r in bindings['bindings']]:
        raise ValueError('mesh_refinement_layers_mismatch')
    result=deepcopy(baseline)
    result.update(schema='autospine.weighted-mesh-refinement/v1',profile='joint-plane-three-bone-v2',
                  source_mesh_sha256=canonical_sha256(baseline))
    bones={b['id']:b for b in skeleton['bones']}
    for row,binding,choice in zip(result['layers'],bindings['bindings'],draft['records']):
        if not row['vertices_xy']:continue
        selected=next((o for o in binding['options'] if o['id']==choice['option_id']),None)
        if choice['action']!='bind' or selected is None or selected['mode']!='mesh_chain' or len(selected['bone_ids'])!=3:
            raise ValueError('mesh_refinement_selection_invalid')
        chain=[bones[key] for key in selected['bone_ids']]
        try:
            weights=weights_for_vertices(row['vertices_xy'],chain)
        except ValueError as exc:
            if str(exc) not in ('joint_plane_degenerate','joint_plane_disconnected'):
                raise
            row.update(status='blocked',reason_codes=[str(exc)],weights=[],qa=None)
            continue
        qa=evaluate_mesh(row['vertices_xy'],row['triangles'],weights,chain)
        row.update(weights=weights,qa=qa,status='candidate_requires_review' if qa['passed'] else 'blocked',
                   reason_codes=['joint_plane_transition','mesh_review_required']+([] if qa['passed'] else ['mesh_deformation_qa_failed']))
    return result


def validate_mesh_refinement(baseline,skeleton,bindings,draft,document):
    expected=refine_mesh_weights(baseline,skeleton,bindings,draft)
    if canonical_sha256(document)!=canonical_sha256(expected):
        raise ValueError('mesh_refinement_mismatch')
    return expected
