"""Exact-body joint-animation job, with fresh evidence and official playback."""
from hashlib import sha256
import json
from types import SimpleNamespace

from ..resolved_project import canonical_sha256
from ..targets.character43.joint_animation import build
from ..targets.character43.joint_animation_config import PROFILE, normalize
from .animated_store import AnimatedStore
from .character_capture import capture
from .motion_intake_process import progress
from .storage_io import canonical_bytes


def execute(folder, state_root, workspace, request):
    frozen = request['joint_execution']
    if (frozen['profile'] != PROFILE or canonical_sha256(frozen['config']) != frozen['config_sha256']
            or normalize(frozen['config'], frozen['duration']) != frozen['config']):
        raise ValueError('joint_animation_frozen_config_changed')
    from .motion_joint_source import frozen_context, assert_frozen_unchanged
    resolved = frozen_context(state_root, request)
    store = AnimatedStore(state_root)
    source = resolved['files']
    camera = request.get('projection') or {}
    camera_keys = camera.get('keys')
    from .motion_joint_inheritance import review
    files, evidence, geometry = build(source, frozen['config'], camera_keys=camera_keys, parent_review=review(resolved),
        on_progress=lambda step: progress(folder, step))
    joint = json.loads(files['joint-animation.json'])
    if joint['animation'] != frozen['animation'] or joint['duration'] != frozen['duration']:
        raise ValueError('joint_animation_timeline_changed')
    from .motion_repair_depth import recheck
    progress(folder, 'depth_overlap')
    depth = recheck(files, request, state_root, lambda: progress(folder, 'depth_overlap'))
    files['joint-provenance.json'] = canonical_bytes(dict(frozen, authority='none', selected=False))
    manifest = json.loads(files['character-manifest.json'])
    manifest['files'] = {n:sha256(raw).hexdigest() for n,raw in files.items() if n != 'character-manifest.json'}
    files['character-manifest.json'] = canonical_bytes(manifest)
    progress(folder, 'publish_candidate')
    assert_frozen_unchanged(state_root, request)
    artifact = store.publish(files)
    runtime = capture(SimpleNamespace(workspace_root=workspace), store, artifact, folder,
        progress=lambda step: progress(folder, step), cancel_requested=lambda: False, storage_reference=True)
    result = dict(artifact_sha256=artifact, character_animation_status=evidence['status'], runtime=runtime,
        animations=[frozen['animation']], issues=evidence['issues'], inherited_issue_context=evidence['inherited_issue_context'],
        geometry_passed=geometry['passed'], contact_status=evidence['contact_status'],
        depth_order_status='joint_overlap_requires_visual_review', joint_depth_overlap=depth.get('target_overlap'),
        clip=request.get('clip'), projection=request.get('projection'),
        joint_animation_profile=PROFILE, joint_parent_job_id=frozen['parent_job_id'],
        joint_parent_artifact_sha256=frozen['parent_artifact_sha256'], joint_config_sha256=frozen['config_sha256'],
        joint_source_provenance=resolved['provenance'],
        joint_summary=dict(loop=joint['loop'], preservation=joint['preservation'], affected_slots=joint['affected_slots'],
            face=dict(status=joint['face'].get('status'), missing=joint['face'].get('missing', [])),
            secondary=dict(status=joint['secondary'].get('status'), skipped=joint['secondary'].get('skipped', []),
                regions=[{key: row.get(key) for key in ('slot', 'requested_config', 'effective_config', 'post_solve_gain')}
                         for row in joint['secondary'].get('regions', [])])),
        authority='none', selected=False, production_authorized=False)
    if 'layer_edits' in request:
        result['layer_edits'] = request['layer_edits']
    (folder/'worker-result.json').write_bytes(canonical_bytes(result))
