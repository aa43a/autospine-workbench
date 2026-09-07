"""Reversible option selections, kept separate from weights and production rights."""
from copy import deepcopy
import unicodedata

from ..resolved_project import canonical_sha256

SCHEMA = 'autospine.layer-binding-draft/v2'
ACTIONS = ('pending', 'bind', 'requires_split', 'exclude', 'semantic_review')


def _require(condition):
    if not condition:
        raise ValueError('layer_binding_draft_invalid')


def _token(value):
    return type(value) is str and 0 < len(value) <= 200 and value == value.strip() \
        and not any(unicodedata.category(c).startswith('C') for c in value)


def _layers(bindings):
    """Caller replays source closure; this boundary checks selectable options."""
    _require(type(bindings) is dict and bindings.get('schema') == 'autospine.layer-binding-candidates/v2'
             and bindings.get('authority') == 'none' and bindings.get('production_authorized') is False
             and bindings.get('status') in ('needs_review', 'blocked'))
    rows = bindings.get('bindings')
    _require(type(rows) is list and 0 < len(rows) <= 256)
    seen = set()
    for row in rows:
        _require(type(row) is dict and _token(row.get('layer_id')) and row['layer_id'] not in seen
                 and row.get('status') in ('needs_review', 'blocked'))
        seen.add(row['layer_id'])
        options = row.get('options')
        _require(type(options) is list and len(options) <= 256)
        option_ids = set()
        for option in options:
            _require(type(option) is dict and _token(option.get('id')) and option['id'] not in option_ids
                     and option.get('mode') in ('rigid', 'mesh_chain'))
            option_ids.add(option['id'])
            bones = option.get('bone_ids')
            _require(type(bones) is list and 1 <= len(bones) <= 256 and all(_token(b) for b in bones)
                     and len(set(bones)) == len(bones))
            _require(len(bones) == 1 if option['mode'] == 'rigid' else len(bones) >= 2)
        _require(row['status'] != 'blocked' or not options)
        _require(bindings['status'] != 'blocked' or row['status'] == 'blocked')
    return rows


def build_layer_binding_draft(bindings):
    rows = _layers(bindings)
    return {'schema': SCHEMA, 'authority': 'none', 'production_authorized': False,
            'source_bindings_sha256': canonical_sha256(bindings),
            'records': [{'layer_id': row['layer_id'], 'action': 'pending', 'option_id': None, 'notes': ''}
                        for row in rows]}


def validate_layer_binding_draft(bindings, document):
    rows = _layers(bindings)
    _require(type(document) is dict and set(document) == {
        'schema', 'authority', 'production_authorized', 'source_bindings_sha256', 'records'})
    _require(document['schema'] == SCHEMA and document['authority'] == 'none'
             and document['production_authorized'] is False
             and document['source_bindings_sha256'] == canonical_sha256(bindings))
    records = document['records']
    _require(type(records) is list and len(records) == len(rows))
    for row, source in zip(records, rows):
        _require(type(row) is dict and set(row) == {'layer_id', 'action', 'option_id', 'notes'}
                 and type(row['layer_id']) is str and row['layer_id'] == source['layer_id']
                 and type(row['action']) is str and row['action'] in ACTIONS)
        notes = row['notes']
        _require(type(notes) is str and len(notes) <= 2000
                 and not any(unicodedata.category(c).startswith('C') and c not in '\n\r\t' for c in notes))
        if row['action'] == 'bind':
            _require(source['status'] == 'needs_review' and type(row['option_id']) is str
                     and row['option_id'] in {option['id'] for option in source['options']})
        else:
            _require(row['option_id'] is None)
        if row['action'] in ('requires_split', 'exclude', 'semantic_review'):
            _require(bool(notes.strip()))
    return deepcopy(document)
