"""Complete body-pair coverage for explicitly selected lossless limb regions."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.depth_surface_inventory import build as inventory_build
from autospine_workbench.targets.character43.depth_surface_checker import SurfaceChecker
from autospine_workbench.targets.character43.torso_projection_profile import prepare
from autospine_workbench.targets.character43.torso_baked_depth_plane import BakedWarpPlane
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.spine43.seam_raster import texture


def run(source,partition,output,regions,state):
    if output.exists():raise ValueError('output_exists')
    digest=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    proof=json.loads((partition/'report.json').read_bytes());raw=(partition/'skeleton.json').read_bytes()
    if (proof['source_artifact_sha256']!=digest or proof['skeleton_sha256']!=sha256(raw).hexdigest()
            or proof['source_skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()):
        raise ValueError('region_surface_identity')
    doc=json.loads(raw);original=json.loads(files['skeleton.json']);name='external-motion'
    if doc['bones']!=original['bones'] or doc['animations'][name]['bones']!=original['animations'][name]['bones']:
        raise ValueError('region_surface_bone_frame_changed')
    groups={r['slot']:r for r in proof['partition']['regions']};inventory=inventory_build(doc)
    if not regions or len(set(regions))!=len(regions) or not set(regions)<=groups.keys():
        raise ValueError('region_surface_selection')
    if len(regions)*(len(inventory['surfaces'])-1)>512:raise ValueError('region_surface_pair_limit')
    request=json.loads((source/'request.json').read_bytes());identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,digest,bundle,request)
    if bundle.source_kind!='bvh':raise ValueError('region_surface_bvh_required')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,request['projection']['yaw_degrees'])
    plane=BakedWarpPlane(original,name,json.loads(files['motion-torso-projection.json']),prepare(bundle,request))
    def provider(document,animation,time,source_sampler,tick):
        if document is not doc or animation!=name:raise ValueError('region_surface_frame_identity')
        return plane(original,name,time,source_sampler,tick)
    axes={};parents={}
    for region in groups.values():
        parent=region['source_slot']
        if parent not in parents:
            mesh=original['skins'][0]['attachments'][parent][parent]
            parents[parent]=infer(original,mesh,texture(files['images/'+mesh.get('path',parent)+'.png']))
        axes[region['slot']]=parents[parent]
    depth=json.loads(files['motion-depth.json']);schedule=None
    for pair in depth['pairs']:
        current=[(r['tick'],r['source_tick']) for r in pair['samples']]
        if schedule is not None and current!=schedule:raise ValueError('region_surface_time_inventory')
        schedule=current
    if not schedule:raise ValueError('region_surface_time_inventory')
    times=sorted(schedule+[((a[0]+b[0])/2,(a[1]+b[1])/2) for a,b in zip(schedule,schedule[1:])])
    if len(times)>1023:raise ValueError('region_surface_sample_limit')
    rows=[];pairs=[]
    output.mkdir(parents=True,exist_ok=False)
    for arm in regions:
        for surface in inventory['surfaces']:
            body=surface['slot']
            if body==arm:continue
            probe=Probe(doc,files,name,tiled=True,sparse=True,rendered_bounds=True)
            checker=SurfaceChecker(probe,sampler,inventory,plane_provider=provider,
                                   source_axes=axes,allow_garment_plane=False)
            counts=Counter();visible=0;peak=0
            for tick,source_tick in times:
                try:
                    overlap=probe.pair(arm,body,tick/1e6)['overlap_pixels']
                    visible+=int(overlap>0);peak=max(peak,overlap)
                    check=checker.check(arm,body,tick/1e6,source_tick)
                except ValueError as error:check=dict(status='unmeasured',reason_code=str(error))
                rows.append(dict(check,arm=arm,body=body,time=tick/1e6,source_tick=source_tick))
                counts[check['status']]+=1
            pair=dict(arm=arm,body=body,role=surface['role'],status_counts=dict(counts),
                      visible_samples=visible,peak_overlap_pixels=peak,sampled_frames=len(times))
            pairs.append(pair);print(json.dumps(pair),flush=True)
        # Per-arm checkpoint is immutable and does not claim the remaining inventory is complete.
        (output/(arm+'.json')).write_bytes(canonical_bytes([r for r in rows if r['arm']==arm]))
    report=dict(profile='partition-all-body-surface-coverage-v1',source_artifact_sha256=digest,
        skeleton_sha256=sha256(raw).hexdigest(),inventory=inventory,regions=regions,pairs=pairs,
        sampled_frames=len(times),status_counts=dict(Counter(r['status'] for r in rows)),
        authority='none',selected=False,scope='all_body_pairs_for_selected_regions_not_all_arms_or_surface_truth',
        garment_plane_assumption=False,runtime_recaptured=False)
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(complete=True,pairs=len(pairs),counts=report['status_counts'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','partition','output'):p.add_argument(key,type=Path)
    p.add_argument('--region',action='append',required=True)
    p.add_argument('--state',type=Path,default=Path('workspace'))
    a=p.parse_args();run(a.source,a.partition,a.output,a.region,a.state)
