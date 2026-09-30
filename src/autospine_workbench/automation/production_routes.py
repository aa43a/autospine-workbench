"""Same-origin production coordinator endpoints."""
from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .pipeline_run import PipelineRunError


def manager_for(server):
    from .motion_intake_routes import manager_for as motions_for
    from .production_driver import ProductionDriver
    from .production_jobs import ProductionJobs
    owner = server.automation_manager
    with owner._lock:
        if owner._closed:
            raise PipelineRunError('pipeline_manager_closed')
        if owner._production is None:
            owner._production = ProductionJobs(owner.application.projects.state_root / 'jobs/production-v1',
                                               ProductionDriver(motions_for(server)))
        return owner._production


def dispatch_production(parts, handler, method):
    if parts[:2] != ['api', 'production']:
        return False
    from .web_routes import _error, _require_mutation
    tail = parts[2:]
    allowed = ('POST, OPTIONS' if tail==['from-body'] else 'GET, HEAD, POST, OPTIONS' if not tail or len(tail)==2 and tail[1]=='work-sessions' else 'GET, HEAD, OPTIONS' if len(tail) == 1 or
               len(tail) == 2 and tail[1] in ('coverage','metrics','body-candidates')
               else 'POST, OPTIONS' if len(tail) == 2 and tail[1] in ('resume', 'cancel', 'retry', 'revise','revision-plan') else None)
    if allowed is None:
        _error(handler, 404, 'production_route_not_found')
        return True
    if method == 'OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method == 'OPTIONS' else 405, b'', 'application/json',
                            visual_review=True, extra_headers={'Allow': allowed})
        return True
    try:
        if method == 'POST':
            _require_mutation(handler.headers)
        if tail == ['options'] and method in ('GET', 'HEAD'):
            from ..targets.character43.joint_animation_config import defaults
            from .motion_camera_policy import PROFILE, ANKLE_PROFILE
            handler._send_visual_json(200, dict(joint_config=defaults(), body_options=dict(
                contact_correction=False, pose_profile=PROFILE, moving_ankle_profile=ANKLE_PROFILE,
                projection=dict(profile=PROFILE, keys=[dict(time=0, yaw=0)]))))
            return True
        manager = manager_for(handler.server)
        if method == 'POST':
            body = read_json_object_request(handler, maximum_bytes=128000)
            if not tail:
                result = manager.submit(body)
            elif tail==['from-body']:
                from .production_existing_body import submit
                result=submit(manager,body)
            elif tail[1]=='work-sessions':
                from .production_measurements import save
                result=save(manager,tail[0],body)
            elif tail[1] in ('revise','revision-plan'):
                if set(body) - {'expected_revision', 'joint_config','body_options','expected_plan_sha256','body_registration'} or 'expected_revision' not in body:
                    raise PipelineRunError('production_request_invalid')
                if tail[1]=='revision-plan':
                    from .production_revision import plan
                    result=plan(manager,tail[0],body['expected_revision'],body.get('joint_config'),body.get('body_options'),body.get('body_registration'))
                else:
                    result = manager.revise(tail[0], body['expected_revision'], body.get('joint_config'),
                        body.get('body_options'),body.get('expected_plan_sha256'),body.get('body_registration'))
            else:
                if set(body) != {'expected_revision'}:
                    raise PipelineRunError('production_request_invalid')
                result = getattr(manager, tail[1])(tail[0], body['expected_revision'])
            if isinstance(result, dict) and 'run_id' in result and 'stages' in result:
                result = manager.execution_view(result)
            handler._send_visual_json(202, result)
        elif len(tail)==2 and tail[1]=='body-candidates':
            from .production_body_selection import candidates
            handler._send_visual_json(200,candidates(manager,tail[0]))
        elif len(tail)==2 and tail[1] in ('metrics','work-sessions'):
            from .production_measurements import metrics,overview
            handler._send_visual_json(200,(metrics if tail[1]=='metrics' else overview)(manager,tail[0]))
        elif len(tail) == 2 and tail[1] == 'coverage':
            from .production_coverage import inspect
            handler._send_visual_json(200, inspect(manager, tail[0]))
        else:
            handler._send_visual_json(200, manager.execution_view(manager.get(tail[0])) if tail else
                                      dict(runs=[manager.execution_view(row) for row in manager.list()]))
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        reason = getattr(exc, 'reason_code', 'production_request_failed')
        _error(handler, 403 if reason in ('forbidden_origin', 'forbidden_intent') else 409, reason)
    return True
