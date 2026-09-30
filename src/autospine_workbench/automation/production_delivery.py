"""Persisted compatible-animation assembly, with fresh capture and source checks."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from threading import Event, RLock
from uuid import uuid4
from zipfile import ZipFile, ZIP_STORED
import re

from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from ..targets.character43.animation_compatibility import signature, compare
from ..targets.character43.multi_animation import build
from .animated_store import AnimatedStore
from .character_capture import capture
from .motion_target_jobs import context
from .pipeline_run import PipelineRunError
from .production_journal import now
from .storage_io import directory, publish_document, read_document, canonical_bytes


class ProductionDeliveries:
    def __init__(self, production):
        self.production = production
        self.projects = production.driver.motions.projects
        self.root = production.journal.root.parent / 'production-deliveries-v1'
        self.store = AnimatedStore(self.projects.state_root)
        self._lock, self._stop = RLock(), Event()
        self._active = set()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='production-delivery')

    def folder(self, job, create=False):
        if type(job) is not str or not re.fullmatch('delivery-[a-f0-9]{32}', job):
            raise PipelineRunError('production_delivery_id_invalid')
        return directory(self.root / job, create=create)

    def get(self, job):
        with self._lock:
            paths = sorted(self.folder(job).glob('revision-*.json'))
            if not paths:
                raise PipelineRunError('production_delivery_not_found')
            value = read_document(paths[-1])
            if (value.get('schema') != 'autospine.production-delivery/v1' or value.get('job_id') != job
                    or paths[-1].name != f"revision-{value['revision']:012d}.json"):
                raise PipelineRunError('production_delivery_invalid')
            return value

    def list(self):
        return sorted((self.get(p.name) for p in self.root.glob('delivery-*')),
                      key=lambda v: v['created_at'], reverse=True) if self.root.exists() else []

    def execution_view(self, value):
        """Keep ephemeral worker ownership out of revisions and exported records."""
        with self._lock:
            result = deepcopy(value)
            result['execution_active'] = (
                not self._stop.is_set() and result['job_id'] in self._active
            )
            return result

    def _append(self, value, event):
        value = deepcopy(value)
        value.update(revision=value['revision'] + 1, updated_at=now(), event=event)
        folder = self.folder(value['job_id'])
        if not publish_document(folder / f"revision-{value['revision']:012d}.json", value, staging=folder/'staging'):
            raise PipelineRunError('production_delivery_conflict')
        return value

    def sources(self, run_ids):
        if (type(run_ids) is not list or not 2 <= len(run_ids) <= 16 or
                any(type(r) is not str for r in run_ids) or len(set(run_ids)) != len(run_ids)):
            raise PipelineRunError('production_delivery_sources_invalid')
        records, sources, baseline, project = [], [], None, None
        for index, run_id in enumerate(run_ids):
            run = self.production.get(run_id)
            self.production.driver.validate(run['request'])
            joint = run['stages']['joint']
            if joint['status'] != 'succeeded':
                raise PipelineRunError('production_joint_not_ready')
            result, files = context(self.production.driver.motions, joint['job_id'])
            if result['artifact_sha256'] != joint['artifact_sha256']:
                raise PipelineRunError('production_completed_child_changed')
            current_project = run['request']['project_id']
            if project is not None and project != current_project:
                raise PipelineRunError('production_delivery_project_mismatch')
            project = current_project
            current = signature(files)
            if baseline is not None and compare(baseline, current):
                raise PipelineRunError('production_delivery_incompatible')
            baseline = current
            records.append(dict(run_id=run_id, job_id=joint['job_id'], artifact_sha256=result['artifact_sha256']))
            sources.append(dict(name=f'motion-{index+1:02d}', artifact_sha256=result['artifact_sha256'], files=files))
        return dict(project_id=project, sources=records), sources

    def submit(self, body):
        if type(body) is not dict or set(body) != {'run_ids'}:
            raise PipelineRunError('production_delivery_request_invalid')
        request, _ = self.sources(body['run_ids'])
        with self._lock:
            for old in self.list():
                if old['request'] == request:
                    if old['status'] not in ('needs_review', 'stage_accepted'):
                        self._schedule(old['job_id'])
                    return old
            job = 'delivery-' + uuid4().hex
            self.folder(job, True)
            value = dict(schema='autospine.production-delivery/v1', job_id=job, revision=0,
                created_at=now(), request=request, status='pending', step='queued',
                authority='none', production_authorized=False, visual_status='not_reviewed')
            value = self._append(value, 'created')
            self._schedule(job)
            return value

    def _schedule(self, job):
        if self._stop.is_set():
            raise PipelineRunError('pipeline_manager_closed')
        if job not in self._active:
            if len(self._active) >= 4:
                raise PipelineRunError('pipeline_queue_full')
            self._active.add(job)
            self._pool.submit(self._execute, job)

    def resume(self, job, revision):
        with self._lock:
            value = self.get(job)
            if type(revision) is not int or value['revision'] != revision:
                raise PipelineRunError('production_delivery_conflict')
            self._validate(value)
            if value['status'] not in ('needs_review', 'stage_accepted'):
                self._schedule(job)
            return value

    def review(self, job, body):
        if (type(body) is not dict or set(body) != {'expected_revision', 'verdict', 'notes'} or
                body['verdict'] not in ('stage_accepted', 'needs_changes') or
                type(body['notes']) is not str or len(body['notes']) > 4000):
            raise PipelineRunError('production_delivery_review_invalid')
        self.review_context(None, job)
        with self._lock:
            value = self.get(job)
            if type(body['expected_revision']) is not int or value['revision'] != body['expected_revision']:
                raise PipelineRunError('production_delivery_conflict')
            value.update(status='stage_accepted' if body['verdict'] == 'stage_accepted' else 'needs_review',
                visual_status=body['verdict'], review=dict(artifact_sha256=value['artifact_sha256'],
                    verdict=body['verdict'], notes=body['notes'], reviewed_at=now(), scope='stage_only'))
            return self._append(value, 'visual_review_saved')

    def _validate(self, value):
        request, sources = self.sources([r['run_id'] for r in value['request']['sources']])
        if request != value['request']:
            raise PipelineRunError('production_delivery_source_changed')
        return sources

    def _update(self, job, **fields):
        with self._lock:
            value = self.get(job)
            value.update(fields)
            return self._append(value, fields.get('step', 'updated'))

    def _execute(self, job):
        from .pipeline_lease import execution_lease
        try:
            with execution_lease(self.root, 'run-' + canonical_sha256({'delivery': job})):
                sources = self._validate(self.get(job))
                self._update(job, status='running', step='merging', reason_code=None)
                files, _ = build(sources)
                digest = self.store.publish(files)
                # Each retry retains its capture evidence rather than overwriting it.
                attempt = self.folder(job) / ('attempt-' + uuid4().hex)
                directory(attempt, create=True)
                self._update(job, artifact_sha256=digest, attempt=attempt.name)
                runtime = capture(self.projects, self.store, digest, attempt,
                    progress=lambda step: self._update(job, step=step), cancel_requested=self._stop.is_set,
                    storage_reference=True)
                self._validate(self.get(job))
                if runtime.get('status') != 'needs_review':
                    raise PipelineRunError('production_delivery_runtime_unavailable')
                self._update(job, status='needs_review', step='review', runtime=runtime)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            if getattr(exc, 'reason_code', None) != 'pipeline_run_busy':
                self._update(job, status='blocked', step='blocked',
                             reason_code=getattr(exc, 'reason_code', str(exc)))
        finally:
            with self._lock:
                self._active.discard(job)

    def review_context(self, project, job):
        value = self.get(job)
        self._validate(value)
        if value['status'] not in ('needs_review', 'stage_accepted'):
            raise PipelineRunError('production_delivery_not_ready')
        if not re.fullmatch('attempt-[a-f0-9]{32}', value['attempt']):
            raise PipelineRunError('production_delivery_invalid')
        root = directory(self.folder(job) / value['attempt'] / 'runtime')
        raw = read_real_file(root / 'report.json', 256 << 20, 'delivery runtime report')
        if sha256(raw).hexdigest() != value['runtime']['files']['report.json']:
            raise PipelineRunError('production_delivery_report_changed')
        return value, self.store.read(value['artifact_sha256']), raw

    def download(self, job):
        value, files, raw = self.review_context(None, job)
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_STORED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            archive.writestr('delivery/runtime-report.json', raw)
            archive.writestr('delivery/record.json', canonical_bytes(value))
        self._validate(value)
        return output.getvalue()

    def review_file(self, job, parts):
        """Serve only captured, inventoried evidence alongside the live player."""
        from mimetypes import guess_type
        if not parts or any(not p or p in ('.', '..') or '/' in p or '\\' in p for p in parts):
            raise PipelineRunError('pipeline_artifact_not_found')
        value, _ = self._preview_record(job)
        name = '/'.join(parts)
        expected = value['runtime']['files'].get(name)
        if expected is None:
            raise PipelineRunError('pipeline_artifact_not_found')
        root = directory(self.folder(job) / value['attempt'] / 'runtime')
        raw = read_real_file(root.joinpath(*parts), 256 << 20, 'delivery evidence')
        if sha256(raw).hexdigest() != expected:
            raise PipelineRunError('production_delivery_report_changed')
        return raw, guess_type(name)[0] or 'application/octet-stream'

    def _preview_record(self, job):
        """An immutable capture preview; upstream rebuild gates stay on writes/download."""
        value = self.get(job)
        if value['status'] not in ('needs_review', 'stage_accepted'):
            raise PipelineRunError('production_delivery_not_ready')
        for source in value['request']['sources']:
            run = self.production.get(source['run_id'])
            joint = run['stages']['joint']
            child = self.production.driver.motions.get(source['job_id'])
            if (joint.get('job_id') != source['job_id'] or joint.get('status') != 'succeeded'
                    or joint.get('artifact_sha256') != source['artifact_sha256']
                    or child.get('status') != 'succeeded'
                    or child.get('result', {}).get('artifact_sha256') != source['artifact_sha256']):
                raise PipelineRunError('production_delivery_source_changed')
        if not re.fullmatch('attempt-[a-f0-9]{32}', value['attempt']):
            raise PipelineRunError('production_delivery_invalid')
        root = directory(self.folder(job)/value['attempt']/'runtime')
        raw = read_real_file(root/'report.json', 256 << 20, 'delivery runtime report')
        if sha256(raw).hexdigest() != value['runtime']['files']['report.json']:
            raise PipelineRunError('production_delivery_report_changed')
        return value, raw

    def player_context(self, project, job):
        value, raw = self._preview_record(job)
        folder = directory(self.store.root/value['artifact_sha256'])
        inventory = read_document(folder/'inventory.json')
        if canonical_sha256(inventory) != value['artifact_sha256']:
            raise PipelineRunError('pipeline_artifact_invalid')
        names = [n for n in inventory if n in ('skeleton.json', 'skeleton.atlas') or n.endswith('.png')]
        files = {n: self.store.read_file(value['artifact_sha256'], n) for n in names}
        return value, files, raw

    def close(self):
        self._stop.set()
        self._pool.shutdown(wait=True)
