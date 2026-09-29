"""Immutable, optimistic revisions for resumable production runs."""
from copy import deepcopy
from datetime import datetime, timezone
import re
from uuid import uuid4

from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.production-run/v1'
STAGES = ('source', 'bindings', 'character', 'body', 'joint', 'review', 'delivery')


def now():
    return datetime.now(timezone.utc).isoformat()


class ProductionJournal:
    def __init__(self, root):
        self.root = root

    def folder(self, run_id, create=False):
        if not isinstance(run_id, str) or not re.fullmatch(r'production-[a-f0-9]{32}', run_id):
            raise PipelineRunError('production_run_id_invalid')
        return directory(self.root / run_id, create=create)

    def create(self, request):
        run_id = 'production-' + uuid4().hex
        self.folder(run_id, True)
        value = dict(schema=SCHEMA, run_id=run_id, revision=0, request=deepcopy(request),
                     status='pending', created_at=now(), updated_at=now(), authority='none',
                     production_authorized=False, stages={s: dict(status='pending', attempts=[]) for s in STAGES})
        return self.append(value, 'created')

    def read(self, run_id):
        files = sorted(self.folder(run_id).glob('revision-*.json'))
        if not files:
            raise PipelineRunError('production_run_not_found')
        value = read_document(files[-1])
        if (value.get('schema') != SCHEMA or value.get('run_id') != run_id
                or files[-1].name != f"revision-{value['revision']:012d}.json"):
            raise PipelineRunError('production_journal_invalid')
        return value

    def append(self, value, event):
        value = deepcopy(value)
        folder = self.folder(value['run_id'])
        value.update(revision=value['revision'] + 1, updated_at=now(), event=event)
        if not publish_document(folder / f"revision-{value['revision']:012d}.json", value,
                                staging=folder / 'staging'):
            raise PipelineRunError('production_revision_conflict')
        return value

    def list(self):
        if not self.root.exists():
            return []
        return sorted((self.read(p.name) for p in self.root.glob('production-*')),
                      key=lambda v: v['created_at'], reverse=True)
