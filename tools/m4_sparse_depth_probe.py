"""Recheck an immutable candidate with conservative sparse alpha tiles."""
import argparse
from hashlib import sha256
import json
import re
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from m4_motion_cohort import api


def run(job,output,check_order=False,registration=None,tight=False):
    task=api('http://127.0.0.1:8918','/api/motions/'+job)
    if task.get('kind')!='adapt' or task['status']!='succeeded':raise ValueError('completed_candidate_required')
    store=AnimatedStore(Path('workspace'))
    artifact=task['result']['artifact_sha256']
    if registration is None:
        files=store.read(artifact);depth_raw=files['motion-depth.json']
    else:
        if not re.fullmatch('[a-f0-9]{64}',registration):raise ValueError('registration_invalid')
        from autospine_workbench.automation.motion_related_evidence import inspect
        from autospine_workbench.automation.storage_io import canonical_bytes
        from autospine_workbench.resolved_project import canonical_sha256
        folder=Path('workspace/jobs/motion-intake-v1')/job
        request=json.loads((folder/'request.json').read_bytes())
        entry=json.loads((folder/'related-candidates'/(registration+'.json')).read_bytes())
        value=json.loads(store.read_file(registration,'related.json'))
        if (entry!={'digest':registration} or value['baseline_sha256']!=artifact
                or value['request_sha256']!=canonical_sha256(request)):
            raise ValueError('registration_source_changed')
        artifact=value['candidate_sha256'];files=store.read(artifact)
        inspect(request,store.read(request['character_sha256']),files,value['receipt'],value['runtime'],value.get('visual'))
        audit=value['receipt']['depth_audit']
        if audit['candidate_bundle_sha256']!=artifact or audit['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
            raise ValueError('registration_depth_changed')
        depth_raw=canonical_bytes(audit['depth'])
    document=json.loads(files['skeleton.json']);depth=json.loads(depth_raw)
    skeleton=sha256(files['skeleton.json']).hexdigest()
    if registration is None and depth.get('skeleton_sha256')!=skeleton:raise ValueError('depth_identity_mismatch')
    probe=Probe(document,files,'external-motion',tiled=True,rendered_bounds=True,
                sparse='tight_triangle_boxes' if tight else True)
    rows=[]
    for pair in depth['pairs']:
        a,b=pair['arm_slot'],pair['torso_slot']
        for sample in pair['samples']:
            time=sample['tick']/1e6;old=sample.get('overlap',{})
            try:value=probe.pair(a,b,time)
            except ValueError as error:
                value=dict(status='unmeasured',reason_code=str(error))
                if getattr(error,'diagnostic',None):value['raster_budget']=error.diagnostic
            rows.append(dict(pair=[a,b],time=time,previous=old,
                current={k:v for k,v in value.items() if k!='tiles'}))
        print(json.dumps(dict(pair=[a,b],remaining=probe.remaining)),flush=True)
    common=[r for r in rows if r['previous'].get('status')=='sampled' and r['current']['status']=='sampled']
    mismatches=[r for r in common if r['previous']['overlap_pixels']!=r['current']['overlap_pixels']]
    result=dict(profile='conservative-triangle-box-tiles-v1-experiment',job_id=job,
        tight_triangle_boxes=tight,
        artifact_sha256=artifact,skeleton_sha256=skeleton,
        registration_sha256=registration,depth_sha256=sha256(depth_raw).hexdigest(),
        pixel_budget=64_000_000,pixel_budget_used=64_000_000-probe.remaining,
        previous_budget_used=depth.get('target_overlap',{}).get('sampled_pixel_budget_used'),
        common_measured=len(common),overlap_mismatches=len(mismatches),
        recovered=sum(r['previous'].get('status')=='unmeasured' and r['current']['status']=='sampled' for r in rows),
        lost_measurements=sum(r['previous'].get('status')=='sampled' and r['current']['status']!='sampled' for r in rows),
        unmeasured=sum(r['current']['status']=='unmeasured' for r in rows),records=rows,
        authority='none',production_authorized=False,
        scope='source_sample_overlap_only_not_new_order_midpoints_runtime_or_visual_acceptance')
    if check_order:
        from copy import deepcopy
        from collections import Counter
        from autospine_workbench.targets.character43.motion_depth_order import build
        checked=deepcopy(depth)
        lookup={(tuple(r['pair']),r['time']):r['current'] for r in rows}
        for pair in checked['pairs']:
            for sample in pair['samples']:
                sample['overlap']=lookup[((pair['arm_slot'],pair['torso_slot']),sample['tick']/1e6)]
        proposed,order=build(document,'external-motion',checked,probe)
        result.update(order=order,order_candidate_available=proposed is not None,
            order_failure_counts=dict(Counter(r['reason_code'] for r in order['failures'])),
            total_pixel_budget_used=64_000_000-probe.remaining,
            measured_pair_times=len(probe.results),
            scope='source_samples_and_guarded_order_attempts_not_exhaustive_midpoints_or_visual_acceptance')
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','order')}),flush=True)
    if mismatches:raise ValueError('sparse_overlap_disagrees_with_existing_measurements')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--order',action='store_true')
    parser.add_argument('--registration')
    parser.add_argument('--tight',action='store_true')
    args=parser.parse_args();run(args.job,args.output,args.order,args.registration,args.tight)
