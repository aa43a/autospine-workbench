"""Package returned art with its exact region, interval, and fresh sampled checks."""
from hashlib import sha256
from io import BytesIO
import json
from PIL import Image
from ...automation.storage_io import canonical_bytes
from .affine_pose import sample
from .numeric_reference import read,write
from .deformation_qa import inspect
from .material_region_scene import build as scene

PROFILE='selected-region-pose-material-v1'


def build(files,plan,material,on_progress=None):
    from ...resolved_project import canonical_sha256
    request=json.loads(material['request.json']);png=material['replacement.png']
    if (request['draft_sha256']!=plan['draft_sha256'] or request['artifact_sha256']!=plan['artifact_sha256']
            or request['slot']!=plan['slot'] or request['animation']!=plan['animation']):
        raise ValueError('material_candidate_identity_changed')
    if canonical_sha256({n:sha256(v).hexdigest() for n,v in material.items()})!=plan['material_bundle_sha256']:
        raise ValueError('material_candidate_bundle_changed')
    doc=json.loads(files['skeleton.json']);reference=read(files);setup=json.loads(files['rig-setup-reference.json'])
    digest=sha256(files['skeleton.json']).hexdigest()
    if reference['skeleton_sha256']!=digest or setup['skeleton_sha256']!=digest:raise ValueError('material_candidate_reference_changed')
    name,slot=plan['animation'],plan['slot'];start,end=plan['mapping']['interval']
    times=[f['time'] for f in reference['animations'][name]]
    if end>max(times):raise ValueError('material_candidate_time_outside_motion')
    # Validate both sides of each hard switch, including the exact boundaries.
    times=sorted(set(times+[start,end]+[t for b in (start,end) for t in (b-1e-4,b+1e-4) if 0<=t<=max(times)]))
    if len(times)>4097:raise ValueError('material_candidate_sample_limit')
    texture='material-'+sha256(png).hexdigest()
    result,report=scene(doc,plan,texture)
    output={n:v for n,v in files.items() if n.endswith('.png') or n=='motion-ir.json'}
    with Image.open(BytesIO(png)) as image:
        if image.mode!='RGBA' or list(image.size)!=request['texture_size']:raise ValueError('material_candidate_image_changed')
        w,h=image.size;page=Image.new('RGBA',(w+4,h+4));page.paste(image,(2,2));stream=BytesIO();page.save(stream,format='PNG')
    output['images/'+texture+'.png']=png;output['editor/images/'+texture+'.png']=png
    output['textures/'+texture+'.png']=stream.getvalue()
    output['skeleton.atlas']=files['skeleton.atlas'].rstrip()+f'\n\ntextures/{texture}.png\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{texture}\nbounds: 2,2,{w},{h}\n'.encode()
    for added in report['added_slots']:setup['vertices'][added]=setup['vertices'][slot]
    output['skeleton.json']=canonical_bytes(result);digest=sha256(output['skeleton.json']).hexdigest();setup['skeleton_sha256']=digest
    output['rig-setup-reference.json']=canonical_bytes(setup);frames=[]
    for i,t in enumerate(times):
        if on_progress and i%32==0:on_progress(dict(index=i,total=len(times)))
        frames.append(dict(time=t,vertices=sample(result,name,t)[0]))
    output=write(output,dict(skeleton_sha256=digest,animations={name:frames}))
    geometry=inspect(output,setup_vertices=setup['vertices']);output['deformation.json']=canonical_bytes(geometry)
    evidence=json.loads(files['motion-review.json'])
    from .final_motion_contact import recheck
    contact=recheck(result,name,json.loads(files['motion-ir.json']),json.loads(files['motion-contact.json']),times,evidence['reference_length_px'])
    evidence.update(status='needs_changes',geometry_passed=geometry['passed'],runtime_status='not_evaluated',contact_status=contact['status'],depth_order_status='not_evaluated',authority='none')
    evidence.setdefault('issues',[]).append(dict(stage='repair',reason_code='motion_material_switch_requires_visual_review'))
    output['motion-review.json']=canonical_bytes(evidence);output['parent-motion-review.json']=files['motion-review.json']
    output['motion-contact.json']=canonical_bytes(contact)
    output['motion-repair.json']=canonical_bytes(dict(profile=PROFILE,slot=slot,animation=name,material=report,
        geometry=geometry,parent_geometry=json.loads(files['deformation.json']),sample_count=len(times),authority='none',selected=False))
    manifest=json.loads(files['character-manifest.json'])
    for layer in manifest.get('layers',[]):
        if any(r['region_id']==slot for r in layer.get('regions',[])):
            layer['regions'].extend(dict(region_id=s,state='weighted_candidate',source_region_id=slot,material_mapping=True) for s in report['added_slots'])
            layer['state']='weighted_candidate'
            layer['reason_codes']=list(dict.fromkeys(layer.get('reason_codes',[])+['pose_material_visual_review_required']))
    manifest.update(status='needs_changes',authority='none',production_authorized=False,
        files={n:sha256(v).hexdigest() for n,v in output.items()})
    output['character-manifest.json']=canonical_bytes(manifest)
    return output,evidence,geometry
