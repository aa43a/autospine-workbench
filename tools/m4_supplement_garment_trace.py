"""Extend frozen local traces with an explicit, isolated garment-plane model."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes,read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.torso_depth_refinement import Checker
from autospine_workbench.targets.character43.cloth_depth_plane import PROFILE


def extend(traces,clothes,checker):
    from copy import deepcopy
    result=deepcopy(traces);checks=[]
    if len(set(clothes))!=len(clothes) or not clothes or set(clothes)&traces.keys():
        raise ValueError('garment_trace_selected_slots')
    for arm,rows in traces.items():
        if set(clothes)&{r['body'] for r in rows}:raise ValueError('garment_trace_duplicate_pair')
        times={}
        for row in rows:
            time=row['time'];source_tick=row['source_tick']
            if time in times and times[time]!=source_tick:raise ValueError('garment_trace_source_time_conflict')
            times[time]=source_tick
        for cloth in clothes:
            for time,source_tick in sorted(times.items()):
                counts={}
                def collect(triangle,values):counts.setdefault(triangle,Counter()).update(values)
                try:check=checker.check(arm,cloth,time,source_tick,on_triangle=collect)
                except ValueError as error:check=dict(status='unmeasured',reason_code=str(error))
                # A failed check cannot preserve a partially accumulated measurement.
                if check['status']=='unmeasured':counts={}
                result[arm].append(dict(body=cloth,time=time,source_tick=source_tick,triangles=counts,
                    status=check['status'],reason_code=check.get('reason_code'),model_profile=PROFILE))
                checks.append(dict(check,arm=arm,cloth=cloth,time=time,source_tick=source_tick))
    return result,checks


def run(parent,clothes,output):
    if output.exists() and any(output.iterdir()):raise ValueError('garment_trace_output_exists')
    receipt_raw=(parent/'report.json').read_bytes();receipt=json.loads(receipt_raw)
    raw=(parent/'observations.json').read_bytes()
    if sha256(raw).hexdigest()!=receipt['observations_sha256']:raise ValueError('garment_trace_observations_identity')
    frozen=json.loads(Path('docs/benchmark/m4-coherent-inference-evidence-v1.json').read_bytes())
    if not any(e['source_artifact_sha256']==receipt['source_artifact_sha256'] and
               e['observations_sha256']==receipt['observations_sha256'] for e in frozen['experiments']):
        raise ValueError('garment_trace_unregistered_source')
    root=Path('workspace');job=root/'jobs/motion-intake-v1'/receipt['source_job_id']
    request=read_document(job/'request.json');result=read_document(job/'result.json')['result']
    if result['artifact_sha256']!=receipt['source_artifact_sha256']:raise ValueError('garment_trace_job_identity')
    files=AnimatedStore(root).read(receipt['source_artifact_sha256']);document=json.loads(files['skeleton.json'])
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,receipt['source_artifact_sha256'],bundle,request)
    if bundle.source_kind=='kimodo_npz':raise ValueError('garment_trace_bvh_required')
    if json.loads(files.get('motion-torso-projection.json',b'{}')).get('applied'):
        raise ValueError('garment_trace_warped_plane_not_supported')
    if not set(clothes)<={s['name'] for s in document['slots']}:raise ValueError('garment_trace_missing_slot')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),json.loads((bundle.path/'map.json').read_bytes()),
                                request.get('projection',{}).get('yaw_degrees',0))
    probe=Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    traces,checks=extend(json.loads(raw),clothes,Checker(probe,sampler,pixelwise=True))
    encoded=canonical_bytes(traces);evidence=canonical_bytes(checks)
    report=dict(source_job_id=receipt['source_job_id'],source_artifact_sha256=receipt['source_artifact_sha256'],
        parent_report_sha256=sha256(receipt_raw).hexdigest(),parent_observations_sha256=sha256(raw).hexdigest(),
        observations_sha256=sha256(encoded).hexdigest(),checks_sha256=sha256(evidence).hexdigest(),
        supplemental_models=[dict(profile=PROFILE,slots=clothes,
            assumption='garment_remains_in_torso_plane_without_thickness_or_out_of_plane_cloth_motion')],
        status_counts=dict(Counter(c['status'] for c in checks)),pixel_budget_used=64_000_000-probe.remaining,
        authority='none',selected=False,runtime_recaptured=False)
    output.mkdir(parents=True,exist_ok=True)
    for name,data in [('observations',encoded),('checks',evidence),('report',canonical_bytes(report))]:
        (output/(name+'.json')).write_bytes(data)
    print(json.dumps(dict(checks=len(checks),status_counts=report['status_counts'],pixels=report['pixel_budget_used'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('parent',type=Path)
    parser.add_argument('output',type=Path);parser.add_argument('--cloth-slot',action='append',required=True)
    args=parser.parse_args();run(args.parent,args.cloth_slot,args.output)
