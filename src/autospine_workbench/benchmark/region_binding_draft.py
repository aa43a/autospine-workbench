"""Explicit reversible region-binding drafts; no default adoption or authority."""
from copy import deepcopy
import unicodedata

from ..resolved_project import canonical_sha256

SCHEMA = 'autospine.region-binding-draft/v1'
ACTIONS = ('pending', 'bind', 'requires_split', 'exclude', 'semantic_review')


def _require(condition):
    if not condition:
        raise ValueError('region_binding_draft_invalid')


def _layers(bindings):
    """Caller replays source bindings; verify the choices exposed to this draft."""
    _require(type(bindings) is dict and bindings.get('schema') == 'autospine.region-binding-candidates/v1'
             and bindings.get('authority') == 'none' and bindings.get('production_authorized') is False
             and bindings.get('status') in ('needs_review', 'blocked'))
    rows = bindings.get('bindings')
    _require(type(rows) is list and 0 < len(rows) <= 256)
    seen = set()
    for row in rows:
        _require(type(row) is dict and type(row.get('layer_id')) is str
                 and row['layer_id'] not in seen and row.get('status') in ('needs_review', 'blocked'))
        seen.add(row['layer_id'])
        options = row.get('bone_options')
        _require(type(options) is list and all(type(o) is dict and type(o.get('bone_id')) is str for o in options))
        _require(len({o['bone_id'] for o in options}) == len(options))
        _require(row['status'] != 'blocked' or not options)
        _require(bindings['status'] != 'blocked' or row['status'] == 'blocked')
    return rows


def build_binding_draft(bindings):
    rows = _layers(bindings)
    return {'schema': SCHEMA, 'authority': 'none', 'production_authorized': False,
            'source_bindings_sha256': canonical_sha256(bindings),
            'records': [{'layer_id': row['layer_id'], 'action': 'pending', 'bone_id': None, 'notes': ''} for row in rows]}


def validate_binding_draft(bindings, document):
    rows = _layers(bindings)
    _require(type(document) is dict and set(document) == {
        'schema', 'authority', 'production_authorized', 'source_bindings_sha256', 'records'})
    _require(document['schema'] == SCHEMA and document['authority'] == 'none'
             and document['production_authorized'] is False
             and document['source_bindings_sha256'] == canonical_sha256(bindings))
    records = document['records']
    _require(type(records) is list and len(records) == len(rows))
    for row, source in zip(records, rows):
        _require(type(row) is dict and set(row) == {'layer_id', 'action', 'bone_id', 'notes'}
                 and type(row['layer_id']) is str and row['layer_id'] == source['layer_id']
                 and type(row['action']) is str and row['action'] in ACTIONS)
        notes = row['notes']
        _require(type(notes) is str and len(notes) <= 2000
                 and not any(unicodedata.category(c).startswith('C') and c not in '\n\r\t' for c in notes))
        if row['action'] == 'bind':
            _require(source['status'] == 'needs_review' and type(row['bone_id']) is str
                     and row['bone_id'] in {o['bone_id'] for o in source['bone_options']})
        else:
            _require(row['bone_id'] is None)
        if row['action'] in ('requires_split', 'exclude', 'semantic_review'):
            _require(bool(notes.strip()))
    return deepcopy(document)
