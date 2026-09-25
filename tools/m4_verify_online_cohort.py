"""Verify exact online candidates and downloads; never adopt or rebuild a job."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.request import urlopen
from zipfile import ZipFile

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.resolved_project import canonical_sha256


def verify(base, state, label, job):
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job):raise ValueError('invalid_job')
    url=base.rstrip('/')+'/api/motions/'+job
    def get(tail=''):return json.load(urlopen(url+tail,timeout=120))
    before=get()
    if before['kind']!='adapt' or before['status']!='succeeded':raise ValueError('job_not_completed')
    artifact=before['result']['artifact_sha256']
    files=AnimatedStore(state).read(artifact)
    request_raw=(state/'jobs/motion-intake-v1'/job/'request.json').read_bytes()
    request=json.loads(request_raw)
    review=get('/stage-review')
    if review['artifact_sha256']!=artifact or review['readiness']['artifact_sha256']!=artifact:
        raise ValueError('readiness_identity_mismatch')
    raw=urlopen(url+'/download',timeout=120).read()
    with ZipFile(BytesIO(raw)) as archive:
        if len(archive.namelist())!=len(files) or set(archive.namelist())!=set(files):
            raise ValueError('download_inventory_mismatch')
        if any(archive.read(name)!=value for name,value in files.items()):
            raise ValueError('download_bytes_mismatch')
    after=get()
    if canonical_sha256(after)!=canonical_sha256(before):raise ValueError('job_changed_during_verification')
    runtime_raw=(state/'jobs/motion-intake-v1'/job/'runtime/report.json').read_bytes()
    runtime=json.loads(runtime_raw)
    if runtime['bundle_sha256']!=artifact:raise ValueError('runtime_identity_mismatch')
    depth=json.loads(files.get('motion-depth.json',b'{}'))
    return dict(character=label,job_id=job,artifact_sha256=artifact,
        request_sha256=sha256(request_raw).hexdigest(),source_job_id=request['source_job_id'],
        character_sha256=request['character_sha256'],motion_identity=request['motion_identity'],
        strategies={k:request.get(k) for k in ('projection','pose_profile','moving_ankle_profile',
            'torso_projection_profile','depth_review_profile','contact_correction')},
        candidate_status=before['result']['character_animation_status'],
        readiness_status=review['readiness']['status'],
        stages=[dict(stage=r['stage'],status=r['status']) for r in review['readiness']['stages']],
        depth_failure_count=len(depth.get('order',{}).get('failures',[])),
        first_depth_failure=next(iter(depth.get('order',{}).get('failures',[])),None),
        runtime=dict(passed=runtime['passed'],version=runtime.get('runtime_version'),
                     frames=len(runtime.get('results',[])),sha256=sha256(runtime_raw).hexdigest()),
        geometry_passed=before['result']['geometry_passed'],
        zip_sha256=sha256(raw).hexdigest(),zip_files=len(files),all_download_bytes_match=True,
        visual_decision=review.get('current'),visual_applies=review.get('current_applies'),
        player_url=url+'/view/player.html')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8918')
    parser.add_argument('--state',type=Path,default=Path('workspace'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--job',action='append',required=True,help='character=motion-id')
    args=parser.parse_args()
    if args.output.exists():raise ValueError('output_exists')
    pairs=[value.split('=',1) for value in args.job]
    if any(len(p)!=2 for p in pairs) or len({p[0] for p in pairs})!=len(pairs):raise ValueError('invalid_cohort')
    rows=[]
    for label,job in pairs:
        row=verify(args.base,args.state,label,job);rows.append(row)
        print(json.dumps({k:row[k] for k in ('character','job_id','readiness_status','depth_failure_count','zip_files')}),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(profile='online-cohort-delivery-verification-v1',
        rows=rows,authority='none',new_runtime_capture=False,new_visual_acceptance=False),indent=2)+'\n',encoding='utf-8')
