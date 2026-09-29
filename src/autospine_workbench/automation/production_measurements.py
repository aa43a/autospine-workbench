"""Run-scoped operator segments and clearly bounded orchestration durations."""
from datetime import datetime, timezone
import math

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .project_work_sessions import valid_segment, interval, STAGES
from .storage_io import directory, read_document, publish_document


def overview(manager, run_id):
    run = manager.get(run_id)
    source = canonical_sha256(run['request'])
    root = manager.journal.folder(run_id)/'measurements'
    head, active, seen = None, {}, set()
    revision = -1
    if root.exists():
        directory(root)
        for index,path in enumerate(sorted(root.glob('*.json'))):
            row = read_document(path)
            if (set(row) != {'schema','run_id','source_sha256','previous_sha256','revision','action','payload','authority'}
                    or row.get('authority') != 'none' or type(row.get('revision')) is not int
                    or row.get('schema') != 'autospine.production-work-session/v1' or row.get('run_id') != run_id
                    or row.get('source_sha256') != source or row.get('previous_sha256') != head
                    or row.get('revision') != index or path.name != f'{index:06d}.json'):
                raise PipelineRunError('production_measurement_history_invalid')
            if row['action'] == 'record':
                segment = row['payload'];valid_segment(segment)
                start,end = interval(segment)
                if segment['session_id'] in seen or any(start < interval(s)[1] and interval(s)[0] < end for s in active.values()):
                    raise PipelineRunError('production_measurement_history_invalid')
                seen.add(segment['session_id']);active[segment['session_id']] = dict(segment,source_sha256=source)
            elif row['action'] == 'revoke' and row['payload'] in active:
                del active[row['payload']]
            else:
                raise PipelineRunError('production_measurement_history_invalid')
            head=canonical_sha256(row);revision=index
    sessions=list(active.values())
    return dict(run_id=run_id,project_id=run_id,source_sha256=source,head_sha256=head,revision=revision,
        authority='none',sessions=sessions,used_session_ids=sorted(seen),metrics=dict(
            scope='explicit_operator_segments_for_this_production_run_only',
            recorded_minutes=math.fsum(s['seconds'] for s in sessions)/60 if sessions else None,
            stage_minutes={stage:math.fsum(s['seconds'] for s in sessions if s['stage']==stage)/60
                           if any(s['stage']==stage for s in sessions) else None for stage in STAGES},
            total_human_minutes=None,completeness='partial_not_full_workflow'))


def save(manager,run_id,body):
    if type(body) is not dict or set(body) != {'expected_head_sha256','expected_source_sha256','action','payload'}:
        raise PipelineRunError('work_session_invalid')
    with manager._lock:
        current=overview(manager,run_id)
        if body['expected_head_sha256'] != current['head_sha256'] or body['expected_source_sha256'] != current['source_sha256']:
            raise PipelineRunError('production_measurement_conflict')
        payload=body['payload']
        if body['action']=='record':
            valid_segment(payload)
            if payload['session_id'] in current['used_session_ids']:
                raise PipelineRunError('work_session_duplicate')
            start,end=interval(payload)
            created=datetime.fromisoformat(manager.get(run_id)['created_at'])
            if start < created or end > datetime.now(timezone.utc):
                raise PipelineRunError('production_measurement_outside_run')
            if any(start<interval(s)[1] and interval(s)[0]<end for s in current['sessions']):
                raise PipelineRunError('work_session_overlap')
        elif body['action']=='revoke':
            if payload not in [s['session_id'] for s in current['sessions']]:
                raise PipelineRunError('work_session_not_found')
        else:
            raise PipelineRunError('work_session_invalid')
        row=dict(schema='autospine.production-work-session/v1',run_id=run_id,source_sha256=current['source_sha256'],
            revision=current['revision']+1,previous_sha256=current['head_sha256'],action=body['action'],payload=payload,authority='none')
        root=directory(manager.journal.folder(run_id)/'measurements',create=True)
        if not publish_document(root/f'{row["revision"]:06d}.json',row,staging=root/'staging'):
            raise PipelineRunError('production_measurement_conflict')
        return overview(manager,run_id)


def metrics(manager,run_id):
    run=manager.get(run_id);attempts={};blocks=set();retries=0
    for path in sorted(manager.journal.folder(run_id).glob('revision-*.json')):
        row=read_document(path)
        if row.get('event')=='retry_requested':retries+=1
        if row.get('status')=='blocked':
            blocks.add((row.get('reason_code'),tuple((k,v.get('job_id')) for k,v in sorted(row['stages'].items()))))
        for stage,value in row['stages'].items():
            start,end=value.get('started_at'),value.get('finished_at')
            if start and end and value.get('job_id'):
                seconds=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
                attempts[(stage,value['job_id'])]=dict(stage=stage,job_id=value['job_id'],seconds=max(0,seconds),status=value['status'])
    stop=run['updated_at'] if run['status'] in ('stage_accepted','canceled') else datetime.now(timezone.utc).isoformat()
    elapsed=(datetime.fromisoformat(stop)-datetime.fromisoformat(run['created_at'])).total_seconds()
    measured=[]
    for row in attempts.values():
        row['execution_seconds']=None
        if not row['job_id'].startswith('motion-'):
            continue
        try:
            child=manager.driver.motions.get(row['job_id'],check_current=False)
            duration=child.get('elapsed_seconds')
            if (child['job_id']==row['job_id'] and child['status'] in ('succeeded','failed','canceled')
                    and type(duration) in (int,float) and math.isfinite(duration) and duration>=0):
                row['execution_seconds']=duration;measured.append(duration)
        except (OSError,RuntimeError,ValueError,KeyError,TypeError):
            row['execution_measurement_status']='unavailable'
    return dict(run_id=run_id,run_revision=run['revision'],human=overview(manager,run_id)['metrics'],
        task_elapsed_seconds=max(0,elapsed),task_elapsed_scope='production_creation_onward_includes_waiting_not_PSD_upload',
        observed_child_intervals=list(attempts.values()),observed_child_scope='reservation_to_observed_finish_includes_queue_and_restart_delays',
        automatic_compute_seconds=None,waiting_seconds=None,blocked_observations=len(blocks),retry_requests=retries,
        recorded_execution_seconds=math.fsum(measured) if measured else None,
        execution_measured_attempts=len(measured),execution_unmeasured_attempts=len(attempts)-len(measured),
        execution_scope='recorded_terminal_worker_elapsed_includes_IO_and_capture_not_CPU_time',
        stages_without_observed_intervals=[s for s in ('source','bindings','character','body','joint')
                                          if s in run['stages'] and not any(r['stage']==s for r in attempts.values())],
        intervention_count=None,scope='journal_observations_are_not_human_interventions',authority='none')
