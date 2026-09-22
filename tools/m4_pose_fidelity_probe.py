"""Compare an exact experimental candidate to its verified source pose."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.automation.motion_target_pose import prepare
from autospine_workbench.targets.character43.source_pose_fidelity import inspect


def run(folder,output):
    receipt=json.loads((folder/'report.json').read_bytes());job=receipt['source_job_id']
    import re
    if not re.fullmatch('motion-[a-f0-9]{32}',job):raise ValueError('pose_fidelity_job_invalid')
    raw=(Path('workspace/jobs/motion-intake-v1')/job/'request.json').read_bytes()
    request=json.loads(raw)
    if request.get('clip'):raise ValueError('pose_fidelity_clipped_time_unsupported')
    identity=request['motion_identity'];bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    source=prepare(bundle)
    report=inspect(json.loads(files['skeleton.json']),'external-motion',source['vectors'],source['times'],
                   request.get('projection',{}).get('yaw_degrees',0))
    report.update(candidate_sha256=receipt['candidate_bundle_sha256'],source_job_id=job,
                  request_sha256=sha256(raw).hexdigest(),motion_identity=identity)
    summary={}
    for limb in ('arm','leg'):
        for side in ('left','right'):
            rows=[r for r in report['rows'] if r['limb']==limb and r['side']==side]
            worst=max(rows,key=lambda r:r['endpoint_error_ratio'])
            summary[limb+'_'+side]=dict(samples=len(rows),worst=worst)
            if limb=='leg':summary[limb+'_'+side]['knee_counts']=dict(Counter(r['knee']['status'] for r in rows))
    report['summary']=summary
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(canonical_bytes(report))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
