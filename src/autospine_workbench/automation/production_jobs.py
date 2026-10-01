"""Persistent coordinator: child launch intent is recorded before submission."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, RLock
from uuid import uuid4

from .pipeline_run import PipelineRunError
from .production_journal import ProductionJournal, now

ACTIVE = {'pending', 'running'}


class ProductionJobs:
    def __init__(self, root, driver, *, poll_seconds=1):
        self.journal = ProductionJournal(root)
        self.driver = driver
        self.poll_seconds = poll_seconds
        self._lock = RLock()
        self._stop = Event()
        self._active = set()
        self._active_lock = RLock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='production')

    def submit(self, body):
        if isinstance(body,dict) and 'body_selection' in body:
            raise PipelineRunError('production_repair_requires_revision')
        request = self.driver.freeze(body)
        with self._lock:
            self._require_open()
            for run in self.journal.list():
                if run['request'] == request and run['status'] in ACTIVE | {'needs_review'}:
                    self._schedule(run['run_id'])
                    return run
            run = self.journal.create(request)
            self._schedule(run['run_id'])
            return run

    def _require_open(self):
        if self._stop.is_set():
            raise PipelineRunError('pipeline_manager_closed')

    def ensure_reserved(self, request, run_id):
        """Recover an exact batch reservation, never launch a second run on replay."""
        self.driver.validate(request)
        with self._lock:
            self._require_open()
            # Do not expose an empty reservation directory to concurrent list reads.
            with self.journal._lock:
                folder = self.journal.folder(run_id, create=True)
                if any(folder.glob('revision-*.json')):
                    run = self.journal.read(run_id)
                    if run['request'] != request:
                        raise PipelineRunError('production_reserved_request_conflict')
                else:
                    run = self.journal.create(request, run_id=run_id)
            if run['status'] in ACTIVE | {'needs_review', 'stage_accepted'}:
                self._schedule(run_id)
            return run

    def is_active(self, run_id):
        with self._active_lock:
            return run_id in self._active

    def _schedule(self, run_id):
        # Mutation coordination always precedes the short live-ownership lock.
        with self._lock:
            self._require_open()
            with self._active_lock:
                if run_id not in self._active:
                    if len(self._active) >= 8:
                        raise PipelineRunError('pipeline_queue_full')
                    self._active.add(run_id)
                    try:
                        self._pool.submit(self._execute, run_id)
                    except BaseException:
                        self._active.discard(run_id)
                        raise

    def get(self, run_id):
        return self.journal.read(run_id)

    def execution_view(self, value):
        """Attach live ownership to an HTTP snapshot, never to its journal."""
        result = deepcopy(value)
        with self._active_lock:
            result['execution_active'] = (
                not self._stop.is_set() and result['run_id'] in self._active
            )
        return result

    def retry(self, run_id, revision):
        """Retain failed attempts; only clear the failed stage and its dependants."""
        with self._lock:
            value = self.journal.read(run_id)
            if type(revision) is not int or value['revision'] != revision:
                raise PipelineRunError('production_revision_conflict')
            if self.is_active(run_id) or value['status'] != 'blocked':
                raise PipelineRunError('production_retry_not_available')
            self.driver.validate(value['request'])
            for stage in ('source', 'bindings', 'sleeves', 'character', 'body', 'joint'):
                row = value['stages'].get(stage)
                if row is None:
                    continue
                if row['status'] in ('succeeded', 'reused'):
                    continue
                if row.get('job_id') and self.driver.exists(row['job_id']):
                    if self.driver.get(row['job_id'])['status'] in ACTIVE:
                        raise PipelineRunError('production_child_still_active')
                row.update(status='pending')
                for key in ('job_id', 'reason_code', 'finished_at', 'artifact_sha256'):
                    row.pop(key, None)
                break
            value.update(status='pending')
            value.pop('reason_code', None)
            value = self.journal.append(value, 'retry_requested')
            self._schedule(run_id)
            return value

    def list(self):
        return self.journal.list()

    def revise(self, run_id, revision, joint_config=None, body_options=None, expected_plan_sha256=None, body_registration=None):
        with self._lock:
            self._require_open()
            previous = self.journal.read(run_id)
            if type(revision) is not int or previous['revision'] != revision:
                raise PipelineRunError('production_revision_conflict')
            if self.is_active(run_id):
                raise PipelineRunError('production_revision_wait_for_current_run')
            from .production_revision import plan
            preview=plan(self,run_id,revision,joint_config,body_options,body_registration)
            if expected_plan_sha256 is not None and expected_plan_sha256!=preview['plan_sha256']:
                raise PipelineRunError('production_revision_plan_changed')
            request = preview['request']
            value = self.journal.create(request)
            value['parent_run_id'] = run_id
            value['reused_stages'] = preview['reuse_stages']
            value['revision_plan']=preview
            for stage in value['reused_stages']:
                old = previous['stages'].get(stage,{})
                value['stages'][stage] = (deepcopy(old) if old.get('status') in ('succeeded','reused')
                    else dict(status='reused',attempts=[],basis='verified_character'))
            value = self.journal.append(value, 'revision_created')
            self._schedule(value['run_id'])
            return value

    def resume(self, run_id, revision):
        with self._lock:
            value = self.journal.read(run_id)
            if type(revision) is not int or value['revision'] != revision:
                raise PipelineRunError('production_revision_conflict')
            if value['status'] == 'canceled':
                raise PipelineRunError('production_canceled_create_new_run')
            self.driver.validate(value['request'])
            self._schedule(run_id)
            return value

    def cancel(self, run_id, revision):
        with self._lock:
            value = self.journal.read(run_id)
            if type(revision) is not int or value['revision'] != revision:
                raise PipelineRunError('production_revision_conflict')
            value['status'] = 'canceled'
            value = self.journal.append(value, 'canceled')
        for stage in value['stages'].values():
            if stage['status'] in ACTIVE and stage.get('job_id') and not stage.get('shared'):
                if self.driver.exists(stage['job_id']):
                    self.driver.cancel(stage['job_id'])
        return value

    def _write(self, run_id, change, event):
        with self._lock:
            value = self.journal.read(run_id)
            if value['status'] == 'canceled' or self._stop.is_set():
                return None
            change(value)
            return self.journal.append(value, event)

    def _child(self, run_id, stage):
        value = self.get(run_id)
        row = value['stages'][stage]
        if row['status'] == 'succeeded':
            child = self.driver.get(row['job_id'])
            if child['status'] != 'succeeded':
                raise PipelineRunError('production_completed_child_changed')
            return True
        job = row.get('job_id')
        if not job:
            job = 'motion-' + uuid4().hex
            def reserve(v):
                v['status'] = 'running'
                v['stages'][stage].update(status='pending', job_id=job, started_at=now())
                v['stages'][stage]['attempts'].append(dict(job_id=job, reserved_at=now()))
            value = self._write(run_id, reserve, stage + '_reserved')
            if value is None:
                return False
        # Crash after request publication is recovered by this exact reserved ID.
        if not self.driver.exists(job):
            with self._lock:
                if self.get(run_id)['status'] == 'canceled' or self._stop.is_set():
                    return False
                response = self.driver.submit(stage, value, job)
                if response['job_id'] != job:
                    raise PipelineRunError('production_child_identity_mismatch')
        self._write(run_id, lambda v: v['stages'][stage].update(status='running'), stage + '_observing')
        while not self._stop.is_set():
            if self.get(run_id)['status'] == 'canceled':
                return False
            child = self.driver.get(job)
            if child['status'] not in ACTIVE:
                break
            self._stop.wait(self.poll_seconds)
        else:
            return False
        def record(v):
            v['stages'][stage].update(status=child['status'], finished_at=now(),
                reason_code=child.get('reason_code'),
                artifact_sha256=child.get('result', {}).get('artifact_sha256'))
            if child['status'] != 'succeeded':
                v.update(status='blocked', reason_code=child.get('reason_code', 'production_child_failed'))
        self._write(run_id, record, stage + '_finished')
        return child['status'] == 'succeeded'

    def _execute(self, run_id):
        from ..resolved_project import canonical_sha256
        from .pipeline_lease import execution_lease
        try:
            with execution_lease(self.journal.root, 'run-' + canonical_sha256({'production': run_id})):
                self._execute_owned(run_id)
        except PipelineRunError as exc:
            if exc.reason_code != 'pipeline_run_busy':
                self._write(run_id, lambda v: v.update(status='blocked', reason_code=exc.reason_code), 'blocked')
        finally:
            with self._active_lock:
                self._active.discard(run_id)

    def _execute_owned(self, run_id):
        try:
            self.driver.validate(self.get(run_id)['request'])
            def started(v):
                v['status'] = 'running'
                v.pop('reason_code', None)
            self._write(run_id, started, 'execution_started')
            if hasattr(self.driver, 'prepare'):
                stopped = lambda: self._stop.is_set() or self.get(run_id)['status'] == 'canceled'
                if not self.driver.prepare(lambda: self.get(run_id),
                        lambda change, event: self._write(run_id, change, event), stopped):
                    return
            def character(v):
                v['stages']['character'].update(status='succeeded',
                    job_id=v['request']['character_job_id'], artifact_sha256=v['request']['character_sha256'])
            if self.get(run_id)['stages']['character']['status'] != 'succeeded':
                self._write(run_id, character, 'character_verified')
            for stage in ('body', 'joint'):
                if not self._child(run_id, stage):
                    return
            value = self.get(run_id)
            job = value['stages']['joint']['job_id']
            review = self.driver.review(job)
            accepted = review['current_applies'] and review['current']['decision'] in ('accepted', 'accepted_with_exceptions')
            def finish(v):
                v['status'] = 'stage_accepted' if accepted else 'needs_review'
                v.pop('reason_code', None)
                v['stages']['review'].update(status=v['status'], job_id=job,
                    evidence_sha256=review['evidence_sha256'], review_revision=review['revision'])
                v['stages']['delivery'].update(status='candidate_available',
                    download_url=f'/api/motions/{job}/download', player_url=f'/api/motions/{job}/view/player.html')
            self._write(run_id, finish, 'review_refreshed')
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            reason = getattr(exc, 'reason_code', 'production_step_failed')
            self._write(run_id, lambda v: v.update(status='blocked', reason_code=reason), 'blocked')

    def close(self):
        self._stop.set()
        self._pool.shutdown(wait=True)
