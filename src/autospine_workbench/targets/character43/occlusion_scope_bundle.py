"""Package a material-scope representation as an independent, unaccepted candidate."""
from copy import deepcopy
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes
from ...resolved_project import canonical_sha256
from .occlusion_scope_partition import build as partition
from .depth_partition_compact import compact
from .numeric_reference import read, write
from .deformation_qa import inspect

PROFILE='explicit-occlusion-render-candidate-v1'


def build(files,plan,on_progress=None):
    document=json.loads(files['skeleton.json']);reference=read(files)
    setup=json.loads(files['rig-setup-reference.json']);source_digest=sha256(files['skeleton.json']).hexdigest()
    if any(r['skeleton_sha256']!=source_digest for r in (reference,setup)):
        raise ValueError('occlusion_candidate_source_identity')
    name,slot=plan['animation'],plan['slot']
    if (set(document['animations'])!={name} or len(document['skins'])!=1
            or document['skins'][0].get('name')!='default'):
        raise ValueError('occlusion_candidate_animation_or_skin_unsupported')
    candidate,report=partition(document,slot,plan['contact_scope'])
    candidate,report=compact(candidate,report)
    report['candidate_skeleton_sha256']=canonical_sha256(candidate)
    old_slots=set(document['skins'][0]['attachments'])
    def remap(vertices):
        if set(vertices)!=old_slots:raise ValueError('occlusion_candidate_reference_inventory')
        values=deepcopy(vertices);points=values.pop(slot)
        for region in report['regions']:
            values[region['slot']]=[deepcopy(points[i]) for i in region['source_vertex_indices']]
        return values
    setup['vertices']=remap(setup['vertices'])
    frames=reference['animations'][name]
    if not 2<=len(frames)<=4097:raise ValueError('occlusion_candidate_sample_limit')
    for index,frame in enumerate(frames):
        if on_progress and index%32==0:on_progress(dict(stage='occlusion_partition_validate',index=index,total=len(frames)))
        frame['vertices']=remap(frame['vertices'])
    output={n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','motion-ir.json')}
    output['skeleton.json']=canonical_bytes(candidate);digest=sha256(output['skeleton.json']).hexdigest()
    setup['skeleton_sha256']=reference['skeleton_sha256']=digest
    output['rig-setup-reference.json']=canonical_bytes(setup);output=write(output,reference)
    geometry=inspect(output,setup_vertices=setup['vertices'])
    output['deformation.json']=canonical_bytes(geometry)
    evidence=json.loads(files['motion-review.json'])
    from .final_motion_contact import recheck
    contact=recheck(candidate,name,json.loads(files['motion-ir.json']),json.loads(files['motion-contact.json']),
                    [f['time'] for f in frames],evidence['reference_length_px'])
    evidence.update(status='needs_changes',geometry_passed=geometry['passed'],runtime_status='not_evaluated',
                    depth_order_status='not_evaluated',contact_status=contact['status'],authority='none')
    # No repair occurred. Retain every prior issue rather than laundering it through a split.
    evidence.setdefault('issues',[]).append(dict(stage='repair',reason_code='motion_occlusion_representation_not_repaired'))
    if not geometry['passed']:
        evidence['issues'].append(dict(stage='geometry',reason_code='motion_target_deformation_needs_changes'))
    for key in ('area_repair','post_contact_repair'):evidence.pop(key,None)
    output['motion-review.json']=canonical_bytes(evidence);output['motion-contact.json']=canonical_bytes(contact)
    output['parent-motion-review.json']=files['motion-review.json']
    output['motion-repair.json']=canonical_bytes(dict(profile=PROFILE,slot=slot,animation=name,
        representation=report,geometry=geometry,parent_geometry=json.loads(files['deformation.json']),
        sample_count=len(frames),source_skeleton_sha256=source_digest,authority='none',selected=False))
    manifest=json.loads(files['character-manifest.json'])
    manifest.update(status='needs_changes',authority='none',production_authorized=False,
                    files={n:sha256(v).hexdigest() for n,v in output.items()})
    output['character-manifest.json']=canonical_bytes(manifest)
    return output,evidence,geometry
