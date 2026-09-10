"""Explicit hand ownership rigid target; unknown vertices never reassigned."""
from copy import deepcopy
from collections import defaultdict
import math
from ..joints.mesh_weights import _rotate,_deform
from .sleeve_helpers import frames
from .sleeve_connection_domain import prepare
from ...resolved_project import canonical_sha256


def reweight(points,weights,triangles,assignments,hand):
    if len(triangles)!=len(assignments):raise ValueError('hand_rigidity_inventory')
    roles=defaultdict(set)
    for t,a in zip(triangles,assignments):
        for i in t:roles[i].add(a['role'])
    selected=sorted(i for i,r in roles.items() if 'hand' in r and r<={'hand','cuff','sleeve','hanging_cloth'})
    result=deepcopy(weights)
    for i in selected:
        p=points[i];local=_rotate([p[k]-hand['head_xy'][k] for k in (0,1)],-hand['world_rotation_degrees'])
        result[i]=[dict(bone_id=hand['id'],weight=1.,local_xy=local)]
    return result,selected


def build(source,garment,draft,skeleton):
    domains=prepare(source,garment,draft);result=deepcopy(source)
    labels={(r['layer_id'],r['component_id']):r['assignments'] for r in draft['records']}
    bones={b['id']:b for b in skeleton['bones']}
    for row in result['records']:
        if 'helper' not in row:continue
        key=row['layer_id'],row['component_id']
        hand=bones[row['tracks'][1]['bone_id']];old_sha=canonical_sha256(row['weights'])
        row['weights'],selected=reweight(row['setup_vertices'],row['weights'],row['triangles'],labels[key],hand)
        parent=bones[hand['parent_id']];chain=[bones[parent['parent_id']],parent,hand,row['helper']]
        actual=_deform(row['weights'],frames(chain,{}))
        row['setup_error']=max(math.dist(a,b) for a,b in zip(actual,row['setup_vertices']))
        row['hand_rigidity']=dict(profile='explicit-hand-shared-boundary-rigid-v1',vertices=selected,source_weights_sha256=old_sha,
            draft_sha256=canonical_sha256(draft),authority='none')
        domains[key]['budget_policy']='one-free-area-bound-cap50-v1'
    return result,domains
