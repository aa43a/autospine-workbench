"""Persist the exact saved sleeve dependency before composing a character."""
from uuid import uuid4

from .pipeline_run import PipelineRunError
from .production_journal import now
from .production_submission import reserved_child
from .storage_io import read_document


def prepare(driver, read, write, stopped, info):
    manager = driver.motions.character_manager().sleeves
    project = read()['request']['project_id']
    row = read()['stages'].get('sleeves', {})
    if not row.get('job_id'):
        status = manager.overview(project)
        if not status['can_build']:
            raise PipelineRunError('sleeve_annotation_required')
        latest = status.get('job')
        if latest and latest.get('candidate_withdrawn'):
            raise PipelineRunError('sleeve_candidate_withdrawn')
        shared = bool(latest and latest['status'] in ('pending', 'running'))
        # A failed independent attempt requires an explicit retry, not an
        # implicit new repair every time the production page is resumed.
        if latest and not shared and not row and latest['status'] != 'needs_review':
            raise PipelineRunError(latest.get('reason_code') or 'character_sleeve_unavailable')
        launch = dict(expected_resolved_sha256=info['expected_resolved_sha256'],
                      expected_draft_sha256=manager._draft_sha(project))
        job = latest['job_id'] if shared else 'job-' + uuid4().hex

        def reserve(v):
            stage = v['stages'].setdefault('sleeves', dict(attempts=[]))
            stage.update(status='running', job_id=job, launch=launch, shared=shared,
                         started_at=now())
            stage['attempts'].append(dict(job_id=job, shared=shared, reserved_at=now()))
        write(reserve, 'sleeves_reserved')
    if stopped():
        return False
    row = read()['stages']['sleeves']; job = row['job_id']; launch = row['launch']
    if manager._draft_sha(project) != launch['expected_draft_sha256']:
        raise PipelineRunError('sleeve_draft_changed')
    path = manager.root/job/'request.json'
    if not path.exists():
        with reserved_child(job):
            result = manager.submit(project, **launch)
        if result['job_id'] != job:
            job = result['job_id']
            write(lambda v: v['stages']['sleeves'].update(job_id=job, shared=True),
                  'sleeves_existing_task_attached')
        path = manager.root/job/'request.json'
    request = read_document(path)
    if (request['project_id'] != project or
            request['expected_resolved_sha256'] != launch['expected_resolved_sha256'] or
            request['draft_sha256'] != launch['expected_draft_sha256']):
        raise PipelineRunError('production_sleeve_source_changed')
    manager._assert_current(request)
    while not stopped():
        result = manager.get(project, job)
        if result['status'] not in ('pending', 'running'):
            break
        driver.wait(1)
    else:
        # Cancellation can race publication: the coordinator may have observed
        # the reservation before the child request existed. Never cancel a
        # borrowed task or treat service shutdown as a user cancellation.
        current = read()
        if current.get('status') == 'canceled' and not current['stages']['sleeves'].get('shared'):
            manager.cancel(project, job)
        return False
    if result['status'] != 'needs_review' or result.get('candidate_withdrawn'):
        raise PipelineRunError(result.get('reason_code') or 'character_sleeve_unavailable')
    manager._assert_current(request)
    write(lambda v: v['stages']['sleeves'].update(status='succeeded', finished_at=now()),
          'sleeves_prepared')
    return True
