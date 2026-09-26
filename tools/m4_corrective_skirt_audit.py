"""Localize leg/skirt overlap after correction using the exact source camera."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_evidence import inspect as related
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.skirt_depth_probe import inspect
from m4_register_corrective_candidate import receipt_for


def run(state,source,corrected,output):
    if output.exists():raise ValueError('corrective_skirt_output_exists')
    read=lambda p:json.loads(p.read_bytes())
    origin=read(source/'report.json');final=read(corrected/'report.json')
    old=AnimatedStore(source/'isolated-store').read(origin['candidate_bundle_sha256'])
    files=AnimatedStore(corrected/'isolated-store').read(final['candidate_bundle_sha256'])
    request=read(source/'request.json');runtime=read(corrected/'runtime/report.json')
    receipt=receipt_for(request,origin,old,final,files,runtime)
    evidence=related(request,AnimatedStore(state).read(request['character_sha256']),files,receipt,runtime)
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh':raise ValueError('corrective_skirt_source_unsupported')
    yaw=request.get('projection',{}).get('yaw_degrees',0)
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,yaw)
    duration=bundle.motion['duration_ticks']/bundle.motion['ticks_per_second']
    times=[duration*i/8 for i in range(9)]
    report=inspect(json.loads(files['skeleton.json']),files,sampler,times,surface=True)
    report.update(artifact_sha256=final['candidate_bundle_sha256'],
        skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),source_identity=identity,
        yaw_degrees=yaw,times=times,related_evidence=evidence,production_authorized=False,
        all_frames_checked=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(canonical_bytes(report))
    print(json.dumps(dict(legs=report['legs'],skirts=report['skirts'],yaw=yaw,
        counts=dict(Counter(r['status'] for r in report['rows'])),
        diagnostics=[{k:r[k] for k in ('time','pair','status','reason_code','counts') if k in r} for r in report['rows']]),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('state','source','corrected','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.state,a.source,a.corrected,a.output)
