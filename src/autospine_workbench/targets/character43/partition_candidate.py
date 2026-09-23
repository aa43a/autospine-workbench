"""Build an isolated mesh partition with explicit sampled boundary-gap checks."""
from hashlib import sha256
import json
import math
from ...automation.storage_io import canonical_bytes
from .numeric_reference import read,write
from .affine_pose import sample
from .deformation_qa import inspect
from .partition_rebind import apply

PROFILE='selected-region-rigid-partition-v1'


def build(files,plan,on_progress=None):
    doc=json.loads(files['skeleton.json']);reference=read(files);setup=json.loads(files['rig-setup-reference.json'])
    digest=sha256(files['skeleton.json']).hexdigest()
    if reference['skeleton_sha256']!=digest or setup['skeleton_sha256']!=digest:
        raise ValueError('partition_source_identity')
    name,slot=plan['animation'],plan['slot']
    if set(doc['animations'])!={name} or len(doc['skins'])!=1 or doc['skins'][0].get('name')!='default':
        raise ValueError('partition_animation_or_skin_unsupported')
    result,points,partition=apply(doc,plan,setup['vertices'][slot]);setup['vertices'][slot]=points
    times=[f['time'] for f in reference['animations'][name]]
    if len(times)>4097:raise ValueError('partition_sample_limit')
    frames=[];worst=None;failed=0
    for index,time in enumerate(times):
        if on_progress and index%32==0:on_progress(dict(stage='partition_validate',index=index,total=len(times)))
        vertices=sample(result,name,time)[0];frames.append(dict(time=time,vertices=vertices))
        gaps=[(math.dist(vertices[slot][a],vertices[slot][b]),a,b) for a,b in partition['boundary_pairs']]
        if gaps:
            gap,a,b=max(gaps);failed+=gap>2
            if worst is None or gap>worst['gap_px']:worst=dict(time=time,gap_px=gap,vertices=[a,b])
    seam=dict(status='needs_changes' if failed else 'sampled_passed',limit_px=2,failed_times=failed,
        sample_count=len(times),worst=worst,scope='paired_boundary_vertices_not_raster_or_continuous_seam_acceptance')
    output={n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','motion-ir.json')}
    output['skeleton.json']=canonical_bytes(result);digest=sha256(output['skeleton.json']).hexdigest()
    setup['skeleton_sha256']=digest;output['rig-setup-reference.json']=canonical_bytes(setup)
    output=write(output,dict(skeleton_sha256=digest,animations={name:frames}))
    geometry=inspect(output,setup_vertices=setup['vertices']);output['deformation.json']=canonical_bytes(geometry)
    evidence=json.loads(files['motion-review.json'])
    from .final_motion_contact import recheck
    contact=recheck(result,name,json.loads(files['motion-ir.json']),json.loads(files['motion-contact.json']),times,evidence['reference_length_px'])
    evidence.update(status='needs_changes',geometry_passed=geometry['passed'],runtime_status='not_evaluated',
        depth_order_status='not_evaluated',contact_status=contact['status'],authority='none')
    evidence['issues']=[i for i in evidence.get('issues',[]) if i['stage']=='projection']
    evidence['issues'].append(dict(stage='repair',reason_code='motion_partition_requires_seam_and_visual_review'))
    if failed:evidence['issues'].append(dict(stage='repair',reason_code='motion_partition_boundary_gap'))
    if not geometry['passed']:evidence['issues'].append(dict(stage='geometry',reason_code='motion_target_deformation_needs_changes'))
    for key in ('area_repair','post_contact_repair'):evidence.pop(key,None)
    output['motion-review.json']=canonical_bytes(evidence);output['motion-contact.json']=canonical_bytes(contact)
    output['parent-motion-review.json']=files['motion-review.json']
    output['motion-repair.json']=canonical_bytes(dict(profile=PROFILE,slot=slot,animation=name,
        partition=partition,boundary=seam,geometry=geometry,parent_geometry=json.loads(files['deformation.json']),
        sample_count=len(times),authority='none',selected=False))
    manifest=json.loads(files['character-manifest.json']);manifest.update(status='needs_changes',authority='none',
        production_authorized=False,files={n:sha256(v).hexdigest() for n,v in output.items()})
    output['character-manifest.json']=canonical_bytes(manifest)
    return output,evidence,geometry
