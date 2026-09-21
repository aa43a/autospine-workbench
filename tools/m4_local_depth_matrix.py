"""Resume full frozen matrix diagnostics without rebuilding or replacing candidates."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document,canonical_bytes
from autospine_workbench.automation.motion_local_depth_evidence import publish
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.local_depth_analysis import analyze,PROFILE
from m4_motion_cohort import api,digest,save


def run(plan_path,cohort_path,output,limit):
    plan=json.loads(plan_path.read_bytes());cohort=json.loads(cohort_path.read_bytes())
    if cohort['plan_sha256']!=digest(plan):raise ValueError('matrix_plan_identity')
    output.mkdir(parents=True,exist_ok=True);state_path=output/'state.json'
    identity=dict(plan_sha256=digest(plan),cohort_sha256=sha256(cohort_path.read_bytes()).hexdigest(),profile=PROFILE)
    state=json.loads(state_path.read_bytes()) if state_path.exists() else dict(identity=identity,cells={})
    if state['identity']!=identity:raise ValueError('matrix_resume_identity')
    root=Path('workspace');done=0
    for motion in plan['motions']:
        for character in plan['characters']:
            key=motion['id']+'/'+character['id'];frozen=cohort['cells'][key]
            job=frozen['job_id'];artifact=frozen['result']['artifact_sha256']
            if key in state['cells']:
                stored=state['cells'][key]
                raw=(output/stored['file']).read_bytes()
                if stored['artifact_sha256']!=artifact or sha256(raw).hexdigest()!=stored['report_sha256']:
                    raise ValueError('matrix_checkpoint_changed')
                continue
            if done>=limit:return state
            current=api('http://127.0.0.1:8918','/api/motions/'+job)
            if current['status']!='succeeded' or current['result']['artifact_sha256']!=artifact:
                raise ValueError('matrix_candidate_changed')
            folder=root/'jobs/motion-intake-v1'/job;request=read_document(folder/'request.json')
            if (request['character_sha256']!=character['sha256'] or
                    request['source_job_id']!=cohort['sources'][motion['id']]['job_id']):
                raise ValueError('matrix_request_identity')
            source=api('http://127.0.0.1:8918','/api/motions/'+request['source_job_id'])
            if source['source_sha256']!=motion['sha256']:raise ValueError('matrix_raw_source_changed')
            files=AnimatedStore(root).read(artifact);address=request['motion_identity']
            bundle=VerifiedMotionBundleReader(root).load(address['clip_sha256'],address['bundle_sha256'])
            print(json.dumps(dict(started=key,job_id=job)),flush=True)
            report=analyze(files,artifact,bundle,request,pixelwise=True,
                           on_pair=lambda:print(json.dumps(dict(progress=key)),flush=True))
            raw=canonical_bytes(report);name=key.replace('/','--')+'.json'
            (output/name).write_bytes(raw)
            evidence=publish(root,folder,request,artifact,report)
            state['cells'][key]=dict(job_id=job,artifact_sha256=artifact,file=name,
                report_sha256=sha256(raw).hexdigest(),evidence_sha256=evidence,
                counts=report['counts'],causes=report['causes'],pixel_budget_used=report['pixel_budget_used'])
            save(state_path,state);done+=1
            from m4_local_depth_matrix_review import render
            (output/'index.html').write_text(render(plan,state),encoding='utf-8')
            print(json.dumps(dict(completed=key,counts=report['counts'],total=len(state['cells']))),flush=True)
    return state


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path);parser.add_argument('cohort',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--limit',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.limit<=24:raise ValueError('matrix_limit')
    run(args.plan,args.cohort,args.output,args.limit)
