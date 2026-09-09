"""Draft assignments reference exact candidate masks; no production authority."""
from copy import deepcopy

ROLES = {'unknown', 'body.arm', 'body.leg', 'body.foot', 'wear.sleeve', 'wear.skirt', 'wear.pants', 'accessory.object'}
SIDES = {'unknown', 'left', 'right', 'center', 'bilateral'}


def template(project, entries, addresses, plan_sha, bone_ids):
    records, candidates = [], []
    if len(set(bone_ids)) != len(bone_ids):
        raise ValueError('component_ownership_duplicate_bone')
    for layer, raw, candidate, digest in entries:
        candidates.append(dict(layer_id=layer['layer_id'], candidate_sha256=digest))
        for region in candidate['components'] + [candidate['residual']]:
            records.append(dict(layer_id=layer['layer_id'], component_id=region['id'],
                                status='pending', semantic='unknown', side='unknown', bone_ids=[]))
    keys = [(r['layer_id'], r['component_id']) for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError('component_ownership_duplicate_region')
    return dict(schema='autospine.component-ownership-draft/v1', project_id=project,
                authority='none', production_authorized=False,
                sources=dict(addresses=deepcopy(addresses), plan_sha256=plan_sha,
                             candidates=candidates, bone_ids=list(bone_ids)), records=records)


def validate(value, expected):
    if (type(value) is not dict or set(value) != set(expected)
            or any(value[k] != expected[k] for k in expected if k != 'records')
            or type(value['records']) is not list or len(value['records']) != len(expected['records'])):
        raise ValueError('component_ownership_source_mismatch')
    for row, original in zip(value['records'], expected['records']):
        if (type(row) is not dict or set(row) != set(original)
                or row['layer_id'] != original['layer_id'] or row['component_id'] != original['component_id']
                or row['status'] not in ('pending', 'assigned')
                or type(row['semantic']) is not str or row['semantic'] not in ROLES
                or type(row['side']) is not str or row['side'] not in SIDES
                or type(row['bone_ids']) is not list or len(row['bone_ids']) > 4
                or any(type(b) is not str for b in row['bone_ids'])
                or len(set(row['bone_ids'])) != len(row['bone_ids'])
                or not set(row['bone_ids']) <= set(expected['sources']['bone_ids'])):
            raise ValueError('component_ownership_record_invalid')
        if row['status'] == 'pending':
            if row['semantic'] != 'unknown' or row['side'] != 'unknown' or row['bone_ids']:
                raise ValueError('component_ownership_pending_invalid')
        elif (row['component_id'] == 'low-alpha-residual' or row['semantic'] == 'unknown'
              or row['side'] == 'unknown' or not row['bone_ids']):
            raise ValueError('component_ownership_assignment_invalid')
    return deepcopy(value)
