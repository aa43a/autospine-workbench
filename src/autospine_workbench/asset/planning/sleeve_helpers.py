"""Branched cloth helper hypotheses with real parent-based FK, no runtime claim."""
from copy import deepcopy
import math
from .component_distal_guard import inventory
from .component_local_solver import metrics
from .component_temporal_qa import passed
from ..joints.mesh_weights import _rotate, _deform
from ...resolved_project import canonical_sha256


def frames(bones, angles):
    lookup={b['id']:b for b in bones};result={}
    if len(lookup)!=len(bones):raise ValueError('cloth_duplicate_bone')
    if not set(angles)<=set(lookup):raise ValueError('cloth_unknown_driver')
    for bone in bones:
        parent=bone['parent_id'];delta=angles.get(bone['id'],0.)
        if not math.isfinite(delta):raise ValueError('cloth_nonfinite_angle')
        if parent in lookup:
            if parent not in result:raise ValueError('cloth_parent_order')
            p=lookup[parent];head,rotation=result[parent]
            local=_rotate([bone['head_xy'][k]-p['head_xy'][k] for k in (0,1)],-p['world_rotation_degrees'])
            offset=_rotate(local,rotation)
            result[bone['id']]=([head[k]+offset[k] for k in (0,1)],rotation+bone['world_rotation_degrees']-p['world_rotation_degrees']+delta)
        else:result[bone['id']]=(bone['head_xy'][:],bone['world_rotation_degrees']+delta)
    return result


def make_helper(mesh, chain, vertex_roles, identifier):
    vertices=[i for i,r in enumerate(vertex_roles) if r==['hanging_cloth']]
    if not vertices:return None
    root=chain[2]['head_xy'][:]
    tip=[sum(mesh['vertices_xy'][i][k] for i in vertices)/len(vertices) for k in (0,1)]
    if math.dist(root,tip)<1e-6:return None
    rotation=math.degrees(math.atan2(tip[1]-root[1],tip[0]-root[0]))
    parent=chain[1]
    helper=dict(id=identifier,parent_id=parent['id'],head_xy=root,tail_xy=tip,length=math.dist(root,tip),
        world_rotation_degrees=rotation,setup_local=dict(rotation_degrees=rotation-parent['world_rotation_degrees'],
        translation_xy=_rotate([root[k]-parent['head_xy'][k] for k in (0,1)],-parent['world_rotation_degrees'])),
        provenance=dict(kind='candidate',reason='cloth_centroid_direction_wrist_root',reviewed=False))
    weights=deepcopy(mesh['weights'])
    for i in vertices:
        row=weights[i];downstream=sum(w['weight'] for w in row if w['bone_id'] in (chain[1]['id'],chain[2]['id']))
        weights[i]=[w for w in row if w['bone_id'] not in (chain[1]['id'],chain[2]['id'])]
        weights[i].append(dict(bone_id=identifier,weight=downstream,
            local_xy=_rotate([mesh['vertices_xy'][i][k]-root[k] for k in (0,1)],-rotation)))
    return helper,weights,vertices


def build(source,skeleton,root_transition=False):
    if (source['schema']!='autospine.sleeve-weights/v1' or source['skeleton_sha256']!=canonical_sha256(skeleton)
            or source.get('authority')!='none' or source.get('production_authorized') is not False):raise ValueError('cloth_source_mismatch')
    bones={b['id']:b for b in skeleton['bones']};lookup=inventory(source['evidence']);rows=[]
    for row in source['records']:
        key=row['layer_id'],row['component_id']
        if key not in lookup:continue
        mesh=row['mesh'];chain=[bones[b] for b in mesh['bone_ids']]
        made=make_helper(mesh,chain,lookup[key]['vertex_roles'],'cloth-'+key[0]+'-'+key[1])
        if made is None:
            rows.append(dict(layer_id=key[0],component_id=key[1],status='blocked',reason_codes=['cloth_helper_unobservable']));continue
        helper,weights,vertices=made
        baseline_weights=deepcopy(weights);transition_info=None
        if root_transition:
            from .cloth_root_transition import reweight
            weights,transition_info=reweight(mesh,chain,helper,vertices)
        if helper['id'] in bones:raise ValueError('cloth_helper_id_collision')
        extended=chain+[helper];restored=_deform(weights,frames(extended,{}))
        error=max(math.dist(a,b) for a,b in zip(mesh['vertices_xy'],restored))
        sums=max(abs(sum(w['weight'] for w in row)-1) for row in weights)
        hand_probe=_deform(weights,frames(extended,{chain[2]['id']:90.}))
        isolation=max(math.dist(restored[i],hand_probe[i]) for i in vertices)
        tracks=[];baseline_tracks=[];regressions=[];improved=False
        for driver,limit in [(chain[1]['id'],30.),(chain[2]['id'],90.),(helper['id'],15.)]:
            qa=[];samples=[];oldqa=[];oldsamples=[]
            for tick in range(129):
                angle=-limit+2*limit*tick/128
                transforms=frames(extended,{driver:angle});points=_deform(weights,transforms)
                qa.append(metrics(mesh['vertices_xy'],points,mesh['triangles']))
                if root_transition:
                    oldpoints=_deform(baseline_weights,transforms)
                    oldqa.append(metrics(mesh['vertices_xy'],oldpoints,mesh['triangles']))
                if tick%4==0:samples.append(dict(angle=angle,points=points,bones=[dict(id=b['id'],head_xy=transforms[b['id']][0],
                    tail_xy=[transforms[b['id']][0][k]+_rotate([math.dist(b['head_xy'],b['tail_xy']),0],transforms[b['id']][1])[k] for k in (0,1)]) for b in extended]))
                if root_transition and tick%4==0:oldsamples.append(dict(samples[-1],points=oldpoints))
            tracks.append(dict(bone_id=driver,angle_range=[-limit,limit],qa=qa,samples=samples,failed_ticks=sum(not passed(q) for q in qa)))
            if root_transition:
                from .component_distal_guard import gate
                rejected,gain=gate(oldqa,qa);regressions.extend(rejected);improved |= gain
                baseline_tracks.append(dict(bone_id=driver,angle_range=[-limit,limit],qa=oldqa,samples=oldsamples,failed_ticks=sum(not passed(q) for q in oldqa)))
        if root_transition:
            selected=not regressions and improved and not transition_info['unreachable_vertices']
            transition_info.update(selected=selected,reason_codes=sorted(set(regressions)) or (['sampled_improvement'] if selected else ['no_gain_or_disconnected_root']),
                baseline_failed_ticks=[t['failed_ticks'] for t in baseline_tracks],trial_failed_ticks=[t['failed_ticks'] for t in tracks],
                trial_qa=[dict(bone_id=t['bone_id'],qa=t['qa']) for t in tracks])
            if not selected:weights=baseline_weights;tracks=baseline_tracks
            restored=_deform(weights,frames(extended,{}))
            error=max(math.dist(a,b) for a,b in zip(mesh['vertices_xy'],restored))
            sums=max(abs(sum(w['weight'] for w in row)-1) for row in weights)
            hand_probe=_deform(weights,frames(extended,{chain[2]['id']:90.}))
            isolation=max(math.dist(restored[i],hand_probe[i]) for i in vertices)
        rows.append(dict(layer_id=key[0],component_id=key[1],status='blocked',reason_codes=['cloth_helper_candidate_not_adopted','cuff_boundary_constraint_required','secondary_motion_not_baked'],
            helper=helper,weights=weights,cloth_vertices=vertices,triangles=mesh['triangles'],setup_vertices=mesh['vertices_xy'],
            setup_error=error,weight_sum_error=sums,hand_isolation_max_error=isolation,tracks=tracks))
        if root_transition:rows[-1]['root_transition']=transition_info
    return dict(schema='autospine.sleeve-helper/v1',profile=('forearm-child-geodesic-root-v1' if root_transition else 'forearm-child-cloth-helper-v1'),project_id=source['project_id'],
        source_sha256=canonical_sha256(source),skeleton_sha256=canonical_sha256(skeleton),records=rows,
        authority='none',production_authorized=False,runtime_status='not_evaluated')
