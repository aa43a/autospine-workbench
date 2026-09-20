"""Evaluate a source-bound local depth proxy at recorded straddle failures."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_depth import _source
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_depth_proxy import overlap_support
from autospine_workbench.resolved_project import canonical_sha256


def analyze(request,result,state_root,*,endpoint_caps=False,sample_limit=16):
    if type(sample_limit) is not int or not 1 <= sample_limit <= 2048:
        raise ValueError('depth_proxy_sample_limit_invalid')
    files=AnimatedStore(state_root).read(result['result']['artifact_sha256'])
    document=json.loads(files['skeleton.json']); depth=json.loads(files['motion-depth.json'])
    identity=request['motion_identity']
    evidence=json.loads(files['motion-review.json'])
    if (evidence['character_sha256']!=request['character_sha256']
            or evidence['motion_bundle_sha256']!=identity['bundle_sha256']
            or depth.get('yaw_degrees')!=request.get('projection',{}).get('yaw_degrees')):
        raise ValueError('depth_proxy_candidate_mismatch')
    bundle=VerifiedMotionBundleReader(state_root).load(identity['clip_sha256'],identity['bundle_sha256'])
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    kimodo=(bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind=='kimodo_npz' else None
    bvh=None if kimodo else parse_bvh(bundle.raw_bvh)
    frames,length,source_sha=_source(bvh,mapping,kimodo,request.get('projection',{}).get('yaw_degrees'))
    if source_sha!=depth['source_sha256'] or canonical_sha256(mapping)!=depth['map_sha256']:
        raise ValueError('depth_proxy_source_mismatch')
    roles={r['role']:r for r in mapping['bones']}
    all_failures=[f for f in depth.get('order',{}).get('failures',[]) if f['reason_code']=='visible_depth_straddle']
    records=[]
    for failure in all_failures[:sample_limit]:
        pair=next(p for p in depth['pairs'] if [p['arm_slot'],p['torso_slot']]==failure['pair'])
        row=next(s for s in pair['samples'] if abs(s['tick']/1e6-failure['time'])<1e-7)
        # Midpoint overlap cannot use preceding-frame source depth.
        if abs(failure['overlap']['time']-failure['time'])>1e-7:
            records.append(dict(time=failure['time'],status='midpoint_depth_unmeasured')); continue
        joints=next(joints for tick,joints in frames if tick==row['source_tick'])
        reference=joints[roles['humanoid.spine.upper']['joint_name']]; segments={}
        for side,suffix in [('left','l'),('right','r')]:
            for part,bone in [('upper','upperarm'),('lower','forearm')]:
                role=roles.get('humanoid.arm.'+part+'.'+side)
                if not role: continue
                aim=role.get('aim',{}).get('joint_name') or role.get('aim_joint_name')
                if aim in joints:
                    segments[bone+'_'+suffix]=tuple((joints[n]-reference)/length for n in (role['joint_name'],aim))
        probe=Probe(document,files,'external-motion',pixel_budget=8_000_000)
        value=overlap_support(probe,*failure['pair'],failure['time'],segments,endpoint_caps=endpoint_caps)
        records.append(dict(value,source_tick=row['source_tick'],segments=segments))
    return dict(profile='local-depth-probe-v1',artifact_sha256=result['result']['artifact_sha256'],
                source_identity=identity,request_sha256=canonical_sha256(request),records=records,
                total_straddle_failures=len(all_failures),sample_limit=sample_limit,
                complete_failure_inventory=len(all_failures)<=sample_limit,
                endpoint_caps=endpoint_caps,authority='none',selected=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output',type=Path)
    parser.add_argument('--endpoint-caps',action='store_true')
    parser.add_argument('--sample-limit',type=int,default=16)
    args=parser.parse_args(); root=Path('workspace'); folder=root/'jobs/motion-intake-v1'/args.job
    if folder.parent!=root/'jobs/motion-intake-v1' or not args.job.startswith('motion-'):
        raise ValueError('job_invalid')
    report=analyze(read_document(folder/'request.json'),read_document(folder/'result.json'),root,
                   endpoint_caps=args.endpoint_caps,sample_limit=args.sample_limit)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    from collections import Counter
    print(json.dumps(dict(total=report['total_straddle_failures'],evaluated=len(report['records']),
                          statuses=dict(Counter(r['status'] for r in report['records'])))))


if __name__=='__main__':main()
