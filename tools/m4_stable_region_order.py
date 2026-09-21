"""Try only temporally uniform region orders with existing crossing guards."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build
from autospine_workbench.targets.character43.depth_partition_constraints import build as constraints


def run(folder,output,safe_subset=False,continuity_guard=False):
    if output.exists() and any(output.iterdir()):raise ValueError('stable_region_output_exists_use_new_directory')
    raw=(folder/'skeleton.json').read_bytes();receipt=json.loads((folder/'report.json').read_bytes())
    if sha256(raw).hexdigest()!=receipt['skeleton_sha256']:raise ValueError('stable_region_skeleton')
    observations=json.loads((folder/'observations.json').read_bytes())
    relation=constraints(receipt['partition'],receipt['traces'],observations)
    document=json.loads(raw);pairs=[];eligible=[]
    for pair in relation['pairs']:
        states={r['state'] for r in pair['samples']}-{'N'}
        if states not in ({'F'},{'B'}):continue
        arm,body=pair['region'],pair['body'];front=arm if states=={'F'} else body
        pairs.append(dict(arm_slot=arm,torso_slot=body,evidence_source='uniform_sampled_local_depth',
            samples=[dict(tick=r['time']*1e6,ambiguous=False,current_front_slot=front) for r in pair['samples']]))
        eligible.append(dict(region=arm,body=body,front=front))
    files=AnimatedStore(Path('workspace')).read(receipt['source_artifact_sha256'])
    probe=Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    subset=None;guard=None
    if continuity_guard and pairs:
        from autospine_workbench.targets.character43.depth_order_continuity_guard import build as guarded_build
        from autospine_workbench.targets.character43.depth_partition_continuity import analyze
        source=json.loads(files['skeleton.json'])
        bodies={name:sorted({r['body'] for r in rows}) for name,rows in observations.items()}
        times=sorted({r['time'] for rows in observations.values() for r in rows})
        times=sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
        candidate,guard=guarded_build(document,'external-motion',dict(pairs=pairs),probe,
            lambda c:analyze(source,c,receipt['partition'],files,bodies,times))
        subset=guard['attempts'][-1]['subset'];order=subset['attempts'][-1]
    elif safe_subset and pairs:
        from autospine_workbench.targets.character43.depth_order_subset import build as subset_build
        candidate,subset=subset_build(document,'external-motion',dict(pairs=pairs),probe)
        order=subset['attempts'][-1]
    else:candidate,order=build(document,'external-motion',dict(pairs=pairs),probe,refine_cycles=True)
    report=dict(profile='stable-sampled-region-order-experiment-v1',source_artifact_sha256=receipt['source_artifact_sha256'],
        partition_skeleton_sha256=sha256(raw).hexdigest(),eligible=eligible,order=order,subset=subset,continuity_guard=guard,
        sampled_frames=receipt['sampled_frames'],pixel_budget_used=64_000_000-probe.remaining,
        candidate_status=guard['status'] if guard else subset['status'] if subset else order['status'],
        failure_counts=dict(Counter(r['reason_code'] for r in order['failures'])),
        authority='none',selected=False,scope='sampled_crossing_guard_not_continuous_depth_or_visual_acceptance')
    output.mkdir(parents=True,exist_ok=True)
    if candidate is not None:
        payload=canonical_bytes(candidate);(output/'skeleton.json').write_bytes(payload)
        report['skeleton_sha256']=sha256(payload).hexdigest()
    (output/'report.json').write_bytes(canonical_bytes(report))
    (output/'constraints.json').write_bytes(canonical_bytes(relation))
    print(json.dumps(dict(eligible=len(eligible),status=guard['status'] if guard else order['status'],
        failures=report['failure_counts'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--safe-subset',action='store_true')
    parser.add_argument('--continuity-guard',action='store_true')
    args=parser.parse_args();run(args.folder,args.output,args.safe_subset,args.continuity_guard)
