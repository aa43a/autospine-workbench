"""Replay source-bound depth fields between keys, independently of clip interpolation."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.motion_depth import build as depth_schedule
from autospine_workbench.targets.character43.hand_depth_observation import observe
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.character43.weighted_depth_interval import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.spine43.seam_raster import texture
from m4_torso_reference_reader import load


def run(source,origin,output,arm,body,subdivisions=4):
    if type(subdivisions) is not int or not 1<=subdivisions<=8:
        raise ValueError('depth_field_sample_budget')
    receipt=json.loads((source/'report.json').read_bytes());identity=receipt['source_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh':raise ValueError('depth_field_adapter_not_implemented')
    parent=receipt['source_candidate_sha256']
    parent_doc=json.loads(AnimatedStore(origin/'isolated-store').read(parent)['skeleton.json'])
    files,document,digest,plane=load(source,parent,parent_doc,bundle,identity,receipt['yaw_degrees'])
    bvh=parse_bvh(bundle.raw_bvh);sampler=SegmentDepthSampler(bvh,bundle.bvh_map,receipt['yaw_degrees'])
    schedule=depth_schedule(document,bvh,bundle.bvh_map,yaw_degrees=receipt['yaw_degrees'])
    pairs=[p for p in schedule['pairs'] if p['arm_slot']==arm and p['torso_slot']==body]
    if len(pairs)!=1:raise ValueError('depth_field_pair_missing')
    rows=pairs[0]['samples'];times=[]
    for i,row in enumerate(rows):
        times.append((row['tick'],row['source_tick']))
        if i+1<len(rows):
            following=rows[i+1]
            times.extend((row['tick']+(following['tick']-row['tick'])*j/subdivisions,
                          row['source_tick']+(following['source_tick']-row['source_tick'])*j/subdivisions)
                         for j in range(1,subdivisions))
    attachment=document['skins'][0]['attachments'][arm][arm]
    axes=infer(document,attachment,texture(files['images/'+attachment.get('path',arm)+'.png']))
    output_rows=[]
    for tick,source_tick in times:
        time=tick/1e6;segments=sampler(source_tick);hands=observe(sampler,source_tick,full_hand=True)
        segments.update(hands['segments'])
        lengths={n:a['length'] for n,a in axes['axes'].items() if n in hands['segments']}
        intervals=build(document,attachment,segments,axis_lengths=lengths)['intervals']
        vertices=sample(document,'external-motion',time)[0][arm]
        dx,dy,offset=plane(document,'external-motion',time,sampler,source_tick)['coefficients']
        values=[None if interval is None else interval[0]-dx*p[0]-dy*p[1]-offset-.02
                for p,interval in zip(vertices,intervals)]
        output_rows.append(dict(time=time,source_tick=source_tick,vertices=vertices,depth_values=values,
                                margin=.02,reference_plane=[dx,dy,offset]))
    report=dict(candidate=digest,origin_parent=parent,arm=arm,body=body,side='front',source_identity=identity,
                rows=output_rows,subdivisions=subdivisions,authority='none',selected=False,
                replayed_torso_bake=True,unknown_vertex_samples=sum(v is None for r in output_rows for v in r['depth_values']),
                source_receipt_sha256=sha256((source/'report.json').read_bytes()).hexdigest(),
                scope='replayed_source_proxy_field_not_measured_surface_or_visual_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,allow_nan=False)
    print(json.dumps(dict(candidate=digest,frames=len(output_rows),unknown_vertex_samples=report['unknown_vertex_samples'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','origin','output'):parser.add_argument(name,type=Path)
    parser.add_argument('--arm',required=True);parser.add_argument('--body',required=True)
    parser.add_argument('--subdivisions',type=int,default=4)
    a=parser.parse_args();run(a.source,a.origin,a.output,a.arm,a.body,a.subdivisions)
