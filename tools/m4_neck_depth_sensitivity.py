"""Compare distal overlap against a declared neck-axis thickness hypothesis."""
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
from autospine_workbench.targets.character43.hand_depth_observation import observe
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.character43.weighted_depth_interval import build
from autospine_workbench.targets.character43.mesh_pair_depth import compare
from autospine_workbench.targets.character43.depth_surface_inventory import influences
from autospine_workbench.targets.spine43.seam_raster import texture


def run(source,partition,order,output,body,state):
    if output.exists():raise ValueError('output_exists')
    digest=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    proof=json.loads((partition/'report.json').read_bytes());raw=(partition/'skeleton.json').read_bytes()
    trial=json.loads(order.read_bytes())
    if (proof['source_artifact_sha256']!=digest or trial['source_artifact_sha256']!=digest
            or proof['source_skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()
            or proof['skeleton_sha256']!=sha256(raw).hexdigest()
            or trial['input_skeleton_sha256']!=sha256(raw).hexdigest()):
        raise ValueError('neck_depth_identity')
    doc=json.loads(raw);original=json.loads(files['skeleton.json']);name='external-motion'
    if (doc['bones']!=original['bones'] or doc['animations'][name]['bones']!=original['animations'][name]['bones']):
        raise ValueError('neck_depth_bone_frame_changed')
    slots={s['name']:s for s in doc['slots']}
    mesh=lambda n:doc['skins'][0]['attachments'][n][slots[n]['attachment']]
    if influences(doc,slots[body],mesh(body))!={'neck'}:raise ValueError('neck_depth_binding_required')
    request=json.loads((source/'request.json').read_bytes());identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,digest,bundle,request)
    if bundle.source_kind!='bvh':raise ValueError('neck_depth_bvh_required')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,request['projection']['yaw_degrees'])
    groups={r['slot']:r for r in proof['partition']['regions']}
    selected=sorted({n for failure in trial['order']['failures']
        if body in failure['conflict']['slots'] for n in failure['conflict']['slots'] if n in groups})
    if not selected or len(selected)>16:raise ValueError('neck_depth_pair_limit')
    depth=json.loads(files['motion-depth.json']);rows=[];counts=Counter();radii=(0,.02,.05,.1)
    for region in selected:
        parent=groups[region]['source_slot'];parent_mesh=original['skins'][0]['attachments'][parent][parent]
        axis=infer(original,parent_mesh,texture(files['images/'+parent_mesh.get('path',parent)+'.png']))
        pair=next(p for p in depth['pairs'] if p['arm_slot']==parent)
        samples=pair['samples'];ticks=[(r['tick'],r['source_tick']) for r in samples]
        ticks += [((a['tick']+b['tick'])/2,(a['source_tick']+b['source_tick'])/2) for a,b in zip(samples,samples[1:])]
        if len(ticks)>1023:raise ValueError('neck_depth_sample_limit')
        probes={radius:Probe(doc,files,name,tiled=True,sparse=True,rendered_bounds=True) for radius in radii}
        for tick,source_tick in sorted(ticks):
            time=tick/1e6;hands=observe(sampler,source_tick,full_hand=True)
            segments=sampler(source_tick);segments.update(hands['segments'])
            lengths={n:v['length'] for n,v in axis['axes'].items() if n in hands['segments']}
            arm=build(doc,mesh(region),segments,axis_lengths=lengths,chain_kind='arm')['intervals']
            endpoints=sampler.mapped_segment('humanoid.neck',source_tick)
            results=[]
            for radius,probe in probes.items():
                neck=[[min(endpoints)-radius,max(endpoints)+radius]]*(len(mesh(body)['uvs'])//2)
                result=compare(probe,region,body,time,arm,neck)
                results.append(dict(result,radius=radius));counts[str(radius)+':'+result['status']]+=1
            rows.append(dict(region=region,body=body,time=time,source_tick=source_tick,
                             neck_axis_depths=endpoints,hypotheses=results))
        print(json.dumps(dict(completed_region=region,counts=dict(counts))),flush=True)
    report=dict(profile='neck-axis-thickness-sensitivity-v1',authority='none',selected=False,
        source_artifact_sha256=digest,skeleton_sha256=sha256(raw).hexdigest(),
        order_report_sha256=sha256(order.read_bytes()).hexdigest(),rows=rows,counts=dict(counts),
        assumptions=['Entire neck material lies within source Neck-to-Head depth range plus radius.',
                     'Radius is a declared sensitivity parameter in source reference-length units, not measured thickness.',
                     'Actual baked mesh alpha overlap is tested; depth transport is a proxy, not observed surface depth.'],
        scope='diagnosis_only_no_order_change_no_candidate_adoption',tested_radii=list(radii))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(canonical_bytes(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','partition','order','output'):p.add_argument(key,type=Path)
    p.add_argument('--body',required=True);p.add_argument('--state',type=Path,default=Path('workspace'))
    a=p.parse_args();run(a.source,a.partition,a.order,a.output,a.body,a.state)
