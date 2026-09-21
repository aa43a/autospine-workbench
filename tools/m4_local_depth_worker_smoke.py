"""Resume a single full-clip supplemental-diagnostic worker smoke task."""
import argparse
import json
from pathlib import Path
import time
from autospine_workbench.automation.storage_io import read_document
from m4_motion_cohort import api,save


def run(path):
    base='http://127.0.0.1:8918'
    if path.exists():state=json.loads(path.read_bytes())
    else:
        previous='motion-8ca66333718c4e9698c2de4261be5878'
        request=read_document(Path('workspace/jobs/motion-intake-v1')/previous/'request.json')
        body={k:request[k] for k in ('project_id','character_job_id','contact_correction','projection',
                                   'torso_projection_profile','depth_review_profile') if k in request}
        save(path,dict(submitting=True))
        job=api(base,'/api/motions/'+request['source_job_id']+'/adapt',body)
        state=dict(job_id=job['job_id'],previous_job=previous);save(path,state)
    if 'job_id' not in state:raise ValueError('uncertain_submission_reconcile')
    last=None
    for _ in range(200):
        job=api(base,'/api/motions/'+state['job_id'])
        stage=(job['status'],job.get('step'))
        if stage!=last:print(json.dumps(dict(job_id=state['job_id'],status=stage)),flush=True);last=stage
        if job['status'] not in ('pending','running'):
            state['terminal']=job;save(path,state)
            if job['status']!='succeeded':raise ValueError('worker_did_not_succeed')
            request=read_document(Path('workspace/jobs/motion-intake-v1')/state['job_id']/'request.json')
            evidence=api(base,'/api/motions/'+state['job_id']+'/view/local-depth-status.json')
            if not request.get('local_depth_profile') or not evidence['reports'] or evidence['reports'][0].get('failure'):
                raise ValueError('automatic_diagnostic_missing_or_failed')
            state['diagnostic']=evidence;save(path,state)
            print(json.dumps(dict(artifact=job['result']['artifact_sha256'],reports=len(evidence['reports']))));return
        time.sleep(5)
    raise ValueError('observation_timeout_resume_same_state')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('state',type=Path)
    run(parser.parse_args().state)
