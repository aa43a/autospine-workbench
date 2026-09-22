"""Check exact reach source/midpoint depth and all crossed visible slot constraints."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.torso_depth_refinement import Checker
from autospine_workbench.targets.character43.motion_depth_order import build


def evidence(check,tick,source_tick,arm,body,fallback):
    status=check['status'];front={'uniform_front_proxy':arm,'uniform_back_proxy':body}.get(status,fallback)
    return dict(tick=tick,source_tick=source_tick,current_front_slot=front,
                ambiguous=status not in ('uniform_front_proxy','uniform_back_proxy','no_overlap'),
                support=status,local_check=check)


def run(root,depth_root,output,index):
    output.mkdir(parents=True,exist_ok=False)
    item=json.loads((root/'comparison.json').read_bytes())['rows'][index]
    depth=json.loads((depth_root/(str(index)+'.json')).read_bytes());digest=depth['candidate_bundle_sha256']
    if digest!=item['views'][1]['artifact'] or depth['yaw_degrees']!=item['views'][1]['yaw']:
        raise ValueError('held_order_candidate_view_mismatch')
    files=AnimatedStore(root/str(index)/'isolated-store').read(digest);doc=json.loads(files['skeleton.json'])
    identity=depth['source_identity'];bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind=='kimodo_npz':
        sampler=KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,bundle.kimodo_map,
                                  depth['yaw_degrees'],interpolation='linear_observed_positions')
    else:sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,depth['yaw_degrees'])
    checked=deepcopy(depth);checked['strict_interval_evidence']=True;counts=Counter()
    probe=Probe(doc,files,'external-motion',tiled=True,rendered_bounds=True,sparse='priority_depth_points')
    checker=Checker(probe,sampler,pixelwise=True)
    for pair in checked['pairs']:
        arm,body=pair['arm_slot'],pair['torso_slot'];samples=pair['samples'];fresh=[]
        for i,row in enumerate(samples):
            times=[(row['tick'],row['source_tick'])]
            if i+1<len(samples):
                following=samples[i+1]
                times.append(((row['tick']+following['tick'])/2,(row['source_tick']+following['source_tick'])/2))
            values=[]
            for tick,source_tick in times:
                try:check=checker.check(arm,body,tick/1e6,source_tick)
                except ValueError as exc:check=dict(status='unmeasured',reason=str(exc),time=tick/1e6)
                counts[check['status']]+=1
                values.append(evidence(check,tick,source_tick,arm,body,pair['setup_front_slot']))
            sample=dict(row,**values[0])
            if len(values)>1:sample['interval_sample']=values[1]
            fresh.append(sample)
        pair.update(samples=fresh,evidence_source='same_view_torso_plane_hand_interval_proxy')
        print(json.dumps(dict(stage='local_depth_complete',pair=[arm,body],counts=dict(counts))),flush=True)
    (output/'depth.json').write_text(json.dumps(checked,ensure_ascii=False),encoding='utf-8')
    proposed,order=build(doc,'external-motion',checked,probe)
    if proposed is not None:
        (output/'skeleton-candidate.json').write_text(json.dumps(proposed),encoding='utf-8')
    report=dict(authority='none',selected=False,character=item['label'],candidate=digest,
                source_identity=identity,yaw=depth['yaw_degrees'],counts=dict(counts),order=order,
                candidate_available=proposed is not None,pixel_budget_used=64_000_000-probe.remaining,
                failure_counts=dict(Counter(f['reason_code'] for f in order['failures'])),
                scope='source_and_midpoint_proxy_order_constraints_not_runtime_or_visual_acceptance')
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('order','source_identity')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','depth_root','output'):p.add_argument(name,type=Path)
    p.add_argument('--index',type=int,default=0)
    a=p.parse_args();run(a.root,a.depth_root,a.output,a.index)
