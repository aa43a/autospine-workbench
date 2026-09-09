"""Expose explicit saved authoring roles without rewriting semantic candidates."""
import re

from ..manifest_artifacts import require_sha256


def collect(project, candidate, resolved_sha256):
    require_sha256(resolved_sha256, 'Resolved project')
    overrides = project['overrides'].get('layer_overrides', {})
    rows = []
    for layer in candidate['layers']:
        identifier = layer['layer_id']
        matches = [row for row in project['layers']
                   if row['id'] == identifier or row['id'].startswith(identifier + '-')]
        if len(matches) != 1 or matches[0]['name'] != layer['name']:
            raise ValueError('planning_semantic_layer_mismatch')
        authoring_id = matches[0]['id']
        role = overrides.get(authoring_id, {}).get('canonical_role')
        if role is not None:
            if not isinstance(role, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*', role):
                raise ValueError('planning_semantic_role_invalid')
            if role == 'unknown':
                role = None
        rows.append(dict(layer_id=identifier, authoring_layer_id=authoring_id,
                         role=role, source='saved_override' if role else 'not_authored'))
    return dict(resolved_project_sha256=resolved_sha256, layers=rows)
