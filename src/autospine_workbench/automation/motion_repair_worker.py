"""Isolated local corrective generation and official runtime capture."""
from types import SimpleNamespace

from ..resolved_project import canonical_sha256
from ..targets.character43.selected_attachment_repair import build
from .animated_store import AnimatedStore
from .character_capture import capture
from .motion_intake_process import progress
from .motion_repair_execution import PROFILE,PARTITION_PROFILE,ORDER_PROFILE,INTERVAL_ORDER_PROFILE,OCCLUSION_PROFILE
from ..targets.character43.material_region_candidate import PROFILE as MATERIAL_PROFILE
from ..targets.character43.pose_geometry_candidate import PROFILE as POSE_PROFILE
from ..targets.character43.view_pose_candidate import PROFILE as VIEW_PROFILE
from .storage_io import canonical_bytes


def execute(folder, state_root, workspace, request):
    repair = request['repair_execution']; plan = repair['draft']
    expected={'local_repair':PROFILE,'partition':PARTITION_PROFILE,'pose_attachment':MATERIAL_PROFILE,
              'pose_geometry':POSE_PROFILE,'region_order':ORDER_PROFILE,'additional_view':VIEW_PROFILE,
              'contact_scope':OCCLUSION_PROFILE}.get(plan['action'])
    if plan['action']=='region_order' and 'interval' in plan.get('region_order', {}):
        expected=INTERVAL_ORDER_PROFILE
    if (expected is None or repair['profile'] != expected or canonical_sha256(plan) != repair['draft_sha256']
            or plan['artifact_sha256'] != repair['parent_artifact_sha256']
            ):
        raise ValueError('motion_repair_identity_mismatch')
    store = AnimatedStore(state_root)
    source = store.read(repair['parent_artifact_sha256'])
    from .motion_repair_lineage import carry
    history = carry(source, repair)
    progress(folder,'post_contact_repair')
    builder=build
    if expected==PARTITION_PROFILE:
        from ..targets.character43.partition_candidate import build as builder
    if expected==OCCLUSION_PROFILE:
        from ..targets.character43.occlusion_scope_bundle import build as builder
    if expected in (ORDER_PROFILE,INTERVAL_ORDER_PROFILE):
        from ..targets.character43.region_order_bundle import build as builder
    if expected==POSE_PROFILE:
        from ..targets.character43.pose_geometry_candidate import build as builder
    if expected==VIEW_PROFILE:
        import json
        from ..targets.character43.view_pose_candidate import build as view_build
        material=store.read(plan['material_bundle_sha256'])
        handoff=json.loads(material['request.json']); pose=json.loads(material['view-pose.json'])
        if (handoff['artifact_sha256']!=plan['artifact_sha256'] or handoff['slot']!=plan['slot']
                or handoff['animation']!=plan['animation'] or not handoff.get('view_needs')
                or pose['slot']!=plan['slot'] or pose['animation']!=plan['animation']):
            raise ValueError('motion_view_worker_scope_changed')
        files,evidence,geometry=view_build(source,pose,material['view.png'],lambda _:progress(folder,'post_contact_repair'))
    elif expected==MATERIAL_PROFILE:
        from ..targets.character43.material_region_candidate import build as material_build
        mapping=repair['material_mapping']
        if canonical_sha256(mapping)!=repair['material_mapping_sha256'] or mapping['draft_sha256']!=repair['draft_sha256']:
            raise ValueError('motion_material_execution_mapping_changed')
        material=store.read(mapping['material_bundle_sha256'])
        files,evidence,geometry=material_build(source,mapping,material,lambda _:progress(folder,'post_contact_repair'))
    else:
        files, evidence, geometry = builder(source,plan,lambda _:progress(folder,'post_contact_repair'))
    # This provenance is part of the immutable result, not a mutable UI association.
    import json
    from .motion_repair_depth import recheck
    progress(folder, 'depth_overlap')
    depth = recheck(files, request, state_root, lambda: progress(folder, 'depth_overlap'))
    provenance = dict(repair, selected=False, authority='none')
    files.update(history)
    files['motion-repair-provenance.json'] = canonical_bytes(provenance)
    manifest = json.loads(files['character-manifest.json'])
    from hashlib import sha256
    manifest['files']['motion-depth.json'] = sha256(files['motion-depth.json']).hexdigest()
    manifest['files']['motion-repair-provenance.json'] = sha256(files['motion-repair-provenance.json']).hexdigest()
    manifest['files'].update({name:sha256(raw).hexdigest() for name,raw in history.items()})
    files['character-manifest.json'] = canonical_bytes(manifest)
    progress(folder,'publish_candidate')
    artifact = store.publish(files)
    runtime = capture(SimpleNamespace(workspace_root=workspace),store,artifact,folder,
        progress=lambda stage:progress(folder,stage),cancel_requested=lambda:False,storage_reference=True)
    from .motion_repair_local_depth import run as local_recheck
    local_depth = local_recheck(files,artifact,request,state_root,folder,lambda:progress(folder,'local_depth'))
    result = dict(artifact_sha256=artifact,character_animation_status='needs_changes',runtime=runtime,
        animations=[plan['animation']],issues=evidence['issues'],geometry_passed=geometry['passed'],
        contact_status=evidence['contact_status'],depth_order_status='not_evaluated',
        authority='none',production_authorized=False,repair_parent_job_id=repair['parent_job_id'],
        repair_parent_artifact_sha256=repair['parent_artifact_sha256'],repair_profile=expected,
        repair_depth_overlap=depth.get('target_overlap'),
        local_depth_evidence_sha256=local_depth,
        clip=request.get('clip'),projection=request.get('projection'))
    if evidence.get('inherited_issue_context'):
        result['inherited_issue_context']=evidence['inherited_issue_context']
    (folder/'worker-result.json').write_bytes(canonical_bytes(result))
