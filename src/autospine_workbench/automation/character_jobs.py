"""Durable project composition jobs with source-bound downloads and cancellation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re
import json
from threading import Event, RLock
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256
from .animated_application import AnimatedApplication
from .animated_input_index import inspect_registration
from .character_composition import build_character
from .character_capture import capture, review_name
from .character_ordinary import route_source
from .pipeline_run import PipelineRunError
from .pipeline_run_validation import require_sha
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.character-web-job/v1'
ACTIVE = {'pending', 'running'}


class CharacterJobs:
    def __init__(self, projects, sleeves, *, application=None, builder=build_character, capturer=capture):
        self.projects = projects; self.sleeves = sleeves
        self.application = application or AnimatedApplication(projects); self.builder = builder
        self.capturer = capturer
        self.root = Path(projects.state_root) / 'jobs/character-web-v1'
        self._lock = RLock(); self._active = {}; self._closed = False
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='character-build')

    def _path(self, job, create=False):
        if not isinstance(job, str) or not re.fullmatch(r'job-[a-f0-9]{32}', job):
            raise PipelineRunError('pipeline_job_id_invalid')
        return directory(self.root / job, create=create)

    def _current(self, request):
        from .character_order_review import overview as order_overview
        if order_overview(self, request['project_id'])['head_sha256'] != request.get('order_decisions_sha256'):
            raise PipelineRunError('character_order_decisions_changed')
        from .character_component_mounts import overview as mount_overview
        if mount_overview(self,request['project_id'])['head_sha256'] != request.get('component_mounts_sha256'):
            raise PipelineRunError('character_mount_decisions_changed')
        from .character_final_regions import overview as final_overview
        if final_overview(self,request['project_id'],stage='after_components')['head_sha256']!=request.get('post_component_regions_sha256'):
            raise PipelineRunError('character_final_decisions_changed')
        if final_overview(self,request['project_id'])['head_sha256']!=request.get('final_region_decisions_sha256'):
            raise PipelineRunError('character_final_decisions_changed')
        from .character_motion_catalog import validate as validate_motion
        validate_motion(self, request)
        from .character_region_decisions import overview as region_overview
        if region_overview(self, request['project_id'])['head_sha256'] != request.get('region_decisions_sha256'):
            raise PipelineRunError('character_region_decisions_changed')
        info = inspect_registration(self.projects, request['project_id'])
        if info['source_addresses']['resolved_project_sha256'] != request['expected_resolved_sha256'] \
                or info['source_addresses']['input_identity_sha256'] != request['expected_input_sha256']:
            raise PipelineRunError('project_snapshot_stale')
        if request['sleeve_job_id'] is None:
            digest=route_source(self.projects,self.sleeves,request['project_id'],request['expected_resolved_sha256'])
            if digest!=request.get('route_choice_sha256'): raise PipelineRunError('character_route_changed')
            return info
        job = self.sleeves.get(request['project_id'], request['sleeve_job_id'])
        if job['status'] != 'needs_review' or job.get('candidate_withdrawn'):
            raise PipelineRunError('character_sleeve_unavailable')
        source = read_document(self.sleeves._path(request['sleeve_job_id']) / 'request.json')
        if source['project_id'] != request['project_id']:
            raise PipelineRunError('pipeline_job_not_found')
        self.sleeves._assert_current(source)
        return info

    def overview(self, project):
        require_safe_token(project, 'project'); self.projects.get_project(project)
        sleeve = self.sleeves.overview(project).get('job')
        result = dict(project_id=project, authority='none', can_build=False, sleeve_job_id=None, job=None, reason_code=None,
                      motion_rebuild_with_region_revalidation=True)
        from .character_region_decisions import overview as region_overview
        result['region_exclusions'] = region_overview(self, project)
        from .character_final_regions import overview as final_overview
        result['final_region_exclusions'] = final_overview(self,project)
        result['post_component_regions'] = final_overview(self,project,stage='after_components')
        from .character_component_mounts import overview as mount_overview
        result['component_mounts'] = mount_overview(self,project)
        from .character_order_review import overview as order_overview
        result['order_review'] = order_overview(self, project)
        try:
            info = inspect_registration(self.projects, project)
            from .character_motion_catalog import choices
            result['motion_choices'] = choices(self, project, info['source_addresses'])
            result.update(expected_resolved_sha256=info['source_addresses']['resolved_project_sha256'],
                          expected_input_sha256=info['source_addresses']['input_identity_sha256'])
            if sleeve and sleeve['status'] == 'needs_review' and not sleeve.get('candidate_withdrawn'):
                result.update(sleeve_job_id=sleeve['job_id'], can_build=any(
                    r['status']=='candidate_exported' for r in sleeve.get('result', {}).get('records', [])))
            elif sleeve is None:
                route_source(self.projects,self.sleeves,project,result['expected_resolved_sha256'])
                result.update(can_build=True,mode='ordinary')
            if not result['can_build']: result['reason_code']='character_sleeve_unavailable'
        except (ValueError, RuntimeError) as exc:
            result['reason_code']=getattr(exc, 'reason_code', 'character_source_unavailable')
        if self.root.exists():
            for file in sorted(self.root.glob('job-*/request.json'), key=lambda p:p.stat().st_mtime_ns, reverse=True):
                if read_document(file)['project_id'] == project:
                    result['job'] = self.get(project, file.parent.name); break
        return result

    def submit(self, project, expected_resolved_sha256, expected_input_sha256, sleeve_job_id, motion_choice_id=None,
               residual_texture_profile=None, skirt_profile=None, shoulder_regions=None):
        from .character_shoulder_trial import validate as validate_shoulder
        validate_shoulder(shoulder_regions)
        from .character_texture_trial import validate
        validate(residual_texture_profile)
        from .character_skirt_trial import validate as validate_skirt
        validate_skirt(skirt_profile)
        require_safe_token(project, 'project'); require_sha(expected_resolved_sha256); require_sha(expected_input_sha256)
        request=dict(project_id=project, expected_resolved_sha256=expected_resolved_sha256,
                     expected_input_sha256=expected_input_sha256, sleeve_job_id=sleeve_job_id)
        from .character_region_decisions import overview as region_overview
        request['region_decisions_sha256'] = region_overview(self, project)['head_sha256']
        from .character_final_regions import overview as final_overview
        post_head=final_overview(self,project,stage='after_components')['head_sha256']
        if post_head is not None: request['post_component_regions_sha256']=post_head
        final_head=final_overview(self,project)['head_sha256']
        if final_head is not None: request['final_region_decisions_sha256']=final_head
        from .character_component_mounts import overview as mount_overview
        mount_head=mount_overview(self,project)['head_sha256']
        if mount_head is not None: request['component_mounts_sha256']=mount_head
        from .character_order_review import overview as order_overview
        order_head = order_overview(self, project)['head_sha256']
        if order_head is not None: request['order_decisions_sha256'] = order_head
        if motion_choice_id is not None: request['motion_choice_id'] = motion_choice_id
        if residual_texture_profile is not None: request['residual_texture_profile'] = residual_texture_profile
        if skirt_profile is not None: request['skirt_profile'] = skirt_profile
        if shoulder_regions is not None: request['shoulder_regions'] = sorted(shoulder_regions)
        if sleeve_job_id is None:
            request['route_choice_sha256']=route_source(self.projects,self.sleeves,project,expected_resolved_sha256)
        self._current(request)
        with self._lock:
            if self._closed: raise PipelineRunError('pipeline_manager_closed')
            for active in self._active.values():
                if active['request']==request: return deepcopy(active['response'])
            if len(self._active)>=4: raise PipelineRunError('pipeline_queue_full')
            job='job-'+uuid4().hex; root=self._path(job,True)
            publish_document(root/'request.json', request, staging=root/'staging')
            response=dict(schema=SCHEMA,job_id=job,project_id=project,status='pending',stage='resolve',authority='none')
            self._active[job]=dict(request=request,response=response,cancel=Event())
            self._pool.submit(self._execute,job)
            return deepcopy(response)

    def get(self, project, job):
        root=self._path(job); request=read_document(root/'request.json')
        if request['project_id']!=project: raise PipelineRunError('pipeline_job_not_found')
        with self._lock:
            if job in self._active: return deepcopy(self._active[job]['response'])
        if not (root/'result.json').exists():
            return dict(schema=SCHEMA,job_id=job,project_id=project,status='blocked',authority='none',reason_code='character_build_interrupted')
        result=read_document(root/'result.json')
        if result.get('schema')!=SCHEMA or result.get('project_id')!=project or result.get('job_id')!=job:
            raise PipelineRunError('pipeline_artifact_invalid')
        if result['status']=='needs_review':
            try: self._current(request)
            except (ValueError,RuntimeError,OSError):
                return dict(schema=SCHEMA,job_id=job,project_id=project,status='blocked',authority='none',reason_code='character_source_changed')
            from .character_texture_trial import enrich_existing
            result=enrich_existing(self.application.store,result)
        return result

    def cancel(self, project, job):
        self.get(project,job)
        with self._lock:
            if job in self._active:
                self._active[job]['cancel'].set(); self._active[job]['response']['cancel_requested']=True
        return self.get(project,job)

    def verified_files(self, project, job):
        """Validate exact sources without allocating an unused download archive."""
        result=self.get(project,job)
        if result['status']!='needs_review': raise PipelineRunError('pipeline_preview_not_ready')
        files=self.application.store.read(result['artifact_sha256'])
        request=read_document(self._path(job)/'request.json')
        manifest=json.loads(files['character-manifest.json']); sources=manifest['source_addresses']
        if sources['resolved_project_sha256']!=request['expected_resolved_sha256'] \
                or sources['input_identity_sha256']!=request['expected_input_sha256'] \
                or (request['sleeve_job_id'] is not None and sources.get('sleeve_job_sha256')!=canonical_sha256(self.sleeves.get(project,request['sleeve_job_id']))) \
                or (request['sleeve_job_id'] is None and sources.get('route_choice_sha256')!=request['route_choice_sha256']):
            raise PipelineRunError('character_artifact_source_mismatch')
        self._current(request)
        return files

    def review_context(self, project, job):
        from .character_review_context import load
        return load(self, project, job)

    def download(self, project, job):
        files=self.verified_files(project,job)
        request=read_document(self._path(job)/'request.json')
        output=BytesIO()
        with ZipFile(output,'w',compression=ZIP_STORED) as archive:
            for name,raw in sorted(files.items()): archive.writestr(ZipInfo(name,(1980,1,1,0,0,0)),raw)
        self._current(request)
        return output.getvalue()

    def review_file(self, project, job, parts):
        from hashlib import sha256
        result=self.get(project,job)
        if result['status']!='needs_review': raise PipelineRunError('pipeline_preview_not_ready')
        name=review_name('/'.join(parts))
        expected=result.get('runtime',{}).get('files',{}).get(name)
        if not expected: raise PipelineRunError('pipeline_artifact_not_found')
        path=self._path(job)/'runtime'/name
        if path.is_symlink() or not path.resolve().is_relative_to((self._path(job)/'runtime').resolve()):
            raise PipelineRunError('pipeline_artifact_invalid')
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=expected: raise PipelineRunError('pipeline_artifact_invalid')
        mime={'.html':'text/html; charset=utf-8','.json':'application/json','.png':'image/png'}.get(path.suffix)
        if not mime: raise PipelineRunError('pipeline_artifact_not_found')
        return raw,mime

    def _execute(self, job):
        with self._lock:
            active=self._active[job]; active['response']['status']='running'
        request=active['request']; response=active['response']
        def progress(stage):
            with self._lock: response['stage']=stage
        try:
            self._current(request)
            result=self.builder(self.application,self.sleeves,request['project_id'],request['sleeve_job_id'],
                                progress=progress,cancel_requested=active['cancel'].is_set)
            from .character_region_decisions import apply_saved
            result=apply_saved(self,request['project_id'],result,request.get('region_decisions_sha256'))
            from .character_motion_catalog import append_selected
            result=append_selected(self,request,result)
            from .character_texture_trial import apply_selected
            if request.get('residual_texture_profile'): progress('texture-trial')
            result=apply_selected(self,request,result)
            from .character_skirt_trial import apply_selected as apply_skirt
            if request.get('skirt_profile'): progress('skirt-trial')
            result=apply_skirt(self,request,result)
            from .character_shoulder_trial import apply_selected as apply_shoulder
            result=apply_shoulder(self,request,result,progress=progress,cancel_requested=active['cancel'].is_set)
            from .character_final_regions import apply_saved as apply_final
            result=apply_final(self,request,result)
            from .character_component_mounts import apply_saved as apply_mounts
            result=apply_mounts(self,request,result)
            result=apply_final(self,request,result,stage="after_components")
            from .character_order_review import apply_saved as apply_order
            result=apply_order(self,request,result)
            self._current(request)
            runtime=self.capturer(self.projects,self.application.store,result['artifact_sha256'],self._path(job),
                                  progress=progress,cancel_requested=active['cancel'].is_set)
            self._current(request)
            response=dict(response, status='needs_review',stage='review',artifact_sha256=result['artifact_sha256'],
                            layers=result['manifest']['layers'],animations=result['manifest']['animations'],runtime=runtime,
                            motion_readiness=result['manifest'].get('motion_readiness',[]))
            if 'texture_trial' in result: response['texture_trial']=result['texture_trial']
            if 'skirt_trial' in result: response['skirt_trial']=result['skirt_trial']
            if 'shoulder_trial' in result: response['shoulder_trial']=result['shoulder_trial']
            if 'final_region_exclusions' in result: response['final_region_exclusions']=result['final_region_exclusions']
            if 'component_mounts' in result: response['component_mounts']=result['component_mounts']
            if 'post_component_regions' in result: response['post_component_regions']=result['post_component_regions']
            if 'order_review' in result: response['order_review']=result['order_review']
            from .character_stage_defaults import publish as publish_defaults
            publish_defaults(self._path(job), response, self.application.store.read(result['artifact_sha256']))
        except Exception as exc:
            reason=getattr(exc,'reason_code',str(exc))
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,99}',reason): reason='character_build_failed'
            response.update(status='failed',reason_code=reason)
        with self._lock:
            if active['cancel'].is_set():
                response=dict(schema=SCHEMA,job_id=job,project_id=request['project_id'],status='canceled',authority='none',reason_code='character_build_canceled')
            root=self._path(job)
            try: publish_document(root/'result.json',response,staging=root/'staging')
            finally: self._active.pop(job,None)

    def close(self):
        with self._lock:
            self._closed=True
            for active in self._active.values(): active['cancel'].set()
        self._pool.shutdown(wait=True)
