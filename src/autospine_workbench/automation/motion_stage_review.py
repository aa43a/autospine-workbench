"""Append-only human stage decisions, bound to exact candidate and QA evidence."""
from datetime import datetime, timezone

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

DECISIONS = {'accepted', 'accepted_with_exceptions', 'rejected', 'revoked'}


def evidence(manager, job):
    import json
    from .motion_target_jobs import review_file
    report = json.loads(review_file(manager, job, ['readiness.json'])[0])
    return report, canonical_sha256(report)


def history(manager, job):
    root = manager.folder(job) / 'stage-reviews'
    if not root.exists():
        return []
    directory(root)
    paths = sorted(root.glob('review-*.json'))
    if len(paths) > 1000:
        raise PipelineRunError('motion_review_revision_limit')
    rows = []; previous = None
    for revision, path in enumerate(paths, 1):
        row = read_document(path)
        if (path.name != f'review-{revision:04d}.json' or row.get('revision') != revision
                or row.get('job_id') != job or row.get('previous_sha256') != previous):
            raise PipelineRunError('motion_review_history_invalid')
        rows.append(row); previous = canonical_sha256(row)
    return rows


def inspect(manager, job):
    with manager._lock:
        report, digest = evidence(manager, job)
        rows = history(manager, job)
        current = rows[-1] if rows else None
        applies = bool(current and current['artifact_sha256'] == report['artifact_sha256']
                       and current['evidence_sha256'] == digest)
        return dict(job_id=job, artifact_sha256=report['artifact_sha256'], evidence_sha256=digest,
                    readiness=report, revision=len(rows), current=current,
                    current_applies=applies, history=rows, authority='none', production_authorized=False)


def save(manager, job, body):
    fields = {'artifact_sha256', 'evidence_sha256', 'expected_revision', 'decision', 'notes'}
    if (set(body) != fields or body.get('decision') not in DECISIONS
            or type(body.get('expected_revision')) is not int
            or not isinstance(body.get('notes'), str) or len(body['notes']) > 4000
            or body['decision'] in ('rejected', 'accepted_with_exceptions') and not body['notes'].strip()):
        raise PipelineRunError('motion_review_request_invalid')
    with manager._lock:
        state = inspect(manager, job)
        if body['expected_revision'] != state['revision']:
            raise PipelineRunError('motion_review_revision_changed')
        if any(body[key] != state[key] for key in ('artifact_sha256', 'evidence_sha256')):
            raise PipelineRunError('motion_review_evidence_changed')
        if body['decision'] == 'accepted' and state['readiness']['status'] != 'stage_review':
            raise PipelineRunError('motion_review_exceptions_require_acknowledgement')
        if body['decision'].startswith('accepted') and not any(
                s['stage'] == 'Runtime' and s['status'] == 'sampled_pass'
                for s in state['readiness']['stages']):
            raise PipelineRunError('motion_review_runtime_required')
        revision = state['revision'] + 1
        if revision > 1000:
            raise PipelineRunError('motion_review_revision_limit')
        root = directory(manager.folder(job) / 'stage-reviews', create=True)
        row = dict(schema='autospine.motion-stage-review/v1', job_id=job, revision=revision,
                   artifact_sha256=state['artifact_sha256'], evidence_sha256=state['evidence_sha256'],
                   decision=body['decision'], notes=body['notes'].strip(),
                   created_at=datetime.now(timezone.utc).isoformat(),
                   previous_sha256=canonical_sha256(state['current']) if state['current'] else None,
                   readiness_status=state['readiness']['status'], authority='none',
                   scope='human_visual_stage_decision_does_not_override_technical_checks',
                   production_authorized=False)
        if not publish_document(root / f'review-{revision:04d}.json', row, staging=root / 'staging'):
            raise PipelineRunError('motion_review_revision_changed')
        return inspect(manager, job)
