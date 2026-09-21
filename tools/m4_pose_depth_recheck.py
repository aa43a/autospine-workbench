"""Re-evaluate arm/torso depth against the changed candidate's actual overlap."""
from pathlib import Path
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_depth import build,OVERLAP_PROFILE
from autospine_workbench.targets.character43.motion_depth_overlap import inspect
from autospine_workbench.targets.character43.motion_depth_order import build as order


def recheck(document,name,files,receipt):
    identity=receipt['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    kimodo=(bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind=='kimodo_npz' else None
    bvh=None if kimodo else parse_bvh(bundle.raw_bvh)
    mapping=bundle.kimodo_map if kimodo else bundle.bvh_map
    depth=build(document,bvh,mapping,kimodo=kimodo)
    depth,probe=inspect(document,files,name,depth)
    proposed,ordering=order(document,name,depth,probe)
    depth.update(profile=OVERLAP_PROFILE,order=ordering)
    if proposed is not None:
        document=proposed
        depth.update(selected=bool(ordering['frames']),
            status='depth_order_sampled_candidate' if ordering['frames'] else 'depth_overlap_no_change')
    depth['scope']='arm_torso_only_not_knee_or_skirt_depth_acceptance'
    return document,depth
