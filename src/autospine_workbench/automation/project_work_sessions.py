"""Immutable, reversible operator time segments; no inferred historical labor."""
import math
import re
from datetime import datetime
from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.project-work-session/v1'
STAGES = ('source_preparation', 'joints', 'bindings', 'sleeves', 'visual_review', 'auto_audit', 'other')


def interval(value):
    try:
        start, end = (datetime.fromisoformat(value[k].replace('Z', '+00:00')) for k in ('started_at', 'ended_at'))
        if start.tzinfo is None or end.tzinfo is None: raise ValueError()
        seconds = value['seconds']
        if (type(seconds) not in (int, float) or not math.isfinite(seconds)
                or not 0 < seconds <= 86400 or not 0 < (end-start).total_seconds() <= 86400
                or abs(seconds-(end-start).total_seconds()) > 2): raise ValueError()
        return start, end
    except (ValueError, TypeError, KeyError, AttributeError):
        raise PipelineRunError('work_session_invalid') from None


def valid_segment(value):
    keys = {'session_id', 'stage', 'started_at', 'ended_at', 'seconds', 'method'}
    if (type(value) is not dict or set(value) != keys or value['stage'] not in STAGES
            or value['method'] != 'operator_stopwatch_segment_v1'
            or type(value['session_id']) is not str or not re.fullmatch('[a-f0-9]{32}', value['session_id'])):
        raise PipelineRunError('work_session_invalid')
    interval(value)


def overview(manager, project):
    require_safe_token(project, 'project')
    source = canonical_sha256(manager.projects.get_project(project)['source'])
    root = manager.root/'work-sessions'/project
    head = None; revision = -1; active = {}; seen = set()
    if root.exists():
        directory(root)
        for index, path in enumerate(sorted(root.glob('*.json'))):
            doc = read_document(path)
            keys = {'schema', 'project_id', 'source_sha256', 'revision', 'previous_sha256', 'action', 'payload', 'authority'}
            if (set(doc) != keys or doc['schema'] != SCHEMA or doc['project_id'] != project
                    or type(doc['revision']) is not int or doc['revision'] != index
                    or path.name != f'{index:06d}.json' or doc['previous_sha256'] != head
                    or doc['authority'] != 'none' or type(doc['source_sha256']) is not str
                    or not re.fullmatch('[a-f0-9]{64}', doc['source_sha256'])):
                raise PipelineRunError('work_session_history_invalid')
            if doc['action'] == 'record':
                segment = doc['payload']; valid_segment(segment)
                sid = segment['session_id']
                if sid in seen: raise PipelineRunError('work_session_history_invalid')
                start, end = interval(segment)
                if any(start < interval(s)[1] and interval(s)[0] < end for s in active.values()
                       if s['source_sha256'] == doc['source_sha256']):
                    raise PipelineRunError('work_session_history_invalid')
                seen.add(sid); active[sid] = dict(segment, source_sha256=doc['source_sha256'])
            elif doc['action'] == 'revoke':
                sid = doc['payload']
                if type(sid) is not str or sid not in active: raise PipelineRunError('work_session_history_invalid')
                del active[sid]
            else: raise PipelineRunError('work_session_history_invalid')
            head = canonical_sha256(doc); revision = index
    current = [s for s in active.values() if s['source_sha256'] == source]
    return dict(project_id=project, source_sha256=source, head_sha256=head, revision=revision,
                authority='none', sessions=current, used_session_ids=sorted(seen),
                metrics=dict(scope='recorded_post_import_operator_segments_only',
                    recorded_minutes=math.fsum(s['seconds'] for s in current)/60 if current else None,
                    stage_minutes={stage: math.fsum(s['seconds'] for s in current if s['stage']==stage)/60
                        if any(s['stage']==stage for s in current) else None for stage in STAGES},
                    total_human_minutes=None, completeness='partial_not_full_workflow'))


def save(manager, project, body):
    if set(body) != {'expected_head_sha256', 'expected_source_sha256', 'action', 'payload'}:
        raise PipelineRunError('work_session_invalid')
    with manager._lock:
        current = overview(manager, project)
        if (body['expected_head_sha256'] != current['head_sha256']
                or body['expected_source_sha256'] != current['source_sha256']):
            raise PipelineRunError('character_review_conflict')
        if body['action'] == 'record':
            segment = body['payload']; valid_segment(segment)
            if segment['session_id'] in current['used_session_ids']: raise PipelineRunError('work_session_duplicate')
            start, end = interval(segment)
            for old in current['sessions']:
                a, b = interval(old)
                if start < b and a < end: raise PipelineRunError('work_session_overlap')
        elif body['action'] == 'revoke':
            if body['payload'] not in [s['session_id'] for s in current['sessions']]:
                raise PipelineRunError('work_session_not_found')
        else: raise PipelineRunError('work_session_invalid')
        doc = dict(schema=SCHEMA, project_id=project, source_sha256=current['source_sha256'],
                   revision=current['revision']+1, previous_sha256=current['head_sha256'],
                   action=body['action'], payload=body['payload'], authority='none')
        root = directory(manager.root/'work-sessions'/project, create=True)
        if not publish_document(root/f'{doc["revision"]:06d}.json', doc, staging=root/'staging'):
            raise PipelineRunError('character_review_conflict')
        return overview(manager, project)


def summarize(observations):
    measured = [o['verified_work_sessions']['metrics']['recorded_minutes'] for o in observations.values()
                if o.get('verified_work_sessions', {}).get('metrics', {}).get('recorded_minutes') is not None]
    return dict(scope='recorded_post_import_operator_segments_only', measured_projects=len(measured),
                total_projects=len(observations), recorded_minutes=math.fsum(measured) if measured else None,
                total_human_minutes=None, completeness='partial_not_full_workflow')
