"""Use existing verified character, body and joint services without copying QA."""
from copy import deepcopy
from threading import Event

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .production_submission import reserved_child


class ProductionDriver:
    def __init__(self, motions):
        self.motions = motions
        self._wait = Event()

    def wait(self, seconds):
        self._wait.wait(seconds)

    def prepare(self, read, write, stopped):
        from .production_preparation import prepare
        return prepare(self, read, write, stopped)

    def freeze(self, body):
        fields = {'project_id', 'character_job_id', 'source_job_id', 'body_options', 'joint_config'}
        if not isinstance(body, dict) or set(body)-{'body_selection'} != fields:
            raise PipelineRunError('production_request_invalid')
        if not isinstance(body['body_options'], dict) or not isinstance(body['joint_config'], dict):
            raise PipelineRunError('production_request_invalid')
        if set(body['body_options']) & {'project_id', 'character_job_id'}:
            raise PipelineRunError('production_request_invalid')
        if body['character_job_id'] is not None:
            character, _ = self.motions.character_manager().verified_snapshot(body['project_id'], body['character_job_id'])
            identity = dict(character_sha256=character['artifact_sha256'])
        else:
            project = self.motions.projects.get_project(body['project_id'])
            identity = dict(character_sha256=None, resolved_sha256=project['resolved']['sha256'])
        source = self.motions.get(body['source_job_id'])
        if source['status'] != 'succeeded' or source.get('result', {}).get('motion_status') != 'compiled':
            raise PipelineRunError('motion_target_source_unavailable')
        frozen = dict(deepcopy(body), **identity, source_sha256=canonical_sha256(source))
        from .production_body_selection import validate
        validate(self, frozen)
        return frozen

    def validate(self, request):
        fields = ('project_id', 'character_job_id', 'source_job_id', 'body_options', 'joint_config') + (('body_selection',) if 'body_selection' in request else ())
        if self.freeze({key: request[key] for key in fields}) != request:
            raise PipelineRunError('production_source_changed')

    def revision_request(self, request, config=None, body_options=None):
        fields = ('project_id', 'character_job_id', 'source_job_id', 'body_options', 'joint_config')
        body = {key: deepcopy(request[key]) for key in fields}
        latest = self.motions.character_manager().motion_target(body['project_id'])['job']
        body['character_job_id'] = latest['job_id'] if latest and latest['status'] == 'needs_review' else None
        if config is not None:
            body['joint_config'] = config
        if body_options is not None:
            body['body_options'] = deepcopy(body_options)
        if (request.get('body_selection') and body['character_job_id']==request['character_job_id']
                and body['body_options']==request['body_options']):
            body['body_selection']=deepcopy(request['body_selection'])
        return self.freeze(body)

    def select_body(self, request, parent_job, registration):
        from .production_body_selection import select
        return dict(request, body_selection=select(self,request,parent_job,registration))

    def exists(self, job):
        if job.startswith('job-'):
            manager = self.motions.character_manager()
            return any((root / job / 'request.json').is_file() for root in (manager.root, manager.sleeves.root))
        return (self.motions.root / job / 'request.json').is_file()

    def submit(self, stage, run, job):
        request = run['request']
        with reserved_child(job):
            if stage == 'body':
                from .motion_target_jobs import submit
                return submit(self.motions, request['source_job_id'], dict(request['body_options'],
                    project_id=request['project_id'], character_job_id=run['stages']['character']['job_id']))
            from .motion_joint_jobs import inspect, submit
            parent = run['stages']['body']['job_id']
            selection=request.get('body_selection')
            registration=selection['registration_sha256'] if selection else None
            if selection and parent!=selection['root_job_id']:
                raise PipelineRunError('production_repair_parent_mismatch')
            if selection:parent=selection['parent_job_id']
            meta = inspect(self.motions, parent, registration)
            if selection and meta.get('source_provenance') != {k:v for k,v in selection.items() if k not in ('root_job_id','selector','lineage')}:
                raise PipelineRunError('production_repair_selection_changed')
            return submit(self.motions, parent, dict(artifact_sha256=meta['artifact_sha256'],
                config=request['joint_config'], **(dict(registration_sha256=registration) if registration else {})))

    def get(self, job):
        if job.startswith('job-'):
            from .storage_io import read_document
            manager = self.motions.character_manager()
            if not (manager.root/job/'request.json').exists():
                manager = manager.sleeves
            request = read_document(manager._path(job) / 'request.json')
            return manager.get(request['project_id'], job)
        return self.motions.get(job)

    def review(self, job):
        from .motion_stage_review import inspect
        return inspect(self.motions, job)

    def cancel(self, job):
        if job.startswith('job-'):
            from .storage_io import read_document
            manager = self.motions.character_manager()
            if not (manager.root/job/'request.json').exists():
                manager = manager.sleeves
            request = read_document(manager._path(job) / 'request.json')
            return manager.cancel(request['project_id'], job)
        return self.motions.cancel(job)
