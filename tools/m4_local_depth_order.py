"""Run the experimental cap proxy through all existing draw-order constraints."""
import argparse
from collections import Counter
import json
from pathlib import Path

from m4_local_depth_probe import analyze
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler,PROFILE
from autospine_workbench.targets.character43.depth_straddle_refine import refine
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build


def run(job,output):
    root=Path('workspace'); folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json'); result=read_document(folder/'result.json')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh': raise ValueError('depth_midpoint_bvh_only')
    provenance=analyze(request,result,root,sample_limit=1)
    files=AnimatedStore(root).read(result['result']['artifact_sha256'])
    document=json.loads(files['skeleton.json']); depth=json.loads(files['motion-depth.json'])
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,
                               request.get('projection',{}).get('yaw_degrees',0))
    refined,evidence=refine(document,files,'external-motion',depth,sampler)
    candidate,order=build(document,'external-motion',refined,Probe(document,files,'external-motion'))
    report=dict(profile='local-depth-order-experiment-v1',artifact_sha256=result['result']['artifact_sha256'],
                source_identity=identity,request_sha256=provenance['request_sha256'],
                sampling_profile=PROFILE,refinement=evidence,order=order,
                candidate_available=candidate is not None,authority='none',selected=False,
                original_failure_counts=dict(Counter(f['reason_code'] for f in depth['order']['failures'])))
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    if candidate is not None:
        output.with_suffix('.skeleton.json').write_text(json.dumps(candidate,ensure_ascii=False),encoding='utf-8')
    return dict(resolved=evidence['resolved_rows'],remaining=evidence['remaining_rows'],
                original=report['original_failure_counts'],candidate_available=report['candidate_available'],
                failures=dict(Counter(f['reason_code'] for f in order['failures'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if not __import__('re').fullmatch('motion-[a-f0-9]{32}',args.job):raise ValueError('job_invalid')
    print(json.dumps(run(args.job,args.output)))
