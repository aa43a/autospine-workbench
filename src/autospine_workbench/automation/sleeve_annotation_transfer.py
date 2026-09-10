"""Conservative reuse of source-space labels; never reuse motion approval."""
from collections import Counter
from copy import deepcopy

from ..asset.planning.sleeve_regions import template, validate
from ..resolved_project import canonical_sha256


def _keys(candidate):
    for row in candidate['records']:
        for tri in row['triangles']:
            # Exact directed winding, coordinates, source pixels and arm identity.
            # No nearest-neighbour mapping or index-only matches.
            points = [tuple(row['vertices_xy'][v]) for v in tri]
            winding = min(tuple(points[i:] + points[:i]) for i in range(3))
            yield (row['layer_id'], row['component_id'], row['source_image_sha256'],
                   tuple(row['bone_ids']), winding)


def transfer(previous_candidate, previous_draft, candidate):
    validate(previous_draft, previous_candidate)
    if previous_candidate['project_id'] != candidate['project_id']:
        raise ValueError('sleeve_transfer_project_mismatch')
    result = template(candidate)
    old_keys, new_keys = list(_keys(previous_candidate)), list(_keys(candidate))
    old_counts, new_counts = Counter(old_keys), Counter(new_keys)
    old_items = [a for r in previous_draft['records'] for a in r['assignments']]
    old = {key: item for key, item in zip(old_keys, old_items) if old_counts[key] == 1}
    suggestions = [s for r in candidate['records'] for s in r['suggestions']]
    items = [a for r in result['records'] for a in r['assignments']]
    counts = dict(manual_count=0, geometry_count=0, pending_count=0)
    for key, item, suggestion in zip(new_keys, items, suggestions):
        prior = old.get(key) if new_counts[key] == 1 else None
        if prior and prior['origin'] == 'manual_edit':
            item.update(role=prior['role'], origin='manual_edit')
            counts['manual_count'] += 1
        elif (prior and prior['origin'] == 'geometry_prefill'
              and prior['role'] == suggestion['suggested_role']):
            item.update(role=prior['role'], origin='geometry_prefill')
            counts['geometry_count'] += 1
        else:
            counts['pending_count'] += 1
    validate(result, candidate)
    receipt = dict(schema='autospine.sleeve-annotation-transfer/v1',
                   profile='exact-source-triangle-v1', authority='none', production_authorized=False, requires_save=True,
                   previous_candidate_sha256=canonical_sha256(previous_candidate),
                   previous_draft_sha256=canonical_sha256(previous_draft),
                   candidate_sha256=canonical_sha256(candidate), draft_sha256=canonical_sha256(result),
                   **counts)
    return deepcopy(result), receipt


def check(receipt, previous_candidate, previous_draft, candidate):
    draft, expected = transfer(previous_candidate, previous_draft, candidate)
    if receipt != expected:
        raise ValueError('sleeve_transfer_receipt_invalid')
    return draft


def summary(receipt):
    return {k: receipt[k] for k in ('manual_count', 'geometry_count', 'pending_count',
                                   'authority', 'requires_save')}
