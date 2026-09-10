"""Semantic cuff boundary diffusion; unknown and pure hand interiors stay pinned."""
from collections import defaultdict
from copy import deepcopy
import math
from .sleeve_connection_domain import prepare
from .sleeve_helpers import frames
from ..joints.mesh_weights import _rotate,_deform
from ...resolved_project import canonical_sha256


def reweight(points,weights,triangles,assignments,bones,include_uncuffed=False):
    if len(triangles)!=len(assignments) or len(points)!=len(weights):raise ValueError('cuff_harmonic_inventory')
    roles=defaultdict(set);neighbors=defaultdict(set)
    for tri,label in zip(triangles,assignments):
        for i in tri:roles[i].add(label['role']);neighbors[i].update(set(tri)-{i})
    # Shared hand boundary is a transition, not the interior of a rigid hand.
    free=sorted(i for i,r in roles.items() if len(r)>1 and 'hand' in r and ('cuff' in r or include_uncuffed)
        and r<={'hand','cuff','sleeve','hanging_cloth'})
    ids=[b['id'] for b in bones];lookup={b['id']:b for b in bones}
    if any(w['bone_id'] not in lookup for row in weights for w in row):raise ValueError('cuff_harmonic_bone')
    values=[{b:sum(w['weight'] for w in row if w['bone_id']==b) for b in ids} for row in weights]
    for _ in range(128):
        for i in free:
            adjacent=sorted(neighbors[i]);factors=[1/max(math.dist(points[i],points[j]),1e-9) for j in adjacent]
            total=sum(factors)
            values[i]={b:sum(f*values[j][b] for f,j in zip(factors,adjacent))/total for b in ids}
    result=deepcopy(weights)
    for i in free:
        total=sum(values[i].values());result[i]=[]
        for bid in ids:
            weight=values[i][bid]/total
            if weight<=0:continue
            b=lookup[bid];local=_rotate([points[i][k]-b['head_xy'][k] for k in (0,1)],-b['world_rotation_degrees'])
            result[i].append(dict(bone_id=bid,weight=weight,local_xy=local))
    return result,dict(profile='semantic-hand-garment-boundary-harmonic128-v1' if include_uncuffed else 'semantic-cuff-shared-hand-harmonic128-v1',vertices=free,
        pinned_vertices=sorted(set(range(len(points)))-set(free)),source_weights_sha256=canonical_sha256(weights))


def build(source,garment,draft,skeleton,include_uncuffed=False):
    domains=prepare(source,garment,draft);result=deepcopy(source)
    labels={(r['layer_id'],r['component_id']):r['assignments'] for r in draft['records']}
    bones={b['id']:b for b in skeleton['bones']}
    for row in result['records']:
        if 'helper' not in row:continue
        key=row['layer_id'],row['component_id'];hand=bones[row['tracks'][1]['bone_id']]
        parent=bones[hand['parent_id']];chain=[bones[parent['parent_id']],parent,hand,row['helper']]
        row['weights'],row['cuff_harmonic']=reweight(row['setup_vertices'],row['weights'],row['triangles'],labels[key],chain,include_uncuffed)
        row['cuff_harmonic']['draft_sha256']=canonical_sha256(draft)
        actual=_deform(row['weights'],frames(chain,{}))
        row['setup_error']=max(math.dist(a,b) for a,b in zip(actual,row['setup_vertices']))
        row['weight_sum_error']=max(abs(sum(w['weight'] for w in r)-1) for r in row['weights'])
        domains[key]['budget_policy']='one-free-area-bound-cap50-v1'
        domains[key]['weight_policy']=deepcopy(row['cuff_harmonic'])
    return result,domains
