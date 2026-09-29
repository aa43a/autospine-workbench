"""Bring a verified existing body into a durable production run without rebaking."""
from .pipeline_run import PipelineRunError
from .production_body_selection import select


OPTIONS=('contact_correction','clip','projection','projection_selection','depth_review_profile',
         'torso_projection_profile','pose_profile','moving_ankle_profile','layer_edits','layer_edit_receipt')


def prepare(driver,body):
    from .motion_joint_source import source_context
    from ..targets.character43.joint_animation_config import defaults
    if (not isinstance(body,dict) or set(body)-{'body_job_id','registration_sha256','joint_config'}
            or 'body_job_id' not in body):
        raise PipelineRunError('production_existing_body_request_invalid')
    job=body['body_job_id'];registration=body.get('registration_sha256')
    resolved=source_context(driver.motions,job,registration)
    source=resolved['request']
    request=driver.freeze(dict(project_id=source['project_id'],character_job_id=source['character_job_id'],
        source_job_id=source['source_job_id'],body_options={k:source[k] for k in OPTIONS if k in source},
        joint_config=body.get('joint_config',defaults())))
    # Even a baseline import pins its exact existing body rather than merely its settings.
    request['body_selection']=select(driver,request,job,registration or 'job:'+job)
    return request,dict(status='succeeded',job_id=job,artifact_sha256=resolved['parent']['result']['artifact_sha256'],
        attempts=[],basis='verified_existing_body')


def submit(manager,body):
    request,stage=prepare(manager.driver,body)
    with manager._lock:
        manager._require_open()
        for old in manager.list():
            if old['request']==request and old['status'] not in ('canceled','blocked'):
                manager._schedule(old['run_id']);return old
        value=manager.journal.create(request)
        value['stages']['body']=stage
        value['stages']['character'].update(status='succeeded',job_id=request['character_job_id'],artifact_sha256=request['character_sha256'])
        for name in ('source','bindings'):
            value['stages'][name].update(status='reused',basis='verified_existing_body')
        value['reused_stages']=['source','bindings','character','body']
        value=manager.journal.append(value,'existing_body_attached')
        manager._schedule(value['run_id'])
        return value
