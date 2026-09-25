"""Versioned intervention plans; never a repair or an acceptance decision."""
import json
from datetime import datetime, timezone

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

ACTIONS = {'local_repair', 'partition', 'region_order', 'pose_attachment', 'contact_scope', 'withdraw'}


def evidence(manager, job):
    from .motion_target_jobs import review_file
    report = json.loads(review_file(manager, job, ['geometry-details.json'])[0])
    # Keep event geometry and identities, not embedded texture bytes.
    report = {**report, 'rows': [{k: v for k, v in row.items() if k != 'texture'}
                               for row in report.get('rows', [])]}
    return report, canonical_sha256(report)


def history(manager, job):
    root = manager.folder(job) / 'repair-drafts'
    if not root.exists():
        return []
    directory(root)
    paths = sorted(root.glob('draft-*.json'))
    if len(paths) > 1000:
        raise PipelineRunError('motion_draft_revision_limit')
    rows = []; previous = None
    for revision, path in enumerate(paths, 1):
        row = read_document(path)
        if (path.name != f'draft-{revision:04d}.json' or row.get('revision') != revision
                or row.get('job_id') != job or row.get('previous_sha256') != previous):
            raise PipelineRunError('motion_draft_history_invalid')
        rows.append(row); previous = canonical_sha256(row)
    return rows


def _state(job, report, digest, rows):
    return dict(job_id=job, artifact_sha256=report['artifact_sha256'],
                evidence_sha256=digest, revision=len(rows), history=rows,
                draft_sha256s=[canonical_sha256(row) for row in rows],
                authority='none', repair_executed=False, production_authorized=False)


def inspect(manager, job):
    report, digest = evidence(manager, job)
    with manager._lock:
        return _state(job, report, digest, history(manager, job))


def save(manager, job, body):
    fields = {'artifact_sha256', 'evidence_sha256', 'expected_revision', 'action',
              'notes', 'slot', 'animation', 'triangle', 'time'}
    if (set(body)-{'partition', 'region_order', 'view_needs', 'contact_scope'} != fields or body.get('action') not in ACTIONS
            or type(body.get('expected_revision')) is not int
            or type(body.get('triangle')) is not int
            or type(body.get('time')) not in (int, float)
            or not isinstance(body.get('notes'), str) or len(body['notes']) > 4000):
        raise PipelineRunError('motion_draft_request_invalid')
    from .motion_material_scope import validate as validate_views
    views=validate_views(body['action'],body.get('view_needs'))
    report, digest = evidence(manager, job)
    from .motion_partition_draft import validate, validate_order
    partition = validate(manager,job,body)
    region_order = validate_order(manager,job,body)
    from .motion_contact_scope import validate as validate_contact
    contact_scope = validate_contact(manager, job, body)
    matches = [detail for row in report.get('rows', [])
               if row['slot'] == body['slot'] and row['animation'] == body['animation']
               for detail in row['details']
               if detail['triangle'] == body['triangle'] and detail['time'] == body['time']]
    if len(matches) != 1:
        raise PipelineRunError('motion_draft_event_not_found')
    with manager._lock:
        rows = history(manager, job)
        state = _state(job, report, digest, rows)
        if body['expected_revision'] != state['revision']:
            raise PipelineRunError('motion_draft_revision_changed')
        if any(body[k] != state[k] for k in ('artifact_sha256', 'evidence_sha256')):
            raise PipelineRunError('motion_draft_evidence_changed')
        revision = len(rows) + 1
        if revision > 1000:
            raise PipelineRunError('motion_draft_revision_limit')
        row = dict(schema='autospine.motion-repair-draft/v1', job_id=job,
                   revision=revision, artifact_sha256=state['artifact_sha256'],
                   evidence_sha256=digest, slot=body['slot'], animation=body['animation'],
                   event=matches[0], action=body['action'], notes=body['notes'].strip(),
                   created_at=datetime.now(timezone.utc).isoformat(),
                   previous_sha256=canonical_sha256(rows[-1]) if rows else None,
                   authority='none', repair_executed=False)
        if partition is not None:row['partition']=partition
        if views is not None:row['view_needs']=views
        if region_order is not None:row['region_order']=region_order
        if contact_scope is not None:row['contact_scope']=contact_scope
        root = directory(manager.folder(job) / 'repair-drafts', create=True)
        if not publish_document(root / f'draft-{revision:04d}.json', row, staging=root / 'staging'):
            raise PipelineRunError('motion_draft_revision_changed')
        return _state(job, report, digest, rows + [row])
