"""Check explicitly bounded times across every depth pair; preserve full-run failures."""
import argparse
import json
import re
from pathlib import Path
from urllib.request import urlopen
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.automation.motion_local_depth_evidence import publish
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.local_depth_analysis import analyze


def run(job, output, count=9, register=False, sleeve_helpers=None):
    if not re.fullmatch(r'motion-[a-f0-9]{32}', job):
        raise ValueError('invalid_job')
    if type(count) is not int or not 2 <= count <= 33:
        raise ValueError('invalid_sample_count')
    if output.exists():
        raise ValueError('output_exists')
    def current():
        with urlopen('http://127.0.0.1:8918/api/motions/'+job, timeout=60) as response:
            return json.load(response)
    before=current()
    if before['status'] != 'succeeded':
        raise ValueError('candidate_not_complete')
    artifact=before['result']['artifact_sha256']
    root=Path('workspace');folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    files=AnimatedStore(root).read(artifact)
    depth=json.loads(files['motion-depth.json'])
    pairs=depth['pairs']
    if not pairs or any(not p['samples'] for p in pairs):
        raise ValueError('depth_samples_missing')
    lo=max(p['samples'][0]['tick'] for p in pairs)
    hi=min(p['samples'][-1]['tick'] for p in pairs)
    if lo >= hi:
        raise ValueError('depth_common_interval_missing')
    times=[(lo+(hi-lo)*i/(count-1))/1e6 for i in range(count)]
    report=analyze(files,artifact,bundle,request,sample_times=times,sleeve_helpers=sleeve_helpers,
                   on_pair=lambda:print('pair checked',flush=True))
    if current()!=before:
        raise ValueError('candidate_changed')
    with output.open('x',encoding='utf-8') as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2)
    evidence=publish(root,folder,request,artifact,report) if register else None
    return dict(job_id=job,artifact_sha256=artifact,evidence_sha256=evidence,
                counts=report['counts'],requested_sample_times=times,
                scope='bounded_supplement_not_full_clip_validation')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--samples',type=int,default=9)
    parser.add_argument('--register',action='store_true')
    parser.add_argument('--sleeve-helper',action='append',default=[],help='Explicit experimental helper=forearm_l/r')
    args=parser.parse_args()
    pairs=[v.split('=') for v in args.sleeve_helper]
    if len(pairs)>8 or any(len(v)!=2 or not v[0] or v[1] not in ('forearm_l','forearm_r') for v in pairs) or len({v[0] for v in pairs})!=len(pairs):
        parser.error('invalid sleeve helper mapping')
    print(json.dumps(run(args.job,args.output,args.samples,args.register,dict(pairs) or None)))
