"""Local-only compatible multi-animation delivery endpoints."""
from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .pipeline_run import PipelineRunError


def manager_for(server):
    from .production_routes import manager_for as production_for
    from .production_delivery import ProductionDeliveries
    owner = server.automation_manager
    with owner._lock:
        if owner._closed:
            raise PipelineRunError('pipeline_manager_closed')
        if owner._production_deliveries is None:
            owner._production_deliveries = ProductionDeliveries(production_for(server))
        return owner._production_deliveries


def dispatch_deliveries(parts, handler, method):
    if parts[:2] != ['api', 'production-deliveries']:
        return False
    from .web_routes import _error, _require_mutation
    tail = parts[2:]
    allowed = ('GET, HEAD, POST, OPTIONS' if not tail else
        'GET, HEAD, OPTIONS' if len(tail) == 1 or len(tail) == 2 and tail[1] == 'download' or
        len(tail) >= 3 and tail[1] == 'view' else
        'POST, OPTIONS' if len(tail) == 2 and tail[1] in ('resume', 'review') else None)
    if allowed is None:
        _error(handler, 404, 'production_delivery_route_not_found')
        return True
    if method == 'OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method == 'OPTIONS' else 405, b'', 'application/json',
                           visual_review=True, extra_headers={'Allow': allowed})
        return True
    try:
        if method == 'POST':
            _require_mutation(handler.headers)
        manager = manager_for(handler.server)
        if method == 'POST':
            body = read_json_object_request(handler, maximum_bytes=128000)
            if not tail:
                value = manager.submit(body)
            elif tail[1] == 'review':
                value = manager.review(tail[0], body)
            else:
                if set(body) != {'expected_revision'}:
                    raise PipelineRunError('production_delivery_request_invalid')
                value = manager.resume(tail[0], body['expected_revision'])
            handler._send_visual_json(202, value)
        elif len(tail) >= 3:
            from .character_player import read
            raw, mime = read(manager, None, tail[0], tail[2:])
            handler._send_bytes(200, raw, mime, visual_review=True)
        elif len(tail) == 2:
            raw = manager.download(tail[0])
            handler._send_bytes(200, raw, 'application/zip', visual_review=True,
                extra_headers={'Content-Disposition': f'attachment; filename="{tail[0]}-candidate.zip"'})
        else:
            handler._send_visual_json(200, manager.get(tail[0]) if tail else dict(deliveries=manager.list()))
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        reason = getattr(exc, 'reason_code', 'production_delivery_failed')
        _error(handler, 403 if reason in ('forbidden_origin', 'forbidden_intent') else 409, reason)
    return True
