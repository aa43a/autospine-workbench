"""Inspect exact offline workbench candidates with the production local-depth checker."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.local_depth_analysis import analyze


def run(folder, state, output, triangles=False):
    receipt=json.loads((folder/'report.json').read_bytes())
    request=json.loads((folder/'request.json').read_bytes())
    identity=request['motion_identity']
    if receipt['motion_identity']!=identity:
        raise ValueError('local_depth_probe_identity_mismatch')
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    artifact=receipt['candidate_bundle_sha256']
    files=AnimatedStore(folder/'isolated-store').read(artifact)
    report=analyze(files,artifact,bundle,request,triangle_traces=triangles,
                   on_pair=lambda:print('pair checked',flush=True))
    if triangles:
        from autospine_workbench.targets.character43.depth_triangle_summary import summarize
        report['triangle_summary']=summarize(report['records'])
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(canonical_bytes(report))
    print(json.dumps(dict(counts=report['counts'],causes=report['causes'],
        pixel_budget_used=report['pixel_budget_used'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('folder','state','output'):p.add_argument(name,type=Path)
    p.add_argument('--triangles',action='store_true')
    a=p.parse_args();run(a.folder,a.state,a.output,a.triangles)
