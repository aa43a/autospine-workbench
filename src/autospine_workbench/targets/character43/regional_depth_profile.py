"""Versioned worker adapter for bounded regional depth candidates."""
from copy import deepcopy
import json

from .regional_depth_candidate import build
from .regional_depth_contract import verify

PROFILE = 'external-regional-depth-order-v1'


def partition_slots(files, document):
    """Use existing skirt-generator provenance, never a layer-name heuristic."""
    trial = json.loads(files.get('skirt-trial.json', b'{}'))
    if trial.get('profile') != 'fixed-waist-three-chain-sway-v1':
        return []
    slots = {s['name'] for s in document['slots']}
    selected = [r['layer_id'] for r in trial.get('rows', [])]
    if len(set(selected)) != len(selected) or not set(selected) <= slots:
        raise ValueError('regional_depth_skirt_inventory')
    return selected


def apply(document, files, animation, depth, bvh, mapping, *, yaw=0, on_stage=None, kimodo=None):
    selected = partition_slots(files, document)
    if bvh is None and kimodo is None:
        raise ValueError('regional_depth_source_required')
    candidate, report = build(document, files, animation, depth, bvh, mapping,
        yaw=yaw, partition_slots=selected, cloth_constraints=bool(selected), limb_constraints=True,
        torso_plane=True, rendered_bounds=True, reuse_refinement_overlap=True,
        tiled=True, pair_budgets=True, refine_cycles=True, include_depth=True, on_stage=on_stage,
        kimodo=kimodo)
    refined = report.pop('depth')
    unmeasured = sum(c['status'] == 'unmeasured' for r in report['refinement']['rows'] for c in r['checks'])
    unmeasured += sum((report.get(k) or {}).get('unmeasured_samples', 0)
                     for k in ('cloth_constraints', 'limb_constraints'))
    if unmeasured:
        candidate = None
        report['order']['status'] = 'blocked'
        report['order']['reason_codes'].append('regional_depth_unmeasured')
    report['unmeasured_samples'] = unmeasured
    # This summary is deliberately profile-specific, not legacy overlap evidence.
    refined.update(profile=PROFILE, regional=report, order=report['order'], selected=candidate is not None,
        status='depth_order_sampled_candidate' if candidate is not None else 'depth_candidates_need_review')
    transform = None
    if candidate is not None:
        transform = verify(document, candidate, animation, selected, report['order'])
    return candidate if candidate is not None else document, refined, transform


def remap_setup(vertices, partition):
    result = deepcopy(vertices)
    for row in (partition or {}).get('regions', []):
        result[row['slot']] = deepcopy(vertices[row['source_slot']])
    for name in {r['source_slot'] for r in (partition or {}).get('regions', [])}:
        del result[name]
    return result
