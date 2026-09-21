"""Register verified local Kimodo diagnostics without modifying candidate results."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.automation.motion_local_depth_evidence import publish
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.motion_rotation_status import build
from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
from m4_motion_cohort import api


def run(path):
    report=json.loads(path.read_bytes());job=report['job_id']
    if len(job)!=39 or not job.startswith('motion-') or any(c not in '0123456789abcdef' for c in job[7:]):
        raise ValueError('job_invalid')
    current=api('http://127.0.0.1:8918','/api/motions/'+job)
    if current['status']!='succeeded' or current['result']['artifact_sha256']!=report['artifact_sha256']:
        raise ValueError('local_depth_job_identity')
    root=Path('workspace');folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json');identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    files=AnimatedStore(root).read(report['artifact_sha256']);build(files,report['artifact_sha256'],bundle,request)
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    sampler=KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,mapping)
    if sampler.identity!=report['source_identity']:raise ValueError('local_depth_source_identity')
    print(publish(root,folder,request,report['artifact_sha256'],report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('report',type=Path)
    run(parser.parse_args().report)
