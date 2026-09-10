"""Explicit world-to-influence deform conversion for R3-S diagnostic meshes."""
from copy import deepcopy
import math
from ...asset.planning.sleeve_helpers import frames
from ...asset.planning.sleeve_motion_envelope import angles
from ...asset.planning.component_local_solver import metrics
from ...asset.planning.component_temporal_qa import passed
from ...asset.joints.mesh_weights import _rotate,_deform
from ...resolved_project import canonical_sha256
from .continuous_pose import world


def offset_at(track,tick,count):
    if not track['correction_selected']:return [[0.,0.] for _ in range(count)]
    left=min(int(tick//4),31);f=(tick-left*4)/4;keys=track['trial_keys']
    return [[a[k]*(1-f)+b[k]*f for k in (0,1)] for a,b in zip(keys[left],keys[left+1])]


def local_offsets(weights,delta,transforms):
    """Each influence receives the inverse-rotated world delta; weights sum to one."""
    result=[]
    for entries,d in zip(weights,delta):
        for entry in entries:
            x,y=_rotate(d,-transforms[entry['bone_id']][1]);result.extend([x,-y])
    return result


def compile_region(source,row,mesh,skeleton):
    if (source.get('schema')!='autospine.sleeve-motion-envelope/v1'
            or source.get('skeleton_sha256')!=canonical_sha256(skeleton)
            or source.get('authority')!='none' or source.get('production_authorized') is not False
            or row not in source['records'] or mesh['vertices_xy']!=row['setup_vertices'] or mesh['triangles']!=row['triangles']):
        raise ValueError('sleeve_target_source_mismatch')
    if any(t['failed_ticks'] for t in row['tracks']):raise ValueError('sleeve_target_geometry_blocked')
    bones=[]
    for bone in skeleton['bones']:
        local=bone['setup_local'];item=dict(name=bone['id'],x=local['x'],y=-local['y'],rotation=-local['rotation_degrees'],length=bone['length'])
        if bone['parent_id'] is not None:item['parent']=bone['parent_id']
        bones.append(item)
    helper=row['helper'];local=helper['setup_local'];bones.append(dict(name=helper['id'],parent=helper['parent_id'],
        x=local['translation_xy'][0],y=-local['translation_xy'][1],rotation=-local['rotation_degrees'],length=helper['length']))
    indices={b['name']:i for i,b in enumerate(bones)};vertices=[]
    for entries in row['weights']:
        if abs(sum(e['weight'] for e in entries)-1)>1e-9:raise ValueError('sleeve_target_weight_sum')
        vertices.append(len(entries))
        for e in entries:vertices.extend([indices[e['bone_id']],e['local_xy'][0],-e['local_xy'][1],e['weight']])
    name=row['layer_id']+'-'+row['component_id'];source_bones={b['id']:b for b in skeleton['bones']}
    parent=source_bones[helper['parent_id']];hand=source_bones[row['tracks'][0]['drivers'][1]]
    chain=[source_bones[parent['parent_id']],parent,hand,helper];animations={};checks={}
    for track in row['tracks']:
        rotation={b:{'rotate':[]} for b in track['drivers']};deform=[]
        for tick in range(129):
            values=angles(track['amplitudes'],tick);transforms=frames(chain,dict(zip(track['drivers'],values)))
            for b,a in zip(track['drivers'],values):rotation[b]['rotate'].append(dict(time=tick/64,value=-a))
            delta=offset_at(track,tick,len(row['weights']))
            deform.append(dict(time=tick/64,vertices=local_offsets(row['weights'],delta,transforms)))
        animations[track['bone_id']]=dict(bones=rotation,attachments={'default':{name:{name:{'deform':deform}}}})
    width,height=skeleton['canvas']
    doc=dict(skeleton=dict(spine='4.3.26',hash=canonical_sha256(source),images='./images/',x=0,y=-height,width=width,height=height,fps=64),
        bones=bones,slots=[dict(name=name,bone=parent['id'],attachment=name)],constraints=[],
        skins=[dict(name='default',attachments={name:{name:dict(type='mesh',path=name,uvs=[v for p in mesh['uvs'] for v in p],
            triangles=[v for t in row['triangles'] for v in t],vertices=vertices)}})],animations=animations)
    for track in row['tracks']:
        probe=deepcopy(doc);probe['animations']={track['bone_id']:animations[track['bone_id']]};qa=[];key_error=0.;mid_error=0.
        for sample in range(257):
            tick=sample/2;actual=[[x,-y] for x,y in world(probe,tick/64)[name]]
            values=angles(track['amplitudes'],tick);base=_deform(row['weights'],frames(chain,dict(zip(track['drivers'],values))))
            delta=offset_at(track,tick,len(row['weights']));expected=[[p[k]+d[k] for k in (0,1)] for p,d in zip(base,delta)]
            error=max(math.dist(a,b) for a,b in zip(actual,expected))
            if sample%2:mid_error=max(mid_error,error)
            else:key_error=max(key_error,error)
            qa.append(metrics(row['setup_vertices'],actual,row['triangles']))
        checks[track['bone_id']]=dict(key_error_px=key_error,midpoint_error_px=mid_error,failed_samples=sum(not passed(q) for q in qa),sample_count=257)
    return doc,dict(target='4.3.26',checks=checks,passed=all(c['key_error_px']<=1e-7 and c['failed_samples']==0 for c in checks.values()),
        authority='none',production_authorized=False,runtime_status='not_evaluated',alpha_contact_status='not_evaluated')
