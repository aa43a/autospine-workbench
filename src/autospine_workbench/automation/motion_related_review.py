"""Registration-scoped human reviews; immutable candidates and baseline stay intact."""
from datetime import datetime, timezone
import re

from ..resolved_project import canonical_sha256
from ..targets.character43.motion_readiness import build
from .motion_stage_review import DECISIONS
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document


def readiness(value, files, registration):
    report = build(files, value['candidate_sha256'], value['runtime'])
    checks = value['evidence'].get('additional_checks')
    if checks:
        for key, stage in [('moving_ankles', '脚端复测'), ('ankle_contact', '接触')]:
            row = dict(stage=stage, status='sampled_pass' if checks[key]['passed'] else 'needs_changes',
                       explanation='当前候选的踝部支点采样复测；不证明鞋底接地或视觉效果。',
                       href='report.json', scope=checks['scope'], samples=checks['samples'],
                       audit_sha256=checks['audit_sha256'], measurement=checks[key])
            old = next((s for s in report['stages'] if s['stage'] == stage), None)
            if old and old['status'] == 'unmeasured':
                old.update(row)
            else:
                if old: row['stage'] += '复测'
                report['stages'].append(row)
    if value['evidence'].get('skirt_checks'):
        report['stages'].append(dict(stage='裙腿局部遮挡', status='unmeasured', href='report.json',
            explanation='选定姿态的假设布面定位；尚不证明完整动作的实际遮挡通过。'))
    if value['evidence'].get('pose_checks'):
        pose = value['evidence']['pose_checks']
        report['stages'].append(dict(stage='源姿态复测', status='unmeasured', href='report.json',
            explanation=f"已复测 {pose['samples']} 个源时刻；骨轴一致性不代表形体或前后关系通过。",
            measurement=pose))
    statuses = {s['status'] for s in report['stages']}
    report.update(profile='external-motion-related-readiness-v1',
        status='needs_changes' if 'needs_changes' in statuses else
               'evidence_incomplete' if 'unmeasured' in statuses else 'stage_review',
        registration_sha256=registration, baseline_sha256=value['baseline_sha256'],
        request_sha256=value['request_sha256'], related_evidence_sha256=canonical_sha256(value['evidence']))
    return report


def _root(manager, job, registration):
    if not isinstance(registration, str) or not re.fullmatch('[a-f0-9]{64}', registration):
        raise PipelineRunError('motion_related_registration_invalid')
    return manager.folder(job) / 'related-stage-reviews' / registration


def history(manager, job, registration):
    root = _root(manager, job, registration)
    if not root.exists(): return []
    directory(root)
    paths = sorted(root.glob('review-*.json'))
    if len(paths) > 1000: raise PipelineRunError('motion_review_revision_limit')
    rows = []; previous = None
    for revision, path in enumerate(paths, 1):
        row = read_document(path)
        if (path.name != f'review-{revision:04d}.json' or row.get('revision') != revision
                or row.get('job_id') != job or row.get('registration_sha256') != registration
                or row.get('previous_sha256') != previous or row.get('decision') not in DECISIONS
                or row.get('authority') != 'none' or row.get('production_authorized') is not False):
            raise PipelineRunError('motion_review_history_invalid')
        rows.append(row); previous = canonical_sha256(row)
    return rows


def _state(job, report, rows, imported):
    digest = canonical_sha256(report)
    current = rows[-1] if rows else None
    applies = bool(current and all(current.get(k) == v for k, v in dict(
        artifact_sha256=report['artifact_sha256'], registration_sha256=report['registration_sha256'],
        evidence_sha256=digest).items()))
    return dict(job_id=job, artifact_sha256=report['artifact_sha256'],
        registration_sha256=report['registration_sha256'], evidence_sha256=digest,
        readiness=report, revision=len(rows), current=current, current_applies=applies,
        evidence_match='exact' if applies else 'not_current', history=rows,
        imported_visual=imported, authority='none', production_authorized=False)


def from_verified(manager, job, registration, value, files):
    """Use already verified immutable content; recheck the mutable source under lock."""
    from .motion_related_candidates import _registration
    report = readiness(value, files, registration)
    with manager._lock:
        current, _ = _registration(manager, job, registration)
        if current != value: raise PipelineRunError('motion_review_evidence_changed')
        return _state(job, report, history(manager, job, registration), value.get('visual'))


def inspect(manager, job, registration):
    from .motion_related_candidates import load
    value, files = load(manager, job, registration)
    return from_verified(manager, job, registration, value, files)


def save(manager, job, registration, body):
    fields = {'registration_sha256', 'artifact_sha256', 'evidence_sha256',
              'expected_revision', 'decision', 'notes'}
    if (set(body) != fields or body.get('decision') not in DECISIONS
            or body.get('registration_sha256') != registration
            or type(body.get('expected_revision')) is not int
            or not isinstance(body.get('notes'), str) or len(body['notes']) > 4000
            or body['decision'] in ('rejected', 'accepted_with_exceptions') and not body['notes'].strip()):
        raise PipelineRunError('motion_review_request_invalid')
    from .motion_related_candidates import load, _registration
    # Hash large artifacts before acquiring the shared job lock.
    value, files = load(manager, job, registration)
    report = readiness(value, files, registration)
    with manager._lock:
        latest, _ = _registration(manager, job, registration)
        if latest != value: raise PipelineRunError('motion_review_evidence_changed')
        state = _state(job, report, history(manager, job, registration), value.get('visual'))
        if body['expected_revision'] != state['revision']:
            raise PipelineRunError('motion_review_revision_changed')
        if any(body[k] != state[k] for k in ('artifact_sha256', 'evidence_sha256')):
            raise PipelineRunError('motion_review_evidence_changed')
        if body['decision'] == 'accepted' and report['status'] != 'stage_review':
            raise PipelineRunError('motion_review_exceptions_require_acknowledgement')
        if body['decision'].startswith('accepted') and not any(
                s['stage'] == 'Runtime' and s['status'] == 'sampled_pass' for s in report['stages']):
            raise PipelineRunError('motion_review_runtime_required')
        revision = state['revision'] + 1
        if revision > 1000: raise PipelineRunError('motion_review_revision_limit')
        row = dict(schema='autospine.motion-related-stage-review/v1', job_id=job,
            registration_sha256=registration, artifact_sha256=state['artifact_sha256'],
            evidence_sha256=state['evidence_sha256'], revision=revision, decision=body['decision'],
            notes=body['notes'].strip(), created_at=datetime.now(timezone.utc).isoformat(),
            previous_sha256=canonical_sha256(state['current']) if state['current'] else None,
            readiness_status=report['status'], authority='none', production_authorized=False,
            scope='human_visual_stage_decision_for_this_registration_only', technical_override=False)
        root = directory(_root(manager, job, registration), create=True)
        if not publish_document(root / f'review-{revision:04d}.json', row, staging=root / 'staging'):
            raise PipelineRunError('motion_review_revision_changed')
        return _state(job, report, state['history'] + [row], value.get('visual'))
