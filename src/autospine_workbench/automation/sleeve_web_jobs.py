"""Project-scoped background bridge to the resumable sleeve CLI."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import RLock
from .production_submission import child_id
from .pipeline_run import PipelineRunError
from .pipeline_run_validation import require_sha
from .storage_io import directory,publish_document,read_document
from ..manifest_artifacts import require_safe_token
from ..safe_input_files import read_real_file
from . import sleeve_visibility
from .sleeve_process_tree import SleeveProcessTree


class SleeveWebJobs:
    def __init__(self,projects):
        self.projects=projects;self.repo=Path(__file__).resolve().parents[3]
        self.root=Path(projects.state_root)/'jobs/sleeve-web-v1'
        self.output=projects.workspace_root/'tmp/r3s-web';self.drafts=projects.workspace_root/'tmp/r3a-sleeve-reviewed-v2'
        self._lock=RLock();self._jobs={};self._processes={};self._closed=False;self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='sleeve-workflow')

    def _path(self,job):
        if not re.fullmatch(r'job-[a-f0-9]{32}',job):raise PipelineRunError('pipeline_job_id_invalid')
        return directory(self.root/job,create=True)

    def overview(self,project):
        require_safe_token(project,'project');self.projects.get_project(project)
        latest=None
        if self.root.exists():
            for path in sorted(self.root.glob('job-*/request.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True):
                request=read_document(path)
                if request['project_id']==project:
                    try:self._assert_current(request)
                    except (RuntimeError,ValueError,OSError) as exc:
                        reason = getattr(exc, 'reason_code', None)
                        allowed = {'project_snapshot_stale', 'sleeve_draft_changed',
                                   'sleeve_annotation_required', 'sleeve_annotation_source_changed'}
                        latest = dict(schema='autospine.sleeve-web-job/v1',
                            job_id=path.parent.name, project_id=project, status='blocked',
                            authority='none', reason_code=reason if reason in allowed else 'sleeve_source_check_failed')
                        break
                    latest=self.get(project,path.parent.name);break
        from .sleeve_draft_source import available
        return dict(project_id=project,can_build=available(self.projects,self.drafts,project),authority='none',job=latest)

    def has_job(self, project):
        """Any repair history blocks ordinary fallback, regardless of its outcome.

        This is an existence guard, not candidate validation. Do not load annotation
        meshes or compute onboarding readiness merely to answer this question.
        """
        require_safe_token(project, 'project')
        self.projects.get_project(project)
        if self.root.exists():
            directory(self.root)
            for path in self.root.glob('job-*/request.json'):
                if read_document(path)['project_id'] == project:
                    return True
        return False

    def _draft_sha(self,project):
        from .sleeve_draft_source import read
        return sha256(read(self.projects,self.drafts,project)).hexdigest()

    def _assert_current(self,request):
        project=request['project_id']
        if self.projects.get_project(project)['resolved']['sha256']!=request['expected_resolved_sha256']:
            raise PipelineRunError('project_snapshot_stale')
        if self._draft_sha(project)!=request['draft_sha256']:
            raise PipelineRunError('sleeve_draft_changed')

    def submit(self,project,expected_resolved_sha256,expected_draft_sha256=None):
        require_sha(expected_resolved_sha256)
        if not self.overview(project)['can_build']:raise PipelineRunError('sleeve_draft_missing')
        if self.projects.get_project(project)['resolved']['sha256']!=expected_resolved_sha256:raise PipelineRunError('project_snapshot_stale')
        draft_sha=self._draft_sha(project)
        if expected_draft_sha256 is not None and draft_sha!=expected_draft_sha256:
            raise PipelineRunError('sleeve_draft_changed')
        with self._lock:
            if self._closed:raise PipelineRunError('pipeline_manager_closed')
            for job in self._jobs.values():
                if job['project_id']==project and job['status'] in ('pending','running'):return self.get(project,job['job_id'])
            if sum(j['status'] in ('pending','running') for j in self._jobs.values())>=4:raise PipelineRunError('pipeline_queue_full')
            job_id=child_id('job-');root=self._path(job_id)
            job=dict(schema='autospine.sleeve-web-job/v1',job_id=job_id,project_id=project,status='pending',step=None,authority='none')
            request=dict(project_id=project,expected_resolved_sha256=expected_resolved_sha256,draft_sha256=draft_sha)
            publish_document(root/'request.json',request,staging=root/'.staging');self._jobs[job_id]=job
            self._pool.submit(self._execute,job_id,request)
            return sleeve_visibility.view(deepcopy(job),root)

    def _execute(self,job_id,request):
        project=request['project_id'];root=self._path(job_id)
        with self._lock:
            if self._jobs[job_id]['status']=='canceled':return
            self._jobs[job_id]['status']='running'
        try:
            self._assert_current(request)
            from .sleeve_draft_source import read
            from ..benchmark.elbow_target_cli import export
            snapshot = root/'annotation-inputs'
            raw = read(self.projects,self.drafts,project)
            if sha256(raw).hexdigest()!=request['draft_sha256']:raise PipelineRunError('sleeve_draft_changed')
            export(snapshot/project/'draft.json',raw)
            command=[sys.executable,'-u',str(self.repo/'tools/run-sleeve-workflow.py'),project,'--draft-root',str(snapshot),
                '--output',str(self.output),'--state-root',str(self.projects.state_root),'--workspace',str(self.projects.workspace_root)]
            core=self.projects.workspace_root/'tmp/spine43-verification/node_modules/@esotericsoftware/spine-core'
            if core.is_dir():command+=['--runtime-core',str(core)]
            from .sleeve_capture_environment import discover
            command+=discover(self.projects.workspace_root)
            env=dict(os.environ);env['PYTHONPATH']=str(self.repo/'src');final=None
            with (root/'execution.log').open('w',encoding='utf-8') as log:
                with SleeveProcessTree(command,cwd=self.repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace') as tree:
                    process=tree.process
                    with self._lock:
                        self._processes[job_id]=tree
                        if self._jobs[job_id].get('cancel_requested'):tree.terminate()
                        else:tree.release()
                    for line in process.stdout:
                        log.write(line);log.flush()
                        if re.fullmatch(r'[a-z]+(?:-[a-z]+)*: (running|succeeded|cached)\n',line):
                            with self._lock:self._jobs[job_id]['step']=line.strip()
                        if line.startswith('{'):
                            try:
                                final=json.loads(line)
                                if final.get('event')=='stage_plan' and final.get('project_id')==project:
                                    with self._lock:self._jobs[job_id]['stage_ids']=final['stage_ids']
                            except ValueError:pass
                    if process.wait()!=0:raise ValueError('sleeve_workflow_failed')
            self._assert_current(request)
            if not final or final.get('project_id')!=project:raise ValueError('sleeve_result_missing')
            result_path=Path(final['review']).resolve();expected=(self.output/project).resolve()
            if expected not in result_path.parents or result_path.name!='index.html':raise ValueError('sleeve_result_invalid')
            directory(result_path.parent)
            reports=[read_document(p) for p in result_path.parent.glob('*.json')]
            reports=[r for r in reports if r.get('schema')=='autospine.sleeve-workflow/v1' and r.get('project_id')==project
                and r.get('status') in ('needs_review','blocked') and r.get('authority')=='none' and r.get('production_authorized') is False]
            report=next((r for r in reports if r.get('schema')=='autospine.sleeve-workflow/v1' and all(s['cached'] for s in r['steps'])),reports[0])
            publish_document(root/'result-location.json',dict(directory=str(result_path.parent)),staging=root/'.staging')
            with self._lock:
                if not self._jobs[job_id].get('cancel_requested'):self._jobs[job_id].update(status=report['status'],result=report)
        except (OSError,RuntimeError,ValueError,KeyError,IndexError,TypeError) as exc:
            reason=getattr(exc,'reason_code',None) or (str(exc) if re.fullmatch(r'[a-z_]{1,80}',str(exc)) else 'sleeve_workflow_failed')
            with self._lock:self._jobs[job_id].update(status='failed',reason_code=reason)
        finally:
            with self._lock:
                self._processes.pop(job_id,None)
                if self._jobs[job_id].get('cancel_requested'):
                    self._jobs[job_id].update(status='canceled',reason_code='sleeve_job_canceled')
                    self._jobs[job_id].pop('result',None)
                publish_document(root/'result.json',self._jobs[job_id],staging=root/'.staging')

    def cancel(self,project,job_id):
        with self._lock:
            job=self._raw_get(project,job_id)
            if job['status'] not in ('pending','running'):return sleeve_visibility.view(job,self._path(job_id))
            current=self._jobs[job_id];current['cancel_requested']=True
            if current['status']=='pending':
                current.update(status='canceled',reason_code='sleeve_job_canceled')
                root=self._path(job_id);publish_document(root/'result.json',current,staging=root/'.staging')
            if job_id in self._processes:self._processes[job_id].terminate()
            return sleeve_visibility.view(deepcopy(current),self._path(job_id))

    def _raw_get(self,project,job_id):
        root=self._path(job_id);request=read_document(root/'request.json')
        if request['project_id']!=project:raise PipelineRunError('pipeline_job_not_found')
        with self._lock:
            if job_id in self._jobs:return deepcopy(self._jobs[job_id])
        if (root/'result.json').exists():return read_document(root/'result.json')
        return dict(schema='autospine.sleeve-web-job/v1',job_id=job_id,project_id=project,status='failed',authority='none',reason_code='sleeve_job_interrupted')

    def get(self,project,job_id):
        with self._lock:
            return sleeve_visibility.view(self._raw_get(project,job_id),self._path(job_id))

    def set_visibility(self,project,job_id,expected_resolved_sha256,expected_visibility_revision,*,withdrawn):
        require_sha(expected_resolved_sha256)
        if type(expected_visibility_revision) is not int or not 0<=expected_visibility_revision<10000000:
            raise PipelineRunError('pipeline_request_invalid')
        with self._lock:
            job=self._raw_get(project,job_id);root=self._path(job_id)
            request=read_document(root/'request.json')
            if request['expected_resolved_sha256']!=expected_resolved_sha256:
                raise PipelineRunError('project_snapshot_stale')
            self._assert_current(request)
            records=job.get('result',{}).get('records',[])
            candidates=[i for i,r in enumerate(records) if r.get('status')=='candidate_exported' and r.get('download')]
            if job['status']!='needs_review' or not candidates:
                raise PipelineRunError('pipeline_preview_not_ready')
            if not withdrawn:
                for index in candidates:self._download_candidate(job,root,index)
                self._assert_current(request)
            sleeve_visibility.write(root,expected_visibility_revision,withdrawn)
            return self.get(project,job_id)

    def download(self,project,job_id,index):
        with self._lock:
            job=self._raw_get(project,job_id);root=self._path(job_id)
            if sleeve_visibility.read(root)['withdrawn']:raise PipelineRunError('sleeve_candidate_withdrawn')
            self._assert_current(read_document(root/'request.json'))
            return self._download_candidate(job,root,index)

    def review_file(self,project,job_id,parts):
        from .sleeve_review_files import read
        with self._lock:
            job=self._raw_get(project,job_id);job_root=self._path(job_id)
            if sleeve_visibility.read(job_root)['withdrawn']:raise PipelineRunError('sleeve_candidate_withdrawn')
            self._assert_current(read_document(job_root/'request.json'))
            if job['status'] not in ('needs_review','blocked'):raise PipelineRunError('pipeline_preview_not_ready')
            root=directory(Path(read_document(job_root/'result-location.json')['directory'])).resolve()
            if (self.output/project).resolve() not in root.parents:raise PipelineRunError('pipeline_request_invalid')
            return read(root,project,job['result'],parts)

    def _download_candidate(self,job,job_root,index):
        if job['status']!='needs_review':raise PipelineRunError('pipeline_preview_not_ready')
        records=job['result']['records']
        if not 0<=index<len(records) or records[index].get('status')!='candidate_exported' or not records[index]['download']:
            raise PipelineRunError('pipeline_preview_not_ready')
        root=directory(Path(read_document(job_root/'result-location.json')['directory'])).resolve()
        path=root/records[index]['download']
        if root not in path.resolve().parents:raise PipelineRunError('pipeline_request_invalid')
        directory(path.parent);raw=read_real_file(path,32<<20,'sleeve preview')
        files=read_document(root/'receipts/spine.json')['files']
        if files.get(path.relative_to(root/'spine').as_posix())!=sha256(raw).hexdigest():
            raise PipelineRunError('sleeve_cached_output_changed')
        return raw

    def close(self):
        with self._lock:
            self._closed=True
            for job in list(self._jobs.values()):
                if job['status'] in ('pending','running'):self.cancel(job['project_id'],job['job_id'])
        self._pool.shutdown(wait=True)
