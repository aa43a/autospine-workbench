"""Reversible root choices bound to the exact candidate report; no release rights."""
from copy import deepcopy
from ..resolved_project import canonical_sha256


def initial(roots):
    if roots['authority']!='none' or roots['production_authorized'] is not False:raise ValueError('wing_draft_source_authority')
    return {'schema':'autospine.wing-root-draft/v1','source_roots_sha256':canonical_sha256(roots),
            'records':[{'relation_index':i,'component_id':c['component_id'],'root_index':None}
                       for i,row in enumerate(roots['rows']) for c in row['components']],
            'authority':'none','production_authorized':False}


def validate(roots,doc):
    base=initial(roots)
    if doc.get('production_authorized') is not False:raise ValueError('wing_draft_source_mismatch')
    if set(doc)!=set(base) or any(doc[k]!=base[k] for k in base if k!='records'):
        raise ValueError('wing_draft_source_mismatch')
    if not isinstance(doc['records'],list) or len(doc['records'])!=len(base['records']):raise ValueError('wing_draft_inventory')
    for record,expected in zip(doc['records'],base['records']):
        if (not isinstance(record,dict) or type(record.get('relation_index')) is not int
                or type(record.get('component_id')) is not int):raise ValueError('wing_draft_inventory')
        if set(record)!=set(expected) or any(record[k]!=expected[k] for k in ('relation_index','component_id')):
            raise ValueError('wing_draft_inventory')
        index=record['root_index']; row=roots['rows'][record['relation_index']]
        component=next(c for c in row['components'] if c['component_id']==record['component_id'])
        if index is not None and (type(index) is not int or not 0<=index<len(component['roots'])):
            raise ValueError('wing_draft_unknown_root')
    return deepcopy(doc)
