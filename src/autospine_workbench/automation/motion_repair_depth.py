"""Fresh source-bound overlap evidence for the repaired rendering regions."""
from hashlib import sha256
import json

from ..bvh_parser import parse_bvh
from ..bvh_fk import bvh_frame_ticks
from ..kimodo_npz_projection import kimodo_frame_ticks
from ..motion_bundle_reader import VerifiedMotionBundleReader
from ..targets.character43.motion_clip import boundaries
from ..targets.character43.motion_depth import build
from ..targets.character43.motion_depth_overlap import inspect
from ..targets.character43.motion_rotation_status import build as verify_source
from .storage_io import canonical_bytes


def recheck(files, request, state_root, on_progress=None):
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    # Verifies both manifest identity and exact clipped/projected MotionIR.
    verify_source(files, 'unpublished-repair', bundle, request)
    kimodo = (bundle.raw_npz, bundle.kimodo_source) if bundle.source_kind == 'kimodo_npz' else None
    bvh = None if kimodo else parse_bvh(bundle.raw_bvh)
    ticks = kimodo_frame_ticks(bundle.kimodo_source) if kimodo else bvh_frame_ticks(bvh)
    document = json.loads(files['skeleton.json'])
    projection = request.get('projection') or {}
    camera = {}
    if request.get('joint_execution') and projection.get('profile') == 'continuous-yaw-source-camera-v1':
        camera = dict(camera_keys=projection['keys'], sampling_profile=projection.get('sampling_profile'))
        if projection.get('sampling_profile') == 'camera-world-projected-adaptive-v2':
            parent_depth = json.loads(files['motion-depth.json'])
            source_camera = parent_depth.get('camera', {})
            if source_camera.get('keys') != projection['keys'] or not source_camera.get('samples'):
                raise ValueError('joint_animation_depth_camera_missing')
            # The body source and camera are unchanged. Reuse their verified
            # source-tick grid, not arbitrary facial/cloth numerical QA times.
            camera['sample_times'] = [r['source_tick']/1e6 for r in source_camera['samples']]
    depth = build(document, bvh, bundle.kimodo_map if kimodo else bundle.bvh_map,
        kimodo=kimodo, clip_bounds=boundaries(request.get('clip'), ticks),
        yaw_degrees=projection.get('yaw_degrees'), render_regions=True, **camera)
    if on_progress:
        on_progress()
    animation = (request['joint_execution']['animation'] if request.get('joint_execution')
                 else request['repair_execution']['draft']['animation'])
    if any('attachment' in tracks for tracks in document['animations'][animation].get('slots', {}).values()):
        from ..targets.character43.active_depth_overlap import recheck as active_overlap
        depth = active_overlap(document, files, animation, depth, sparse=True)
    else:
        depth, _ = inspect(document, files, animation, depth, sparse=True)
    depth.update(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        character_sha256=request['character_sha256'], motion_bundle_sha256=identity['bundle_sha256'],
        repair_recheck=True, selected=False,
        scope='fresh_source_sample_overlap_not_draw_order_or_local_surface_validation')
    depth['limitations'].append('repair_depth_is_source_arm_proxy_not_repaired_surface_depth')
    files['motion-depth.json'] = canonical_bytes(depth)
    return depth
