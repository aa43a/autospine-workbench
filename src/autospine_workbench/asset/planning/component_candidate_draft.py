"""Unapproved automatic suggestion drafts for repeatable cohort experiments."""
from copy import deepcopy
from .component_ownership import validate


def prefill(template,suggestions):
    if suggestions.get('sources')!=template['sources'] or suggestions.get('authority')!='none' or suggestions.get('production_authorized') is not False:
        raise ValueError('component_prefill_source_mismatch')
    rows={(r['layer_id'],r['component_id']):r for r in suggestions['records']}
    if len(rows)!=len(suggestions['records']):raise ValueError('component_prefill_duplicate')
    result=deepcopy(template)
    for row in result['records']:
        suggestion=rows.get((row['layer_id'],row['component_id']))
        if row['status']=='pending' and suggestion and suggestion['status']=='suggested':
            row.update(suggestion['proposal'])
    return validate(result,template)
