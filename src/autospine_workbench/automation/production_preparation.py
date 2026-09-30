"""Prepare missing inputs and ordinary bindings through existing reversible rules."""
from uuid import uuid4

from .animated_input_index import inspect_registration
from .pipeline_run import PipelineRunError
from .production_submission import reserved_child


def prepare(driver, read, write, stopped):
    value = read()
    request = value['request']
    project = request['project_id']
    manager = driver.motions.character_manager()
    from .production_character_options import launch_options, assert_selected, assert_launch
    options = launch_options(request)
    if request['character_job_id']:
        if 'character_options' in request:
            assert_selected(manager, project, request['character_job_id'], request['character_options'])
        def reused(v):
            for stage in ('source', 'bindings'):
                v['stages'].setdefault(stage, dict(attempts=[])).update(status='reused')
            v['stages']['character'].update(status='succeeded', job_id=request['character_job_id'],
                                            artifact_sha256=request['character_sha256'])
        if value['stages']['character']['status'] != 'succeeded':
            write(reused, 'character_reused')
        return not stopped()
    if value['stages']['source']['status'] != 'succeeded':
        from .input_preparation_application import InputPreparationApplication
        application = InputPreparationApplication(driver.motions.projects)
        write(lambda v: v['stages']['source'].update(status='running'), 'source_preparing')
        outcome = application.prepare(project, request['resolved_sha256'], cancel_requested=stopped)
        if not outcome.get('source_registered'):
            raise PipelineRunError(outcome.get('reason_code') or 'production_source_preparation_failed')
        write(lambda v: v['stages']['source'].update(status='succeeded'), 'source_prepared')
    if stopped():
        return False
    if read()['stages']['bindings']['status'] != 'succeeded':
        from .binding_auto_workflow import prepare_and_apply
        info = inspect_registration(driver.motions.projects, project)
        if info.get('skeleton_status') != 'candidate_requires_review':
            raise PipelineRunError('joint_review_required')
        addresses = info['source_addresses']
        write(lambda v: v['stages']['bindings'].update(status='running'), 'bindings_preparing')
        outcome = prepare_and_apply(driver.motions.projects, project,
            addresses['resolved_project_sha256'], addresses['input_identity_sha256'])
        if outcome['status'] != 'succeeded':
            raise PipelineRunError(outcome.get('reason_code') or 'production_bindings_incomplete')
        write(lambda v: v['stages']['bindings'].update(status='succeeded',
            changed_layer_ids=outcome['changed_layer_ids']), 'bindings_prepared')
    if stopped():
        return False
    row = read()['stages']['character']
    job = row.get('job_id')
    if not job:
        info = manager.overview(project)
        if (read()['stages'].get('sleeves') or not info['can_build'] and
                info.get('reason_code') in ('character_sleeve_candidate_required', 'character_sleeve_unavailable')):
            from .production_sleeves import prepare as prepare_sleeves
            if not prepare_sleeves(driver, read, write, stopped, info):
                return False
            info = manager.overview(project)
            if info.get('sleeve_job_id') != read()['stages']['sleeves']['job_id']:
                raise PipelineRunError('production_sleeve_selection_changed')
        if not info['can_build']:
            raise PipelineRunError(info.get('reason_code') or 'production_character_unavailable')
        job = 'job-' + uuid4().hex
        launch = dict({k: info[k] for k in ('expected_resolved_sha256', 'expected_input_sha256', 'sleeve_job_id')},
                      **options)
        def reserve(v):
            v['stages']['character'].update(job_id=job, launch=launch, status='running', shared=False)
            v['stages']['character']['attempts'].append(dict(job_id=job))
        write(reserve, 'character_reserved')
    if stopped():
        return False
    assert_launch(request, read()['stages']['character'].get('launch', {}))
    if not (manager.root / job / 'request.json').exists():
        with reserved_child(job):
            result = manager.submit(project, **read()['stages']['character']['launch'])
        if result['job_id'] != job:
            # The character service may already have an identical in-flight task.
            job = result['job_id']
            write(lambda v: v['stages']['character'].update(job_id=job, shared=True), 'character_existing_task_attached')
        if stopped():
            if read().get('status') == 'canceled' and not read()['stages']['character'].get('shared'):
                manager.cancel(project, job)
            return False
    while not stopped():
        result = manager.get(project, job)
        if result['status'] not in ('pending', 'running'):
            break
        driver.wait(1)
    else:
        if read().get('status') == 'canceled' and not read()['stages']['character'].get('shared'):
            manager.cancel(project, job)
        return False
    if result['status'] != 'needs_review':
        raise PipelineRunError(result.get('reason_code') or 'production_character_failed')
    verified, _ = manager.verified_snapshot(project, job)
    if 'character_options' in request:
        assert_selected(manager, project, job, request['character_options'], verified=verified)
    def record(v):
        v['stages']['character'].update(status='succeeded', artifact_sha256=verified['artifact_sha256'])
    write(record, 'character_prepared')
    return not stopped()
