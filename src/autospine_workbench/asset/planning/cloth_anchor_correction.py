"""Cloth-only corrective keys, tested between keys against actual branching FK."""
from copy import deepcopy
import math
from .cloth_anchor_solver import solve
from .sleeve_helpers import frames
from .component_local_solver import metrics
from .component_distal_guard import gate
from .component_temporal_qa import passed
from ..joints.mesh_weights import _deform
from ...resolved_project import canonical_sha256


def interpolate(keys,tick):
    left=min(tick//4,31);fraction=(tick-left*4)/4
    return [[a[k]*(1-fraction)+b[k]*fraction for k in (0,1)] for a,b in zip(keys[left],keys[left+1])]


def build(source,skeleton):
    if (source.get('schema')!='autospine.sleeve-interface-root/v1'
            or source.get('skeleton_sha256')!=canonical_sha256(skeleton)
            or source.get('authority')!='none' or source.get('production_authorized') is not False):
        raise ValueError('cloth_anchor_source_mismatch')
    rows=deepcopy(source['records']);bones={b['id']:b for b in skeleton['bones']}
    for row in rows:
        if 'helper' not in row:continue
        anchors=sorted({i for e in row['interface_root']['edges'] for i in e})
        if not anchors:
            row['anchor_correction']=dict(selected=False,reason_codes=['missing_interface']);continue
        parent=bones[row['helper']['parent_id']];upper=bones[parent['parent_id']]
        hand=bones[row['tracks'][1]['bone_id']];chain=[upper,parent,hand,row['helper']]
        budget=.15*math.dist(parent['head_xy'],parent['tail_xy']);newtracks=[];reasons=[];gain=False;offsets=[]
        for old in row['tracks']:
            keys=[]
            for frame in old['samples']:
                result,_=solve(row['setup_vertices'],row['triangles'],frame['points'],row['cloth_vertices'],anchors,budget)
                keys.append([[q[k]-p[k] for k in (0,1)] for p,q in zip(frame['points'],result)])
            qa=[];samples=[];low,high=old['angle_range']
            for tick in range(129):
                angle=low+(high-low)*tick/128
                base=_deform(row['weights'],frames(chain,{old['bone_id']:angle}));delta=interpolate(keys,tick)
                points=[[p[k]+d[k] for k in (0,1)] for p,d in zip(base,delta)]
                qa.append(metrics(row['setup_vertices'],points,row['triangles']))
                if tick%4==0:samples.append(dict(old['samples'][tick//4],points=points))
            rejected,improved=gate(old['qa'],qa);reasons.extend(rejected);gain|=improved
            newtracks.append(dict(old,qa=qa,samples=samples,failed_ticks=sum(not passed(q) for q in qa)))
            offsets.append(dict(bone_id=old['bone_id'],keys=keys))
        selected=not reasons and gain
        row['anchor_correction']=dict(selected=selected,reason_codes=sorted(set(reasons)) or ['sampled_improvement' if selected else 'no_sampled_gain'],
            anchors=anchors,budget_px=budget,baseline_failed_ticks=[t['failed_ticks'] for t in row['tracks']],
            trial_failed_ticks=[t['failed_ticks'] for t in newtracks],trial_qa=[dict(bone_id=t['bone_id'],qa=t['qa']) for t in newtracks],
            trial_offsets=offsets,coordinate_space='canvas_world_delta',interpolation='linear_offset_over_branch_fk')
        if selected:row['tracks']=newtracks
    return dict(schema='autospine.cloth-anchor-correction/v1',profile='cloth-only-pbd48-guard129-v1',
        project_id=source['project_id'],source_sha256=canonical_sha256(source),skeleton_sha256=canonical_sha256(skeleton),
        records=rows,authority='none',production_authorized=False,runtime_status='not_evaluated')
