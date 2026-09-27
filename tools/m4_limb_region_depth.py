"""Bounded per-region depth diagnosis on a verified lossless limb partition."""
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
from autospine_workbench.targets.character43.torso_projection_profile import prepare
from autospine_workbench.targets.character43.torso_baked_depth_plane import BakedWarpPlane
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.torso_depth_refinement import Checker
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.spine43.seam_raster import texture


def run(source, partition, output, state):
    if output.exists():raise ValueError('output_exists')
    receipt=json.loads((source/'report.json').read_bytes())
    digest=receipt['candidate_bundle_sha256'];files=AnimatedStore(source/'isolated-store').read(digest)
    proof=json.loads((partition/'report.json').read_bytes());raw=(partition/'skeleton.json').read_bytes()
    if (proof['source_artifact_sha256']!=digest or proof['skeleton_sha256']!=sha256(raw).hexdigest()
            or proof['source_skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()):
        raise ValueError('region_depth_identity')
    original=json.loads(files['skeleton.json']);document=json.loads(raw);name='external-motion'
    if (original['bones']!=document['bones'] or original['animations'][name]['bones']!=document['animations'][name]['bones']):
        raise ValueError('region_depth_bone_frame_changed')
    request=json.loads((source/'request.json').read_bytes());identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,digest,bundle,request)
    if bundle.source_kind!='bvh':raise ValueError('region_depth_bvh_required')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,request['projection']['yaw_degrees'])
    plane=BakedWarpPlane(original,name,json.loads(files['motion-torso-projection.json']),prepare(bundle,request))
    def provider(doc,animation,time,source_sampler,tick):
        if doc is not document or animation!=name:raise ValueError('region_depth_frame_mismatch')
        return plane(original,name,time,source_sampler,tick)
    depth=json.loads(files['motion-depth.json']);axes={};rows=[];counts=Counter();pairs=0
    for region in proof['partition']['regions']:
        parent=region['source_slot'];slot=region['slot']
        if parent not in axes:
            mesh=original['skins'][0]['attachments'][parent][parent]
            axes[parent]=infer(original,mesh,texture(files['images/'+mesh.get('path',parent)+'.png']))
        for pair in depth['pairs']:
            if pair['arm_slot']!=parent:continue
            pairs+=1
            if pairs>256:raise ValueError('region_depth_pair_limit')
            probe=Probe(document,files,name,tiled=True,sparse=True,rendered_bounds=True)
            checker=Checker(probe,sampler,plane_provider=provider,pixelwise=True)
            checker.axes[slot]=axes[parent] # Preserve complete source-hand extent.
            samples=pair['samples'];ticks=[(r['tick'],r['source_tick']) for r in samples]
            ticks += [((a['tick']+b['tick'])/2,(a['source_tick']+b['source_tick'])/2) for a,b in zip(samples,samples[1:])]
            if len(ticks)>1023:raise ValueError('region_depth_sample_limit')
            for tick,source_tick in sorted(ticks):
                try: result=checker.check(slot,pair['torso_slot'],tick/1e6,source_tick)
                except ValueError as error:result=dict(status='unmeasured',reason_code=str(error))
                rows.append(dict(result,region=slot,source_slot=parent,group=region['group'],body=pair['torso_slot'],
                                 time=tick/1e6,source_tick=source_tick))
                counts[result['status']]+=1
        print(json.dumps(dict(region=slot,completed_pairs=pairs)),flush=True)
    report=dict(profile='limb-region-depth-diagnosis-v1',source_artifact_sha256=digest,
        skeleton_sha256=sha256(raw).hexdigest(),rows=rows,counts=dict(counts),source_hand_axes=axes,
        authority='none',selected=False,scope='source_frames_and_midpoints_proxy_not_order_or_visual_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(canonical_bytes(report))
    print(json.dumps(dict(counts)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','partition','output'):p.add_argument(key,type=Path)
    p.add_argument('--state',type=Path,default=Path('workspace'))
    a=p.parse_args();run(a.source,a.partition,a.output,a.state)
