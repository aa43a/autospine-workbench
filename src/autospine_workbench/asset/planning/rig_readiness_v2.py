"""Authoring-role overlay for diagnostics; original plans stay immutable."""
from copy import deepcopy
from .rig_readiness import build as build_v1, _row
from ...manifest_artifacts import require_sha256


def build(plan, bindings, input_sha, plan_sha, semantics):
    result = build_v1(plan, bindings, input_sha, plan_sha)
    require_sha256(semantics['resolved_project_sha256'], 'Resolved project')
    if [r['layer_id'] for r in semantics['layers']] != plan['scope']:
        raise ValueError('rig_readiness_semantic_inventory_mismatch')
    sources = {r['layer_id']: r for r in semantics['layers']}
    bindings_by_id = {r['layer_id']: r for r in bindings['bindings']}
    plans = {r['layer_id']: r for r in plan['layers']}
    rows = []
    for original in result['layers']:
        identifier = original['layer_id']
        source = sources[identifier]
        layer = deepcopy(plans[identifier])
        if source['source'] not in ('saved_override', 'not_authored'):
            raise ValueError('rig_readiness_semantic_source_invalid')
        if source['source'] == 'saved_override':
            if not isinstance(source['role'], str) or not source['role'].strip() or source['role'] == 'unknown':
                raise ValueError('rig_readiness_semantic_source_invalid')
            layer['semantic'] = source['role']
        elif source['role'] is not None:
            raise ValueError('rig_readiness_semantic_source_invalid')
        row = _row(layer, bindings_by_id[identifier])
        row['semantic_evidence'] = deepcopy(source)
        rows.append(row)
    return dict(result, schema='autospine.rig-plan-readiness/v2',
                profile='garment-partition-readiness-v2', layers=rows,
                resolved_project_sha256=semantics['resolved_project_sha256'])
