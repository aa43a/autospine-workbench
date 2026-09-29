"""Durable handoff from pending PSD/motion intake to an exact production run."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, RLock
from uuid import uuid4
import re

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .production_journal import now
from .storage_io import directory, publish_document, read_document


class ProductionEntrances:
    def __init__(self, production, imports, *, poll_seconds=1):
        self.production, self.imports = production, imports
        self.motions = production.driver.motions
        self.root = production.journal.root.parent/'production-entrances-v1'
        self._lock, self._stop = RLock(), Event()
        self._active = set()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='production-entrance')
        self.poll_seconds = poll_seconds

    def folder(self, job, create=False):
        if type(job) is not str or not re.fullmatch('entrance-[a-f0-9]{32}', job):
            raise PipelineRunError('production_entrance_id_invalid')
        return directory(self.root/job, create=create)

    def get(self, job):
        with self._lock:
            paths = sorted(self.folder(job).glob('revision-*.json'))
            if not paths:
                raise PipelineRunError('production_entrance_not_found')
            value = read_document(paths[-1])
            if (value.get('schema') != 'autospine.production-entrance/v1' or value.get('job_id') != job
                    or paths[-1].name != f"revision-{value['revision']:012d}.json"):
                raise PipelineRunError('production_entrance_invalid')
            return value

    def list(self):
        return sorted((self.get(p.name) for p in self.root.glob('entrance-*')),
                      key=lambda v:v['created_at'], reverse=True) if self.root.exists() else []

    def _append(self, value, event):
        value = deepcopy(value)
        value.update(revision=value['revision']+1, updated_at=now(), event=event)
        folder = self.folder(value['job_id'])
        if not publish_document(folder/f"revision-{value['revision']:012d}.json", value, staging=folder/'staging'):
            raise PipelineRunError('production_entrance_conflict')
        return value

    def _source(self, kind, job):
        manager = self.imports if kind == 'psd' else self.motions
        return read_document(manager.folder(job)/'request.json')

    def freeze(self, body):
        if (type(body) is not dict or set(body) != {'character', 'source_job_id', 'body_options', 'joint_config'}
                or type(body['character']) is not dict or len(body['character']) != 1
                or set(body['character']) not in ({'project_id'}, {'import_job_id'})
                or type(body['body_options']) is not dict or type(body['joint_config']) is not dict):
            raise PipelineRunError('production_entrance_request_invalid')
        character = body['character']
        if 'import_job_id' in character:
            identity = dict(character=canonical_sha256(self._source('psd', character['import_job_id'])))
        else:
            project = self.motions.projects.get_project(character['project_id'])
            identity = dict(character=project['resolved']['sha256'])
        motion = self._source('motion', body['source_job_id'])
        if motion.get('kind', 'import') not in ('import', 'generate'):
            raise PipelineRunError('production_entrance_motion_invalid')
        identity['motion'] = canonical_sha256(motion)
        return dict(deepcopy(body), source_identity=identity)

    def options(self):
        imports = []
        if self.imports.root.exists():
            for path in self.imports.root.glob('import-*/request.json'):
                request = read_document(path)
                imports.append(dict(self.imports.get(path.parent.name), name=request['name']))
        return dict(imports=imports, motions=[m for m in self.motions.overview()['jobs']
                    if m.get('kind', 'import') in ('import', 'generate')])

    def submit(self, body):
        request = self.freeze(body)
        with self._lock:
            for old in self.list():
                if old['request'] == request and old['status'] != 'canceled':
                    self._schedule(old['job_id'])
                    return old
            job = 'entrance-'+uuid4().hex
            self.folder(job, True)
            value = self._append(dict(schema='autospine.production-entrance/v1',job_id=job,
                revision=0,created_at=now(),request=request,status='pending',step='sources',
                run_id='production-'+uuid4().hex,authority='none',production_authorized=False), 'created')
            self._schedule(job)
            return value

    def _schedule(self, job):
        if self._stop.is_set():
            raise PipelineRunError('pipeline_manager_closed')
        if job not in self._active:
            if len(self._active) >= 8:
                raise PipelineRunError('pipeline_queue_full')
            self._active.add(job)
            self._pool.submit(self._execute, job)

    def resume(self, job, revision):
        with self._lock:
            value = self.get(job)
            if type(revision) is not int or revision != value['revision']:
                raise PipelineRunError('production_entrance_conflict')
            if value['status'] == 'canceled':
                raise PipelineRunError('production_entrance_canceled')
            self._schedule(job)
            return value

    def cancel(self, job, revision):
        with self._lock:
            value = self.get(job)
            if type(revision) is not int or revision != value['revision']:
                raise PipelineRunError('production_entrance_conflict')
            if value['status'] == 'linked':
                raise PipelineRunError('production_entrance_cancel_in_production')
            value.update(status='canceled')
            return self._append(value,'canceled')

    def _update(self, job, **fields):
        with self._lock:
            value = self.get(job)
            if value['status'] == 'canceled':
                return value
            if all(value.get(k) == v for k,v in fields.items()):
                return value
            value.update(fields)
            return self._append(value, fields.get('step','updated'))

    def _resolve(self, request):
        body = {k:v for k,v in request.items() if k != 'source_identity'}
        if self.freeze(body) != request:
            raise PipelineRunError('production_entrance_source_changed')
        character = request['character']
        if 'import_job_id' in character:
            imported = self.imports.get(character['import_job_id'])
            if imported['status'] in ('pending','running'):
                return None, 'psd'
            if imported['status'] != 'succeeded':
                raise PipelineRunError(imported.get('reason_code','production_entrance_psd_failed'))
            project = imported['project_id']
        else:
            project = character['project_id']
        motion = self.motions.get(request['source_job_id'])
        if motion['status'] in ('pending','running'):
            return None, 'motion'
        if motion['status'] != 'succeeded' or motion.get('result',{}).get('motion_status') != 'compiled':
            raise PipelineRunError(motion.get('reason_code','production_entrance_motion_failed'))
        target = self.motions.character_manager().motion_target(project)['job']
        body = dict(project_id=project, character_job_id=target['job_id'] if target and
            target['status'] == 'needs_review' else None, source_job_id=request['source_job_id'],
            body_options=request['body_options'],joint_config=request['joint_config'])
        return self.production.driver.freeze(body), 'production'

    def _execute(self, job):
        from .pipeline_lease import execution_lease
        try:
            with execution_lease(self.root,'run-'+canonical_sha256({'entrance':job})):
                value = self.get(job)
                # Once handed off, the production task owns source revision and
                # rebuild policy. Never choose a different character on resume.
                frozen = value.get('production_request')
                while frozen is None and not self._stop.is_set():
                    if self.get(job)['status'] == 'canceled':
                        return
                    frozen, step = self._resolve(value['request'])
                    self._update(job,status='running',step=step,reason_code=None)
                    if frozen is None and self._stop.wait(self.poll_seconds):
                        return
                if self._stop.is_set():
                    return
                with self._lock:
                    if self.get(job)['status'] == 'canceled':
                        return
                    if 'production_request' not in value:
                        previous = next((r for r in self.production.list() if r['request'] == frozen and
                            r['status'] in ('pending','running','needs_review','stage_accepted')), None)
                        value = self._update(job,production_request=frozen,
                            run_id=previous['run_id'] if previous else value['run_id'],reused=bool(previous))
                    run = self.production.ensure_reserved(frozen,value['run_id'])
                    self._update(job,status='linked',step='production',production_status=run['status'],reason_code=None)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            if getattr(exc,'reason_code',None) != 'pipeline_run_busy':
                self._update(job,status='blocked',step='sources',reason_code=getattr(exc,'reason_code',str(exc)))
        finally:
            with self._lock:
                self._active.discard(job)

    def close(self):
        self._stop.set()
        self._pool.shutdown(wait=True)
