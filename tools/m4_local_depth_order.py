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
from autospine_workbench.targets.character43.source_depth_sampler import PROFILE
from autospine_workbench.targets.character43.regional_depth_candidate import build


def run(job,output,*,refine_cycles=False,partition_slots=None,cloth_constraints=False,limb_constraints=False,torso_plane=False,rendered_bounds=False,reuse_refinement_overlap=False,tiled=False,pair_budgets=False):
    root=Path('workspace'); folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json'); result=read_document(folder/'result.json')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh': raise ValueError('depth_midpoint_bvh_only')
    provenance=analyze(request,result,root,sample_limit=1)
    files=AnimatedStore(root).read(result['result']['artifact_sha256'])
    document=json.loads(files['skeleton.json']); depth=json.loads(files['motion-depth.json'])
    original_failures=dict(Counter(f['reason_code'] for f in depth['order']['failures']))
    bvh=parse_bvh(bundle.raw_bvh); yaw=request.get('projection',{}).get('yaw_degrees',0)
    candidate,pipeline=build(document,files,'external-motion',depth,bvh,bundle.bvh_map,yaw=yaw,
        partition_slots=partition_slots,cloth_constraints=cloth_constraints,limb_constraints=limb_constraints,
        torso_plane=torso_plane,rendered_bounds=rendered_bounds,reuse_refinement_overlap=reuse_refinement_overlap,
        tiled=tiled,pair_budgets=pair_budgets,refine_cycles=refine_cycles)
    evidence=pipeline['refinement']; order=pipeline['order']
    report=dict(profile='local-depth-order-experiment-v1',artifact_sha256=result['result']['artifact_sha256'],
                source_identity=identity,request_sha256=provenance['request_sha256'],
                sampling_profile=PROFILE,refinement=evidence,order=order,
                bounds_policy='rendered_triangle_vertices' if rendered_bounds else 'all_vertices',
                reuse_refinement_overlap=reuse_refinement_overlap,
                raster_policy='native_pixel_tiles_256_v1' if tiled else 'single_roi_legacy',
                candidate_available=candidate is not None,authority='none',selected=False,
                original_failure_counts=original_failures,**{k:v for k,v in pipeline.items() if k not in ('refinement','order')})
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    if candidate is not None:
        output.with_suffix('.skeleton.json').write_text(json.dumps(candidate,ensure_ascii=False),encoding='utf-8')
    return dict(resolved=evidence['resolved_rows'],remaining=evidence['remaining_rows'],
                original=report['original_failure_counts'],candidate_available=report['candidate_available'],
                failures=dict(Counter(f['reason_code'] for f in order['failures'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output',type=Path)
    parser.add_argument('--refine-cycles',action='store_true')
    parser.add_argument('--partition-slot',action='append')
    parser.add_argument('--cloth-constraints',action='store_true')
    parser.add_argument('--limb-constraints',action='store_true')
    parser.add_argument('--torso-plane',action='store_true')
    parser.add_argument('--rendered-bounds',action='store_true')
    parser.add_argument('--reuse-refinement-overlap',action='store_true')
    parser.add_argument('--tiled',action='store_true')
    parser.add_argument('--pair-budgets',action='store_true')
    args=parser.parse_args()
    if not __import__('re').fullmatch('motion-[a-f0-9]{32}',args.job):raise ValueError('job_invalid')
    print(json.dumps(run(args.job,args.output,refine_cycles=args.refine_cycles,partition_slots=args.partition_slot,
                         cloth_constraints=args.cloth_constraints,limb_constraints=args.limb_constraints,torso_plane=args.torso_plane,
                         rendered_bounds=args.rendered_bounds,reuse_refinement_overlap=args.reuse_refinement_overlap,tiled=args.tiled,
                         pair_budgets=args.pair_budgets)))
