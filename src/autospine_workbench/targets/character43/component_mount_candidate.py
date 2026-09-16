"""Split a static attachment into rigidly mounted candidates in a complete scene."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from ...asset.planning.component_mount import partition
from ...automation.storage_io import canonical_bytes
from ...resolved_project import canonical_sha256
from .affine_pose import sample,matrices
from .skirt_contact import source_image
from .skirt_candidate import inverse
from .numeric_reference import read,write
from .deformation_qa import inspect


def generate(files,slot,parents,decision=None,*,partition_only=False):
    from PIL import Image
    inspect(files)
    source_sha=canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()})
    doc=json.loads(files['skeleton.json']);manifest=json.loads(files['character-manifest.json'])
    layers=[l for l in manifest['layers'] if any(r['region_id']==slot and r.get('state')=='static_reference' for r in l['regions'])]
    if len(layers)!=1 or doc['skeleton']['spine']!='4.3.26' or len(doc['skins'])!=1:
        raise ValueError('component_mount_source')
    for animation in doc['animations'].values():
        if animation.get('drawOrder') or animation.get('draworder') or slot in animation.get('slots',{}) or any(slot in skin for skin in animation.get('attachments',{}).values()):
            raise ValueError('component_mount_animated_dependency')
    attachment=doc['skins'][0]['attachments'][slot][slot];data=attachment['vertices']
    if len(data)%5 or any(data[i]!=1 or data[i+4]!=1 or data[i+1]!=data[1] for i in range(0,len(data),5)):
        raise ValueError('component_mount_static_weight_unsupported')
    if partition_only and (decision is not None or parents!=[doc['bones'][data[1]]['name']]):
        raise ValueError('component_partition_must_preserve_parent')
    setup=dict(doc,animations={'setup':{}})
    positions,bones=sample(setup,'setup',0);transforms=matrices(setup,'setup',0)
    if not parents or len(set(parents))!=len(parents) or any(p not in bones for p in parents):
        raise ValueError('component_mount_parent_missing')
    image,origin=source_image(files,doc,positions,slot);w,h=image.size
    plan=partition(image.getchannel('A').tobytes(),w,h,{p:[bones[p][0]-origin[0],origin[1]-bones[p][1]] for p in parents})
    if not plan['regions']: raise ValueError('component_mount_no_parts')
    rows=deepcopy(plan['regions']);residual_parent=None
    if decision is not None:
        expected=dict(schema='autospine.component-mount-decision/v1',source_bundle_sha256=source_sha,
            source_region_id=slot,plan_sha256=canonical_sha256(plan),decision_source='human_confirmation',reversible=True)
        if decision.get('schema')=='autospine.component-mount-decision/v2':
            residual_parent=decision.get('residual_parent')
            if residual_parent not in parents or not plan['residual_pixels']:
                raise ValueError('component_mount_residual_scope')
            expected.update(schema='autospine.component-mount-decision/v2',residual_parent=residual_parent)
        if set(decision)!=set(expected)|{'parents'} or decision.get('reversible') is not True or any(decision.get(k)!=v for k,v in expected.items()):
            raise ValueError('component_mount_decision_source')
        choices=decision['parents']
        if type(choices) is not dict or set(choices)!={r['component_id'] for r in rows} or any(p not in parents for p in choices.values()):
            raise ValueError('component_mount_decision_scope')
        if residual_parent is not None and set(choices.values())!={residual_parent}:
            raise ValueError('component_mount_residual_scope')
        for row in rows:row['proposed_parent']=choices[row['component_id']];row['reason_code']='component_parent_human_confirmed'
    if plan['residual_pixels']:
        indices=plan['residual_pixels'];xs=[i%w for i in indices];ys=[i//w for i in indices]
        rows.append(dict(component_id='unbound-residual',pixels=indices,bbox=[min(xs),min(ys),max(xs)+1,max(ys)+1],
            proposed_parent=residual_parent or doc['bones'][data[1]]['name'],
            reason_code='whole_region_parent_human_confirmed' if residual_parent else 'small_components_retained'))
    output={n:b for n,b in files.items() if n.endswith('.png') or n in ('skeleton.atlas','binding-provenance.json','skirt-trial.json')}
    original_slot=next(s for s in doc['slots'] if s['name']==slot);new_slots=[];regions=[];covered=set()
    atlas=files['skeleton.atlas'].decode();rgba=image.tobytes();details=[]
    for row in rows:
        name=slot+'-'+row['component_id']
        if name in doc['skins'][0]['attachments']:raise ValueError('component_mount_name_collision')
        left,top,right,bottom=row['bbox'];cw,ch=right-left,bottom-top
        raw=bytearray(cw*ch*4)
        for index in row['pixels']:
            if index in covered:raise ValueError('component_mount_duplicate_pixel')
            covered.add(index);offset=((index//w-top)*cw+index%w-left)*4
            raw[offset:offset+4]=rgba[index*4:index*4+4]
        crop=Image.frombytes('RGBA',(cw,ch),bytes(raw));stream=BytesIO();crop.save(stream,format='PNG')
        output['images/'+name+'.png']=stream.getvalue();output['editor/images/'+name+'.png']=stream.getvalue()
        page=Image.new('RGBA',(cw+4,ch+4));page.paste(crop,(2,2));stream=BytesIO();page.save(stream,format='PNG')
        output['textures/'+name+'.png']=stream.getvalue()
        atlas+=f'\ntextures/{name}.png\nsize: {cw+4},{ch+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 2,2,{cw},{ch}\n\n'
        parent=row['proposed_parent'];bone_index=next(i for i,b in enumerate(doc['bones']) if b['name']==parent)
        points=[(origin[0]+x,origin[1]-y) for x,y in ((left,top),(right,top),(right,bottom),(left,bottom))]
        vertices=[]
        for point in points:vertices.extend([1,bone_index,*inverse(transforms[parent],point),1])
        doc['skins'][0]['attachments'][name]={name:dict(type='mesh',path=name,width=cw,height=ch,
            vertices=vertices,uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],hull=4)}
        new_slots.append(dict(original_slot,name=name,attachment=name))
        state='static_reference' if partition_only or (row['component_id']=='unbound-residual' and residual_parent is None) else 'weighted_candidate'
        regions.append(dict(region_id=name,state=state))
        details.append({k:v for k,v in row.items() if k!='pixels'}|dict(region_id=name,visible_pixels=len(row['pixels'])))
    if len(covered)!=plan['visible_pixel_count']:raise ValueError('component_mount_coverage')
    at=next(i for i,s in enumerate(doc['slots']) if s['name']==slot);doc['slots'][at:at+1]=new_slots
    del doc['skins'][0]['attachments'][slot]
    output['skeleton.json']=canonical_bytes(doc);output['skeleton.atlas']=atlas.encode()
    editor=deepcopy(doc);editor['skeleton']['images']='./images/';output['editor/skeleton.json']=canonical_bytes(editor)
    reference=read(files)
    for animation,frames in reference['animations'].items():
        for frame in frames:
            vertices,_=sample(doc,animation,frame['time'])
            if any(len(vertices[name])!=len(points) or any(abs(a-b)>1e-6 for p,q in zip(vertices[name],points) for a,b in zip(p,q))
                   for name,points in frame['vertices'].items() if name!=slot):
                raise ValueError('component_mount_context_changed')
            frame['vertices']={name:points for name,points in frame['vertices'].items() if name!=slot}
            frame['vertices'].update({r['region_id']:vertices[r['region_id']] for r in regions})
    reference['skeleton_sha256']=sha256(output['skeleton.json']).hexdigest();output=write(output,reference)
    qa=inspect(output);output['deformation.json']=canonical_bytes(qa)
    layer=layers[0];layer['regions']=[r for r in layer['regions'] if r['region_id']!=slot]+regions
    unresolved=bool(plan['residual_pixels']) and residual_parent is None
    layer.update(state='partial' if unresolved else 'weighted_candidate',
        reason_codes=(['small_components_retained'] if unresolved else [])+([] if decision else ['component_parent_review_required']))
    if partition_only:layer.update(state='static_reference',reason_codes=['component_parent_review_required'])
    owners=manifest.get('region_owners',{});owner=owners.pop(slot,None)
    if owner is not None:
        for r in regions:owners[r['region_id']]=deepcopy(owner)
    report=dict(schema='autospine.character-component-mount/v1',source_bundle_sha256=source_sha,
        source_region_id=slot,layer_id=layer['layer_id'],profile=plan['profile'],plan_sha256=canonical_sha256(plan),parts=details,
        visible_pixels=plan['visible_pixel_count'],covered_pixels=len(covered),geometry_passed=qa['passed'],
        authority='none',selected=False,production_authorized=False,parent_review_required=decision is None,
        draw_order='replace_source_slot_in_place',motion='rigid_parent_follow_no_added_tracks')
    output['component-mount.json']=canonical_bytes(report)
    if partition_only:
        report.update(profile='same-parent-component-partition-v1',motion='original_parent_preserved',partition_only=True)
        output['component-mount.json']=canonical_bytes(report)
    if decision is not None:
        output['component-mount-decision.json']=canonical_bytes(decision)
        report['parent_decision_sha256']=sha256(output['component-mount-decision.json']).hexdigest()
        output['component-mount.json']=canonical_bytes(report)
    manifest.update(profile='component-mount-candidate-v1',authority='none',production_authorized=False,
        source_character_sha256=source_sha,full_character_animation=False,status='needs_review',qa={'runtime_status':'not_run'})
    manifest['files']={n:sha256(b).hexdigest() for n,b in output.items()};output['character-manifest.json']=canonical_bytes(manifest)
    return output,report
