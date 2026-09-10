"""Project sleeve editor preparation and explicit draft save endpoints."""
from .sleeve_onboarding import SleeveOnboarding
from .pipeline_run import PipelineRunError
from ..http_json_request import HttpJsonRequestError, read_json_object_request


def dispatch_annotation(tail, handler, method, project):
    from .web_routes import _error, _require_mutation
    allowed = 'GET, HEAD, OPTIONS' if tail in ([], ['view']) else 'POST, OPTIONS' if tail in (['prepare'], ['save']) else None
    if allowed is None:
        _error(handler, 404, 'sleeve_annotation_route_not_found')
        return True
    if method == 'OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method == 'OPTIONS' else 405, b'', 'application/json',
                            visual_review=True, extra_headers={'Allow': allowed})
        return True
    try:
        service = SleeveOnboarding(handler.server.automation_manager.application.projects)
        if method == 'POST':
            _require_mutation(handler.headers)
            body = read_json_object_request(handler, maximum_bytes=16 << 20)
            if tail == ['prepare']:
                if set(body) != {'expected_resolved_sha256'}:
                    raise PipelineRunError('sleeve_annotation_request_invalid')
                result = service.prepare(project, body['expected_resolved_sha256'])
            else:
                result = service.save(project, body)
            handler._send_visual_json(200, result)
        elif tail == ['view']:
            handler._send_bytes(200, service.page(project), 'text/html; charset=utf-8', visual_review=True)
        else:
            handler._send_visual_json(200, service.status(project))
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        reason = getattr(exc, 'reason_code', 'sleeve_annotation_failed')
        _error(handler, 403 if reason in ('forbidden_origin', 'forbidden_intent') else 409, reason)
    return True
