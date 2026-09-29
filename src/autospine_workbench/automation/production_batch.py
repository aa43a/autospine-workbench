"""Durable character-by-motion reservations; failed cells do not stop other cells."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, RLock
from uuid import uuid4
import re

from .pipeline_run import PipelineRunError
from .production_journal import now
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.production-batch/v1'
ACTIVE = {'pending', 'running'}
READY = {'needs_review', 'stage_accepted'}


class ProductionBatches:
    def __init__(self, production, *, poll_seconds=1):
        self.production = production
        self.root = production.journal.root.parent / 'production-batches-v1'
        self._lock, self._stop = RLock(), Event()
        self._active = set()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='production-batch')
        self.poll_seconds = poll_seconds

    def folder(self, batch, create=False):
        if type(batch) is not str or not re.fullmatch(r'batch-[a-f0-9]{32}', batch):
            raise PipelineRunError('production_batch_id_invalid')
        return directory(self.root / batch, create=create)

    def get(self, batch):
        with self._lock:
            paths = sorted(self.folder(batch).glob('revision-*.json'))
            if not paths:
                raise PipelineRunError('production_batch_not_found')
            value = read_document(paths[-1])
            if (value.get('schema') != SCHEMA or value.get('batch_id') != batch or
                    paths[-1].name != f"revision-{value['revision']:012d}.json"):
                raise PipelineRunError('production_batch_invalid')
            return value

    def list(self):
        if not self.root.exists():
            return []
        return sorted((self.get(p.name) for p in self.root.glob('batch-*')),
                      key=lambda v: v['created_at'], reverse=True)

    def _append(self, value, event):
        value = deepcopy(value)
        value.update(revision=value['revision'] + 1, updated_at=now(), event=event)
        folder = self.folder(value['batch_id'])
        if not publish_document(folder / f"revision-{value['revision']:012d}.json", value,
                                staging=folder / 'staging'):
            raise PipelineRunError('production_batch_conflict')
        return value

    def submit(self, body):
        if (type(body) is not dict or set(body) != {'characters', 'source_job_ids', 'body_options', 'joint_config'}
                or type(body['characters']) is not list or type(body['source_job_ids']) is not list
                or not body['characters'] or not body['source_job_ids']
                or len(body['characters']) * len(body['source_job_ids']) > 32):
            raise PipelineRunError('production_batch_request_invalid')
        characters, sources = body['characters'], body['source_job_ids']
        if any(type(c) is not dict or set(c) != {'project_id', 'character_job_id'} for c in characters):
            raise PipelineRunError('production_batch_request_invalid')
        if (any(type(s) is not str for s in sources) or len(set(sources)) != len(sources)
                or any(type(c['project_id']) is not str for c in characters)
                or len({c['project_id'] for c in characters}) != len(characters)):
            raise PipelineRunError('production_batch_duplicates')
        frozen = [self.production.driver.freeze(dict(c, source_job_id=s,
            body_options=body['body_options'], joint_config=body['joint_config']))
            for c in characters for s in sources]
        with self._lock:
            if self._stop.is_set():
                raise PipelineRunError('pipeline_manager_closed')
            for previous in self.list():
                if [row['request'] for row in previous['cells']] == frozen and previous['status'] != 'canceled':
                    self._schedule(previous['batch_id'])
                    return previous
            # Freeze every reservation before starting any child. Reuse only an
            # exact existing candidate; its acceptance remains bound to that run.
            existing = self.production.list()
            cells = []
            for request in frozen:
                match = next((r for r in existing if r['request'] == request and r['status'] in ACTIVE | READY), None)
                cells.append(dict(request=request, run_id=match['run_id'] if match else 'production-' + uuid4().hex,
                                  reused=bool(match), status='pending', reason_code=None))
            batch = 'batch-' + uuid4().hex
            self.folder(batch, True)
            value = dict(schema=SCHEMA, batch_id=batch, revision=0, created_at=now(),
                         status='pending', cells=cells, authority='none', production_authorized=False)
            value = self._append(value, 'created')
            self._schedule(batch)
            return value

    def _schedule(self, batch):
        if self._stop.is_set():
            raise PipelineRunError('pipeline_manager_closed')
        if batch not in self._active:
            if len(self._active) >= 4:
                raise PipelineRunError('pipeline_queue_full')
            self._active.add(batch)
            self._pool.submit(self._execute, batch)

    def resume(self, batch, revision):
        with self._lock:
            value = self.get(batch)
            if type(revision) is not int or value['revision'] != revision:
                raise PipelineRunError('production_batch_conflict')
            if value['status'] == 'canceled':
                raise PipelineRunError('production_batch_canceled')
            self._schedule(batch)
            return value

    def cancel(self, batch, revision):
        with self._lock:
            value = self.get(batch)
            if type(revision) is not int or value['revision'] != revision:
                raise PipelineRunError('production_batch_conflict')
            value['status'] = 'canceled'
            value = self._append(value, 'canceled')
        # Shared/reused runs remain independently owned; stop only this batch's
        # dispatch. Already submitted runs can be canceled in their own pages.
        return value

    def _record(self, batch, index, run=None, error=None):
        with self._lock:
            value = self.get(batch)
            if value['status'] == 'canceled' or self._stop.is_set():
                return False
            row = value['cells'][index]
            update = dict(status=run['status'] if run else 'blocked',
                          reason_code=run.get('reason_code') if run else error)
            if all(row.get(k) == v for k, v in update.items()):
                return True
            row.update(update)
            value['status'] = 'running'
            self._append(value, 'cell_updated')
            return True

    def _execute(self, batch):
        from .pipeline_lease import execution_lease
        from ..resolved_project import canonical_sha256
        try:
            with execution_lease(self.root, 'run-' + canonical_sha256({'batch': batch})):
                for i, row in enumerate(self.get(batch)['cells']):
                    if self._stop.is_set() or self.get(batch)['status'] == 'canceled':
                        return
                    try:
                        run = self.production.ensure_reserved(row['request'], row['run_id'])
                        while run['status'] in ACTIVE or self.production.is_active(row['run_id']):
                            if not self._record(batch, i, run) or self._stop.wait(self.poll_seconds):
                                return
                            run = self.production.get(row['run_id'])
                        if not self._record(batch, i, run):
                            return
                    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                        if not self._record(batch, i, error=getattr(exc, 'reason_code', 'production_batch_cell_failed')):
                            return
                with self._lock:
                    value = self.get(batch)
                    if value['status'] == 'canceled' or self._stop.is_set():
                        return
                    statuses = {row['status'] for row in value['cells']}
                    value['status'] = ('stage_accepted' if statuses == {'stage_accepted'} else
                                       'needs_review' if statuses <= READY else 'needs_intervention')
                    self._append(value, 'observed')
        except PipelineRunError as exc:
            if exc.reason_code != 'pipeline_run_busy':
                with self._lock:
                    value = self.get(batch)
                    if value['status'] != 'canceled':
                        value.update(status='needs_intervention', reason_code=exc.reason_code)
                        self._append(value, 'blocked')
        finally:
            with self._lock:
                self._active.discard(batch)

    def close(self):
        self._stop.set()
        self._pool.shutdown(wait=True)
