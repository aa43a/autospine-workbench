"""All-body source-bound traces with explicit surface routing and unknowns."""
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
from autospine_workbench.targets.character43.depth_surface_checker import SurfaceChecker
from autospine_workbench.targets.character43.depth_surface_inventory import build as inventory_build


def run(job,output,subdivisions=2):
    import re
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job):raise ValueError('surface_trace_job_invalid')
    if output.exists() and any(output.iterdir()):raise ValueError('surface_trace_output_exists')
    root=Path('workspace');folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json');result=read_document(folder/'result.json')['result']
    files=AnimatedStore(root).read(result['artifact_sha256']);identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,result['artifact_sha256'],bundle,request)
    if bundle.source_kind=='kimodo_npz':raise ValueError('surface_trace_bvh_required')
    if json.loads(files.get('motion-torso-projection.json',b'{}')).get('applied'):
        raise ValueError('surface_trace_warped_plane_not_supported')
    document=json.loads(files['skeleton.json']);depth=json.loads(files['motion-depth.json'])
    inventory=inventory_build(document);arms=sorted({p['arm_slot'] for p in depth['pairs']});source={}
    for pair in depth['pairs']:
        for row in pair['samples']:
            tick=row['tick'];value=row['source_tick']
            if tick in source and source[tick]!=value:raise ValueError('surface_trace_time_conflict')
            source[tick]=value
    if subdivisions not in (2,4):raise ValueError('surface_trace_subdivisions')
    ticks=sorted(source.items());times=dict(ticks)
    times.update({a[0]+(b[0]-a[0])*i/subdivisions:a[1]+(b[1]-a[1])*i/subdivisions
                  for a,b in zip(ticks,ticks[1:]) for i in range(1,subdivisions)})
    if not times or len(times)>512 or len(arms)*len(inventory['surfaces'])>512:raise ValueError('surface_trace_resource_limit')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),json.loads((bundle.path/'map.json').read_bytes()),
                                request.get('projection',{}).get('yaw_degrees',0))
    observations={};pairs=[];checks=[]
    for arm in arms:
        for surface in inventory['surfaces']:
            body=surface['slot']
            if body==arm:continue
            probe=Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
            checker=SurfaceChecker(probe,sampler,inventory);rows=[];counts=Counter()
            for tick,source_tick in sorted(times.items()):
                triangle_counts={}
                def collect(i,values):triangle_counts.setdefault(i,Counter()).update(values)
                try:check=checker.check(arm,body,tick/1e6,source_tick,on_triangle=collect)
                except ValueError as error:check=dict(status='unmeasured',reason_code=str(error))
                if check['status']=='unmeasured':triangle_counts={}
                counts[check['status']]+=1
                rows.append(dict(body=body,time=tick/1e6,source_tick=source_tick,triangles=triangle_counts,
                                 status=check['status'],reason_code=check.get('reason_code'),surface_role=surface['role']))
                checks.append(dict(check,arm=arm,body=body,time=tick/1e6,source_tick=source_tick))
            # Omit only pairs proven nonoverlapping at every sample; retain their coverage receipt.
            retained=any(r['status']!='no_overlap' for r in rows)
            if retained:observations.setdefault(arm,[]).extend(rows)
            pairs.append(dict(arm=arm,body=body,role=surface['role'],retained=retained,status_counts=dict(counts),
                              pixel_budget_used=64_000_000-probe.remaining))
            print(json.dumps(pairs[-1]),flush=True)
    output.mkdir(parents=True,exist_ok=True);raw=canonical_bytes(observations);check_raw=canonical_bytes(checks)
    report=dict(source_job_id=job,source_artifact_sha256=result['artifact_sha256'],inventory=inventory,pairs=pairs,
        observations_sha256=sha256(raw).hexdigest(),checks_sha256=sha256(check_raw).hexdigest(),
        source_sha256=sha256(bundle.raw_bvh).hexdigest(),sampled_frames=len(times),source_subdivisions=subdivisions,pixel_budget_per_pair=64_000_000,
        supplemental_models=[dict(profile='surface-routing-depth-models-v1-experiment',
            assumptions=['torso_planar_garment_without_thickness_or_cloth_z','segment_axis_depth',
                         'observed_fingertip_hand_axis','same_chain_secondary_influence_envelopes'])],
        status_counts=dict(Counter(c['status'] for c in checks)),authority='none',selected=False,runtime_recaptured=False)
    for name,data in [('observations',raw),('checks',check_raw),('report',canonical_bytes(report))]:
        (output/(name+'.json')).write_bytes(data)
    print(json.dumps(dict(retained_pairs=sum(p['retained'] for p in pairs),status_counts=report['status_counts'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--subdivisions',type=int,choices=(2,4),default=2)
    args=parser.parse_args();run(args.job,args.output,args.subdivisions)
