"""Same-origin preparation API; runner configuration never comes from HTTP."""
from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .input_preparation_jobs import InputPreparationJobs
from .pipeline_run import PipelineRunError


def manager_for(server):
    owner = server.automation_manager
    with owner._lock:
        if owner._closed:
            raise PipelineRunError('pipeline_manager_closed')
        if owner._preparation is None:
            owner._preparation = InputPreparationJobs(owner.application.projects)
        return owner._preparation


def dispatch_preparation(tail, handler, method, project_id):
    from .web_routes import _error, _require_mutation
    allowed = 'GET, HEAD, POST, OPTIONS' if not tail else \
        'GET, HEAD, OPTIONS' if len(tail) == 2 and tail[0] == 'jobs' else \
        'POST, OPTIONS' if len(tail) == 3 and tail[0] == 'jobs' and tail[2] == 'cancel' else None
    if allowed is None:
        _error(handler, 404, 'pipeline_route_not_found')
        return True
    if method == 'OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method == 'OPTIONS' else 405, b'', 'application/json',
                            extra_headers={'Allow': allowed}, visual_review=True)
        return True
    try:
        if method == 'POST':
            _require_mutation(handler.headers)
            body = read_json_object_request(handler, maximum_bytes=2048)
            if not tail:
                if set(body) != {'expected_resolved_sha256'}:
                    raise PipelineRunError('pipeline_request_invalid')
                value = manager_for(handler.server).submit(project_id, **body)
            else:
                if body:
                    raise PipelineRunError('pipeline_request_invalid')
                value = manager_for(handler.server).cancel(project_id, tail[1])
            handler._send_visual_json(202, value)
        else:
            manager = manager_for(handler.server)
            value = manager.application.overview(project_id) if not tail else manager.get(project_id, tail[1])
            handler._send_visual_json(200, value)
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        reason = getattr(exc, 'reason_code', 'preparation_request_failed')
        status = 403 if reason in {'forbidden_origin', 'forbidden_intent'} else \
                 404 if reason == 'pipeline_job_not_found' else 409 if reason == 'pipeline_queue_full' else 400
        _error(handler, status, reason)
    return True
