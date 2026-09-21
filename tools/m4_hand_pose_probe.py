"""Add observed hand axes to an exact uncorrected limb probe."""
import argparse
import json
from pathlib import Path
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.source_hand_axis import extract
from autospine_workbench.targets.character43.source_pose_fit import fit
from autospine_workbench.targets.character43.source_palm_plane import extract as palm_plane


def run(folder,output):
    parent=json.loads((folder/'report.json').read_bytes());doc=json.loads((folder/'skeleton.json').read_bytes())
    if canonical_sha256(doc)!=parent['output_sha256']:raise ValueError('hand_probe_parent_mismatch')
    identity=parent['source_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    observed=extract(bundle)
    palm=palm_plane(bundle,yaw=parent.get('fixed_source_yaw_deg',0))
    result,report=fit(doc,'external-motion',observed['vectors'],observed['times'],
        yaw=parent.get('fixed_source_yaw_deg',0),project_lengths=True,include_hands=True)
    report.update(source_identity=identity,character_sha256=parent['character_sha256'],
        parent_receipt_sha256=canonical_sha256(parent),observations=observed,palm_plane=palm,
        fixed_source_yaw_deg=parent.get('fixed_source_yaw_deg',0),runtime_verified=False)
    output.mkdir(parents=True,exist_ok=False)
    (output/'skeleton.json').write_text(json.dumps(result),encoding='utf-8')
    (output/'report.json').write_text(json.dumps(report),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
