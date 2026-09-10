"""HTTP bridge for explicit workflow routing choices."""
from .project_route import ProjectRoute
from ..http_json_request import HttpJsonRequestError, read_json_object_request


def dispatch_route(handler, method, project):
    from .web_routes import _require_mutation, _error
    allowed = 'GET, HEAD, POST, OPTIONS'
    if method == 'OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method == 'OPTIONS' else 405, b'', 'application/json',
                            visual_review=True, extra_headers={'Allow': allowed})
        return True
    try:
        service = ProjectRoute(handler.server.automation_manager.application.projects)
        if method == 'POST':
            _require_mutation(handler.headers)
            result = service.save(project, read_json_object_request(handler, maximum_bytes=2048))
        else:
            result = service.get(project)
        handler._send_visual_json(200, result)
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        reason = getattr(exc, 'reason_code', 'project_route_failed')
        _error(handler, 403 if reason in ('forbidden_origin', 'forbidden_intent') else 409, reason)
    return True
