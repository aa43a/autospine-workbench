"""Turn explicit material regions into render parts without solving their motion."""
from ...resolved_project import canonical_sha256
from .depth_region_partition import build as partition

KINDS={'fixed','sliding','free','transition','occlusion'}


def build(document, slot, scope, *, part_limit=128):
    reference=scope['reference_slot']
    if reference==slot:
        raise ValueError('occlusion_partition_reference_invalid')
    slots={s['name']:s for s in document['slots']}
    if slot not in slots or reference not in slots:
        raise ValueError('occlusion_partition_slot_missing')
    meshes=document['skins'][0]['attachments']
    if any(slots[s].get('attachment') not in meshes.get(s,{}) for s in (slot,reference)):
        raise ValueError('occlusion_partition_setup_attachment_unavailable')
    mesh=meshes[slot][slots[slot]['attachment']]
    other=meshes[reference][slots[reference]['attachment']]
    if (canonical_sha256(mesh)!=scope['mesh_sha256'] or
            canonical_sha256(other)!=scope['reference_mesh_sha256']):
        raise ValueError('occlusion_partition_mesh_changed')
    regions=scope['regions']
    if not isinstance(regions,dict) or set(regions)-KINDS:
        raise ValueError('occlusion_partition_roles_invalid')
    if not regions.get('occlusion'):
        raise ValueError('occlusion_partition_scope_required')
    count=len(mesh['triangles'])//3
    labels=['unclassified']*count
    seen=set()
    for kind,indices in regions.items():
        if (not isinstance(indices,list) or any(type(i) is not int or not 0<=i<count for i in indices)
                or len(set(indices))!=len(indices) or seen.intersection(indices)):
            raise ValueError('occlusion_partition_triangles_invalid')
        seen.update(indices)
        for i in indices:labels[i]=kind
    candidate,report=partition(document,[slot],triangle_labels={slot:labels},
                               part_limit=part_limit,preserve_draw_order=True)
    # All roles retain their motion. A fixed/sliding label is not a solved constraint.
    report.update(profile='explicit-occlusion-render-regions-v1',source_slot=slot,
        reference_slot=reference,scope_sha256=canonical_sha256(scope),
        source_skeleton_sha256=canonical_sha256(document),
        candidate_skeleton_sha256=canonical_sha256(candidate),
        unclassified_triangles=count-len(seen),motion_changed=False,order_changed=False,
        solved_constraints=False,visual_status='not_checked',
        scope='explicit_region_representation_not_depth_inference_or_occlusion_repair')
    return candidate,report
