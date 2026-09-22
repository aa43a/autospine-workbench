"""Extract conservative continuous front boundaries from verified Reach depth evidence."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.hand_depth_observation import observe
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.character43.weighted_depth_interval import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.depth_clip_contour import extract
from autospine_workbench.targets.spine43.seam_raster import texture


def run(source,evidence,output,arm,side='front'):
    if side not in ('front','back'):raise ValueError('clip_side_invalid')
    receipt=json.loads((source/'report.json').read_bytes());raw=evidence.read_bytes();depth=json.loads(raw)
    digest=receipt['candidate_bundle_sha256']
    if depth['candidate_bundle_sha256']!=digest or depth['source_identity']!=receipt['source_identity']:
        raise ValueError('clip_depth_identity_mismatch')
    files=AnimatedStore(source/'isolated-store').read(digest);document=json.loads(files['skeleton.json'])
    identity=receipt['source_identity'];bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh':raise ValueError('clip_source_adapter_not_implemented')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,depth['yaw_degrees'])
    pairs=[p for p in depth['pairs'] if p['arm_slot']==arm]
    if len(pairs)!=1:raise ValueError('clip_unique_pair_required')
    mesh=document['skins'][0]['attachments'][arm][arm]
    axes=infer(document,mesh,texture(files['images/'+mesh.get('path',arm)+'.png']))
    rows=[]
    for original in pairs[0]['samples']:
        for row in (original,original.get('interval_sample')):
            if row is None:continue
            check=row['local_check'];time=row['tick']/1e6
            if 'reference_plane' not in check:raise ValueError('clip_reference_plane_missing')
            segments=sampler(row['source_tick']);hands=observe(sampler,row['source_tick'],full_hand=True)
            segments.update(hands['segments']);lengths={n:a['length'] for n,a in axes['axes'].items() if n in hands['segments']}
            intervals=build(document,mesh,segments,axis_lengths=lengths)['intervals']
            points=sample(document,'external-motion',time)[0][arm]
            dx,dy,offset=check['reference_plane'];margin=check['margin']
            values=[None if v is None else v[0]-dx*p[0]-dy*p[1]-offset-margin for p,v in zip(points,intervals)]
            if side=='back':values=[None if v is None else -v for v in values]
            try:
                contour=extract(points,mesh['triangles'],values)
                status='single_loop' if len(contour['loops'])==1 else 'empty' if not contour['loops'] else 'multiple_loops'
            except ValueError as error:
                contour=dict(loops=[]);status=str(error)
            rows.append(dict(time=time,status=status,margin=margin,**contour))
    report=dict(candidate=digest,source_identity=identity,depth_sha256=sha256(raw).hexdigest(),arm=arm,side=side,rows=rows,
                statuses=dict(Counter(r['status'] for r in rows)),authority='none',selected=False,
                scope='positive_lower_bound_proxy_contours_not_interpolated_clipping_or_visual_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False)
    print(json.dumps(dict(statuses=report['statuses'],loop_vertex_counts=dict(Counter(len(loop['points']) for r in rows for loop in r['loops'])))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','evidence','output'):parser.add_argument(name,type=Path)
    parser.add_argument('--arm',required=True);parser.add_argument('--side',choices=('front','back'),default='front')
    args=parser.parse_args();run(args.source,args.evidence,args.output,args.arm,args.side)
