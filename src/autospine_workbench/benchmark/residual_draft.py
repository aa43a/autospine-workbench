"""Editable residual policy choices carry no binding or production authority."""
from copy import deepcopy
import unicodedata
from ..resolved_project import canonical_sha256


def build_draft(partitions):
    return {'schema':'autospine.residual-draft/v1','authority':'none','production_authorized':False,
            'source_partitions_sha256':canonical_sha256(partitions),
            'records':[{'layer_id':r['layer_id'],'policy':'pending','notes':''} for r in partitions['layers']]}


def validate_draft(partitions,document):
    base=build_draft(partitions)
    if type(document) is not dict or set(document)!=set(base) or \
            any(type(document[k]) is not type(base[k]) or document[k]!=base[k] for k in base if k!='records') or \
            type(document['records']) is not list or len(document['records'])!=len(base['records']):
        raise ValueError('residual_draft_invalid')
    for row,expected in zip(document['records'],base['records']):
        if type(row) is not dict or set(row)!=set(expected) or row['layer_id']!=expected['layer_id'] or \
                type(row['policy']) is not str or row['policy'] not in ('pending','retain','nearest_4px') or \
                type(row['notes']) is not str or len(row['notes'])>2000 or \
                any(unicodedata.category(c).startswith('C') and c not in '\n\r\t' for c in row['notes']) or \
                (row['policy']!='pending' and not row['notes'].strip()):
            raise ValueError('residual_draft_invalid')
    return deepcopy(document)
