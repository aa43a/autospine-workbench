"""Compare exact baseline and registered experiments against the same source."""
import argparse
from collections import Counter
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document,canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.knee_projection import inspect


def run(job,experiment,output):
    import re
    if not re.fullmatch('motion-[a-f0-9]{32}',job):raise ValueError('job_invalid')
    root=Path('workspace');request=read_document(root/'jobs/motion-intake-v1'/job/'request.json')
    value=json.loads(AnimatedStore(root).read_file(experiment,'experiment.json'))
    from autospine_workbench.resolved_project import canonical_sha256
    if value['request_sha256']!=canonical_sha256(request):raise ValueError('experiment_request_mismatch')
    identity=request['motion_identity'];bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    vectors,_,_=extract(bundle)
    keys=next(t for t in bundle.motion['tracks'] if t['property']=='rotation')['keys']
    times=[k['tick']/bundle.motion['ticks_per_second'] for k in keys]
    results={}
    for label,address in [('baseline',value['baseline_sha256']),('experiment',value['report']['candidate_bundle_sha256'])]:
        files=AnimatedStore(root).read(address);document=json.loads(files['skeleton.json'])
        checked=inspect(document,'external-motion',vectors,times)
        results[label]=dict(artifact_sha256=address,**checked)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as handle:handle.write(canonical_bytes(dict(job_id=job,experiment=experiment,results=results)))
    print(json.dumps({k:dict(Counter(r['status'] for r in v['rows'])) for k,v in results.items()}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job');p.add_argument('experiment');p.add_argument('output',type=Path)
    a=p.parse_args();run(a.job,a.experiment,a.output)
