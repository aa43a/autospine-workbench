"""Test explicit front-garment depth envelopes on unresolved order-cycle pairs."""
import argparse
from collections import Counter
from copy import deepcopy
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
from autospine_workbench.targets.character43.depth_surface_inventory import influences,classify
from autospine_workbench.targets.character43.skirt_surface_envelope import material_offsets,at
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.spine43.seam_raster import texture


def run(source,partition,order,output,body,state,pixelwise=False,triangle_traces=False,pixel_locations=False):
    if output.exists():raise ValueError('output_exists')
    if triangle_traces and not pixelwise:raise ValueError('skirt_triangle_trace_requires_pixelwise')
    if pixel_locations and not pixelwise:raise ValueError('skirt_pixel_locations_require_pixelwise')
    location_count=0
    digest=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    proof=json.loads((partition/'report.json').read_bytes());raw=(partition/'skeleton.json').read_bytes()
    trial=json.loads(order.read_bytes())
    if (proof['source_artifact_sha256']!=digest or trial['source_artifact_sha256']!=digest
            or proof['source_skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()
            or proof['skeleton_sha256']!=sha256(raw).hexdigest()
            or trial['input_skeleton_sha256']!=sha256(raw).hexdigest()):
        raise ValueError('skirt_depth_identity')
    doc=json.loads(raw);original=json.loads(files['skeleton.json']);name='external-motion'
    if (doc['bones']!=original['bones'] or doc['animations'][name]['bones']!=original['animations'][name]['bones']):
        raise ValueError('skirt_depth_bone_frame_changed')
    slots={s['name']:s for s in doc['slots']};bones={b['name']:b for b in doc['bones']}
    mesh=lambda n:doc['skins'][0]['attachments'][n][slots[n]['attachment']]
    if classify(influences(doc,slots[body],mesh(body)),bones)!='garment_plane_candidate':
        raise ValueError('skirt_depth_binding_required')
    request=json.loads((source/'request.json').read_bytes());identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,digest,bundle,request)
    if bundle.source_kind!='bvh':raise ValueError('skirt_depth_bvh_required')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,request['projection']['yaw_degrees'])
    setup=deepcopy(doc);setup['animations']={name:{}}
    points=sample(setup,name,0)[0][body]
    length=json.loads(files['motion-review.json'])['reference_length_px']
    aspects=(.25,.5,.75,1.)
    models={v:material_offsets(points,mesh(body)['triangles'],length,aspect_range=(.25,v)) for v in aspects}
    groups={r['slot']:r for r in proof['partition']['regions']}
    selected=sorted({n for failure in trial['order']['failures']
        if body in failure['conflict']['slots'] for n in failure['conflict']['slots'] if n in groups})
    if not selected or len(selected)>16:raise ValueError('skirt_depth_pair_limit')
    depth=json.loads(files['motion-depth.json']);rows=[];counts=Counter()
    for region in selected:
        parent=groups[region]['source_slot'];parent_mesh=original['skins'][0]['attachments'][parent][parent]
        axis=infer(original,parent_mesh,texture(files['images/'+parent_mesh.get('path',parent)+'.png']))
        pair=next(p for p in depth['pairs'] if p['arm_slot']==parent)
        samples=pair['samples'];ticks=[(r['tick'],r['source_tick']) for r in samples]
        ticks += [((a['tick']+b['tick'])/2,(a['source_tick']+b['source_tick'])/2) for a,b in zip(samples,samples[1:])]
        if len(ticks)>1023:raise ValueError('skirt_depth_sample_limit')
        probes={v:Probe(doc,files,name,tiled=True,sparse=True,rendered_bounds=True) for v in aspects}
        for tick,source_tick in sorted(ticks):
            time=tick/1e6;hands=observe(sampler,source_tick,full_hand=True)
            segments=sampler(source_tick);segments.update(hands['segments'])
            lengths={n:v['length'] for n,v in axis['axes'].items() if n in hands['segments']}
            arm=build(doc,mesh(region),segments,axis_lengths=lengths,chain_kind='arm')['intervals']
            anchor=sampler.torso_anchors(source_tick)['pelvis'];results=[]
            for aspect,probe in probes.items():
                garment=at(models[aspect],anchor,'front')
                traces={}
                def collect(index,counts):traces.setdefault(index,Counter()).update(counts)
                locations={'back':[],'ambiguous':[]}
                def pixels(rect,masks):
                    nonlocal location_count
                    for kind in locations:
                        yy,xx=masks[kind].nonzero();location_count+=len(xx)
                        if location_count>1_000_000:raise ValueError('skirt_pixel_location_limit')
                        locations[kind].extend([[int(x+rect[0]),int(y+rect[1])] for x,y in zip(xx,yy)])
                result=compare(probe,region,body,time,arm,garment,pixelwise=pixelwise,
                               on_triangle=collect if triangle_traces else None,
                               on_pixels=pixels if pixel_locations else None)
                if triangle_traces:result['triangles']=traces
                if pixel_locations:result['pixel_locations']=locations
                results.append(dict(result,aspect_max=aspect));counts[str(aspect)+':'+result['status']]+=1
            rows.append(dict(region=region,body=body,time=time,source_tick=source_tick,
                             pelvis_depth=anchor,hypotheses=results))
        print(json.dumps(dict(completed_region=region,counts=dict(counts))),flush=True)
    report=dict(profile='front-garment-depth-sensitivity-v1',authority='none',selected=False,
        source_artifact_sha256=digest,skeleton_sha256=sha256(raw).hexdigest(),
        order_report_sha256=sha256(order.read_bytes()).hexdigest(),rows=rows,counts=dict(counts),
        models=models,tested_aspect_max=list(aspects),
        triangle_traces=triangle_traces,
        pixel_locations=pixel_locations,pixel_location_space='world_x_negative_world_y_integer_pixel_origin',
        spatial_sampling='barycentric_pixel_intervals' if pixelwise else 'whole_triangle_intervals',
        assumptions=['Explicitly selected front garment; binding alone does not establish surface side.',
                     'Fixed elliptic material sections attached in depth to the source pelvis.',
                     'Aspect range is hypothetical; actual baked alpha overlap does not validate cloth depth.'],
        scope='diagnosis_only_no_order_change_no_candidate_adoption')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(canonical_bytes(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','partition','order','output'):p.add_argument(key,type=Path)
    p.add_argument('--body',required=True);p.add_argument('--state',type=Path,default=Path('workspace'))
    p.add_argument('--pixelwise',action='store_true')
    p.add_argument('--triangle-traces',action='store_true')
    p.add_argument('--pixel-locations',action='store_true')
    a=p.parse_args();run(a.source,a.partition,a.order,a.output,a.body,a.state,a.pixelwise,a.triangle_traces,a.pixel_locations)
