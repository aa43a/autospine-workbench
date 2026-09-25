"""Opt-in real generation cancel/retry probe in a fresh isolated state directory."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time
from types import SimpleNamespace

from autospine_workbench.automation import motion_intake_jobs as jobs_module
from autospine_workbench.automation.motion_generation_jobs import submit
from autospine_workbench.automation.storage_io import canonical_bytes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args();root=args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    handles=[];launch=jobs_module.launch_owned
    def observed_launch(*values):
        process,owner=launch(*values);handles.append(process);return process,owner
    jobs_module.launch_owned=observed_launch
    manager=jobs_module.MotionIntakeJobs(SimpleNamespace(state_root=root/'state',workspace_root=args.workspace.resolve()))
    body=dict(prompt='A person stands still and breathes gently',duration_seconds=1,seed=20260926,diffusion_steps=10,view='front')
    record=dict(profile='real-kimodo-cancel-retry-v1',parameters=body,authority='none',events=[])
    def persist(): (root/'lifecycle.json').write_bytes(canonical_bytes(record))
    def await_state(job, cancel_at_generation=False):
        previous=None;deadline=time.monotonic()+3700;requested=False
        while True:
            current=manager.get(job)
            state=(current['status'],current.get('step'),current.get('cancel_requested'))
            if state!=previous:
                event=dict(job_id=job,status=state[0],step=state[1],cancel_requested=state[2],activity=current.get('activity'))
                record['events'].append(event);persist();print(json.dumps(event),flush=True);previous=state
            if current['status'] not in ('pending','running'):return current
            if cancel_at_generation and current.get('step')=='generate_motion' and not requested:
                # Wait for the actual child log, not merely intent to launch.
                activity=current.get('activity') or {}
                if (activity.get('log_bytes') or 0)>0:
                    manager.cancel(job);requested=True
            if time.monotonic()>deadline:
                manager.cancel(job);raise TimeoutError('probe_deadline')
            time.sleep(.25)
    try:
        first=submit(manager,body);job=first['job_id'];record['original_job_id']=job;persist()
        canceled=await_state(job,True)
        if canceled['status']!='canceled':raise ValueError('generation_finished_before_cancel_or_failed')
        if not handles or handles[-1].poll() is None:raise ValueError('original_worker_still_live')
        original=(manager.folder(job)/'request.json').read_bytes()
        result=(manager.folder(job)/'result.json').read_bytes()
        retry=manager.retry(job);new=retry['job_id'];record['retry_job_id']=new;persist()
        if new==job:raise ValueError('retry_reused_identity')
        final=await_state(new)
        if (manager.folder(job)/'request.json').read_bytes()!=original or (manager.folder(job)/'result.json').read_bytes()!=result:
            raise ValueError('old_record_changed')
        request=json.loads((manager.folder(new)/'request.json').read_bytes())
        assert request['generation']==body
        assert request['retry_of']==dict(job_id=job,request_sha256=sha256(original).hexdigest())
        record.update(final_status=final['status'],reason=final.get('reason_code'),old_records_unchanged=True,
                      original_worker_exited=handles[0].poll() is not None,retry_of=request['retry_of'])
        if final['status']=='succeeded':
            preview=manager.preview(new)
            from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
            identity=final['result']['motion']
            bundle=VerifiedMotionBundleReader(root/'state').load(identity['clip_sha256'],identity['bundle_sha256'])
            if sha256(bundle.raw_npz).hexdigest()!=final['source_sha256']:
                raise ValueError('generated_source_identity_changed')
            record.update(preview_sha256=sha256(preview).hexdigest(),generation=final['result'].get('generation'),
                          source_sha256=final.get('source_sha256'),verified_motion_identity=identity)
        reopened=jobs_module.MotionIntakeJobs(SimpleNamespace(state_root=root/'state',workspace_root=args.workspace.resolve()))
        try:
            record['reopened_statuses']=[reopened.get(job)['status'],reopened.get(new)['status']]
            if final['status']=='succeeded':
                record['reopened_preview_matches']=sha256(reopened.preview(new)).hexdigest()==record['preview_sha256']
        finally:reopened.close()
        persist();print(json.dumps({k:v for k,v in record.items() if k not in ('events','generation')}),flush=True)
    finally:
        manager.close();jobs_module.launch_owned=launch


if __name__=='__main__':main()
