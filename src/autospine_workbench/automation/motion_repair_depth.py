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
    depth = build(document, bvh, bundle.kimodo_map if kimodo else bundle.bvh_map,
        kimodo=kimodo, clip_bounds=boundaries(request.get('clip'), ticks),
        yaw_degrees=request.get('projection', {}).get('yaw_degrees') if request.get('projection') else None,
        render_regions=True)
    if on_progress:
        on_progress()
    animation = request['repair_execution']['draft']['animation']
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
