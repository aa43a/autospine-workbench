"""Diagnose bounded shared-camera feasibility from a verified request source."""
import argparse
import json
from pathlib import Path

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.camera_path import plan
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.torso_projection_source import anchors
from autospine_workbench.automation.storage_io import canonical_bytes


def run(state,request,output):
    request=json.loads(request.read_bytes())
    if request.get('clip'):raise ValueError('camera_probe_requires_full_source')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    vectors,_,_=extract(bundle)
    frames,ticks=anchors(bundle,0)
    reports=[plan(vectors,frames,[t/1e6 for t in ticks],maximum_speed=speed) for speed in (60,90)]
    value=dict(motion_identity=identity,source_kind=bundle.source_kind,records=reports,authority='none')
    with output.open('xb') as stream:stream.write(canonical_bytes(value))
    print(json.dumps([dict(status=r['status'],limits=r['limits'],failure=r.get('failure')) for r in reports]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','request','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.state,a.request,a.output)
