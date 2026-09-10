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
from uuid import uuid4
from .pipeline_run import PipelineRunError
from .pipeline_run_validation import require_sha
from .storage_io import directory,publish_document,read_document
from ..manifest_artifacts import require_safe_token
from ..safe_input_files import read_real_file
from . import sleeve_visibility


class SleeveWebJobs:
    def __init__(self,projects):
        self.projects=projects;self.repo=Path(__file__).resolve().parents[3]
        self.root=Path(projects.state_root)/'jobs/sleeve-web-v1'
        self.output=projects.workspace_root/'tmp/r3s-web';self.drafts=projects.workspace_root/'tmp/r3a-sleeve-reviewed-v2'
        self._lock=RLock();self._jobs={};self._closed=False;self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='sleeve-workflow')

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
                    except (RuntimeError,ValueError,OSError):break
                    latest=self.get(project,path.parent.name);break
        return dict(project_id=project,can_build=(self.drafts/project/'draft.json').is_file(),authority='none',job=latest)

    def _draft_sha(self,project):
        return sha256(read_real_file(self.drafts/project/'draft.json',16<<20,'sleeve draft')).hexdigest()

    def _assert_current(self,request):
        project=request['project_id']
        if self.projects.get_project(project)['resolved']['sha256']!=request['expected_resolved_sha256']:
            raise PipelineRunError('project_snapshot_stale')
        if self._draft_sha(project)!=request['draft_sha256']:
            raise PipelineRunError('sleeve_draft_changed')

    def submit(self,project,expected_resolved_sha256):
        require_sha(expected_resolved_sha256)
        if not self.overview(project)['can_build']:raise PipelineRunError('sleeve_draft_missing')
        if self.projects.get_project(project)['resolved']['sha256']!=expected_resolved_sha256:raise PipelineRunError('project_snapshot_stale')
        with self._lock:
            if self._closed:raise PipelineRunError('pipeline_manager_closed')
            for job in self._jobs.values():
                if job['project_id']==project and job['status'] in ('pending','running'):return self.get(project,job['job_id'])
            if sum(j['status'] in ('pending','running') for j in self._jobs.values())>=4:raise PipelineRunError('pipeline_queue_full')
            job_id='job-'+uuid4().hex;root=self._path(job_id)
            job=dict(schema='autospine.sleeve-web-job/v1',job_id=job_id,project_id=project,status='pending',step=None,authority='none')
            request=dict(project_id=project,expected_resolved_sha256=expected_resolved_sha256,draft_sha256=self._draft_sha(project))
            publish_document(root/'request.json',request,staging=root/'.staging');self._jobs[job_id]=job
            self._pool.submit(self._execute,job_id,request)
            return sleeve_visibility.view(deepcopy(job),root)

    def _execute(self,job_id,request):
        project=request['project_id'];root=self._path(job_id)
        with self._lock:self._jobs[job_id]['status']='running'
        try:
            self._assert_current(request)
            command=[sys.executable,'-u',str(self.repo/'tools/run-sleeve-workflow.py'),project,'--draft-root',str(self.drafts),
                '--output',str(self.output),'--state-root',str(self.projects.state_root),'--workspace',str(self.projects.workspace_root)]
            core=self.projects.workspace_root/'tmp/spine43-verification/node_modules/@esotericsoftware/spine-core'
            if core.is_dir():command+=['--runtime-core',str(core)]
            from .sleeve_capture_environment import discover
            command+=discover(self.projects.workspace_root)
            env=dict(os.environ);env['PYTHONPATH']=str(self.repo/'src');final=None
            with (root/'execution.log').open('w',encoding='utf-8') as log:
                with subprocess.Popen(command,cwd=self.repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace') as process:
                    for line in process.stdout:
                        log.write(line);log.flush()
                        if re.fullmatch(r'[a-z]+: (running|succeeded|cached)\n',line):
                            with self._lock:self._jobs[job_id]['step']=line.strip()
                        if line.startswith('{'):
                            try:final=json.loads(line)
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
            with self._lock:self._jobs[job_id].update(status=report['status'],result=report)
        except (OSError,RuntimeError,ValueError,KeyError,IndexError,TypeError) as exc:
            reason=getattr(exc,'reason_code',None) or (str(exc) if re.fullmatch(r'[a-z_]{1,80}',str(exc)) else 'sleeve_workflow_failed')
            with self._lock:self._jobs[job_id].update(status='failed',reason_code=reason)
        finally:
            with self._lock:publish_document(root/'result.json',self._jobs[job_id],staging=root/'.staging')

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
        with self._lock:self._closed=True
        self._pool.shutdown(wait=True)
