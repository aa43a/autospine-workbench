"""Source-bound visibility continuity check of an isolated draw-order candidate."""
import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_partition_continuity import analyze


def run(partition_folder,order_folder,output):
    base_raw=(partition_folder/'skeleton.json').read_bytes();candidate_raw=(order_folder/'skeleton.json').read_bytes()
    receipt=json.loads((partition_folder/'report.json').read_bytes());order=json.loads((order_folder/'report.json').read_bytes())
    if (sha256(base_raw).hexdigest()!=receipt['skeleton_sha256'] or
        sha256(candidate_raw).hexdigest()!=order['skeleton_sha256'] or order['partition_skeleton_sha256']!=receipt['skeleton_sha256']
        or order['source_artifact_sha256']!=receipt['source_artifact_sha256']):raise ValueError('continuity_candidate_identity')
    candidate=json.loads(candidate_raw);base=json.loads(base_raw);stripped=deepcopy(candidate)
    stripped['animations']['external-motion'].pop('drawOrder',None)
    if stripped!=base:raise ValueError('continuity_non_order_change')
    files=AnimatedStore(Path('workspace')).read(receipt['source_artifact_sha256']);source=json.loads(files['skeleton.json'])
    observations=json.loads((partition_folder/'observations.json').read_bytes())
    bodies={name:sorted({r['body'] for r in rows}) for name,rows in observations.items()}
    depth=json.loads(files['motion-depth.json']);ticks=sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    times=sorted({t/1e6 for t in ticks}|{(a+(b-a)*i/4)/1e6 for a,b in zip(ticks,ticks[1:]) for i in (1,2,3)})
    result=analyze(source,candidate,receipt['partition'],files,bodies,times)
    result.update(source_artifact_sha256=receipt['source_artifact_sha256'],candidate_skeleton_sha256=order['skeleton_sha256'],
        partition_receipt_sha256=sha256((partition_folder/'report.json').read_bytes()).hexdigest())
    output.write_bytes(canonical_bytes(result))
    print(json.dumps(dict(status=result['status'],records=len(result['records']),work=result['work_used'],
        front_regions=dict(Counter(r['front_region'] for r in result['records'])))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('partition','order','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.partition,args.order,args.output)
