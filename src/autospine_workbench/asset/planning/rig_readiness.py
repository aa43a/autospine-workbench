"""Source-bound next actions for garment and partition candidates, never QA."""
from ...manifest_artifacts import require_sha256
from ...resolved_project import canonical_sha256

PROFILE = 'garment-partition-readiness-v1'
KINDS = {'weighted_mesh', 'partition_mesh', 'semantic_review'}


def _row(layer, binding):
    kind = layer['strategy']
    reasons = []
    options = []
    action = 'review_semantics_and_split_need'
    evidence = layer['evidence']
    count = evidence['component_count']
    option_ids = [option['id'] for option in binding['options']]
    if len(set(option_ids)) != len(option_ids):
        raise ValueError('rig_readiness_duplicate_option')
    if type(count) is not int or count < 0:
        raise ValueError('rig_readiness_invalid_alpha_evidence')
    if not count:
        reasons.append('no_opaque_alpha_support')
    elif kind == 'semantic_review' or not (layer.get('semantic') or '').strip():
        reasons.append('garment_semantics_review_required')
    elif kind == 'partition_mesh':
        reasons.append('reviewed_partition_artifact_required')
        action = 'review_partition_ownership'
    else:
        hits = set()
        for sample in evidence['bone_alpha_samples']:
            opaque, total = sample['opaque_samples'], sample['samples']
            if type(opaque) is not int or type(total) is not int or not 0 <= opaque <= total or total < 1:
                raise ValueError('rig_readiness_invalid_alpha_evidence')
            if opaque:
                hits.add(sample['bone_id'])
        for option in binding['options']:
            bones = option['bone_ids']
            if (option['mode'] == 'mesh_chain' and 2 <= len(bones) <= 3
                    and len(set(bones)) == len(bones) and set(bones) <= hits):
                options.append(option['id'])
        if len(options) == 1 and count == 1:
            reasons.append('mesh_coverage_and_deformation_review_required')
            action = 'review_binding_and_geometry'
        elif count > 1:
            reasons.append('disconnected_alpha_ownership_review_required')
            action = 'review_partition_ownership'
        elif len(options) > 1:
            reasons.append('mesh_chain_ambiguous')
            action = 'review_binding_and_geometry'
        else:
            reasons.append('supported_mesh_chain_evidence_missing')
            action = 'review_binding_and_geometry'
    return dict(layer_id=layer['layer_id'], strategy=kind,
                status='needs_review' if reasons == ['mesh_coverage_and_deformation_review_required'] else 'blocked',
                reason_codes=reasons, next_action=action, mesh_option_ids=options)


def build(plan, bindings, input_identity_sha256, plan_sha256):
    """Inspect immutable plan evidence without mutating it or inferring approval.

    A needs_review row only identifies one supported-shape option for inspection.
    It does not assert chain topology, triangulation, weights or visual safety.
    """
    require_sha256(input_identity_sha256, 'Input identity')
    require_sha256(plan_sha256, 'Plan identity')
    if (canonical_sha256(plan) != plan_sha256
            or canonical_sha256(bindings) != plan['source_bindings_sha256']
            or plan['authority'] != 'none' or plan['production_authorized'] is not False):
        raise ValueError('rig_readiness_source_mismatch')
    ids = [row['layer_id'] for row in plan['layers']]
    if (len(set(ids)) != len(ids) or plan['scope'] != ids
            or ids != [row['layer_id'] for row in bindings['bindings']]):
        raise ValueError('rig_readiness_inventory_mismatch')
    rows = []
    for layer, binding in zip(plan['layers'], bindings['bindings']):
        if layer['image_sha256'] != binding['image_sha256']:
            raise ValueError('rig_readiness_source_mismatch')
        if layer['strategy'] in KINDS:
            rows.append(_row(layer, binding))
    return dict(schema='autospine.rig-plan-readiness/v1', profile=PROFILE,
                input_identity_sha256=input_identity_sha256, source_plan_sha256=plan_sha256,
                authority='none', production_authorized=False, layers=rows)


def validate(plan, bindings, input_identity_sha256, plan_sha256, document):
    if document != build(plan, bindings, input_identity_sha256, plan_sha256):
        raise ValueError('rig_readiness_replay_mismatch')
    return document
