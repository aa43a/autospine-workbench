"""Reproduce a reference-view torso bake before using its virtual depth plane."""
import json
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.torso_projection_source import anchors,reference_shapes
from autospine_workbench.targets.character43.torso_projection_candidate import build
from autospine_workbench.targets.character43.torso_baked_depth_plane import BakedWarpPlane


def load(folder,parent_digest,parent_document,bundle,identity,yaw):
    receipt=json.loads((folder/'report.json').read_bytes())
    if (receipt['source_candidate_sha256']!=parent_digest or receipt['source_identity']!=identity
            or receipt['yaw_degrees']!=yaw or receipt['reference_source_yaw']!=0):
        raise ValueError('torso_reference_depth_source_mismatch')
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    doc=json.loads(files['skeleton.json'])
    frames,ticks=anchors(bundle,yaw);reference,_=anchors(bundle,0)
    expected=reference_shapes(frames,[t/1e6 for t in ticks],reference[0])
    reproduced,evidence=build(parent_document,'external-motion',expected)
    if reproduced is None or doc!=reproduced or receipt['source']!=expected:
        raise ValueError('torso_reference_depth_bake_mismatch')
    # Applied means reproduced visual deformation, not human or production adoption.
    evidence['applied']=True
    plane=BakedWarpPlane(doc,'external-motion',evidence,expected)
    return files,doc,receipt['candidate_bundle_sha256'],plane
