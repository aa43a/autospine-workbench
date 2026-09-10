"""Same-origin asset catalog routes; mutations never remove source files."""
from .asset_library import AssetLibrary
from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .pipeline_run import PipelineRunError


def require_idle(owner, project):
    """Reject hiding a project while a product workflow is still executing."""
    for manager in [owner, getattr(owner, '_animated', None),
                    getattr(owner, '_preparation', None), getattr(owner, '_sleeves', None)]:
        if manager is None:
            continue
        with manager._lock:
            values = [item['response'] for item in getattr(manager, '_active', {}).values()]
            values += list(getattr(manager, '_jobs', {}).values())
            if any(v.get('project_id') == project and v.get('status') in ('pending', 'running') for v in values):
                raise PipelineRunError('asset_job_running')


def active_tasks(owner):
    result = {}
    for kind, manager in [('preview', owner), ('animation', getattr(owner, '_animated', None)),
                          ('preparation', getattr(owner, '_preparation', None)), ('sleeves', getattr(owner, '_sleeves', None))]:
        if manager is None:
            continue
        with manager._lock:
            values = [item['response'] for item in getattr(manager, '_active', {}).values()]
            values += list(getattr(manager, '_jobs', {}).values())
            for value in values:
                if value.get('status') in ('pending', 'running'):
                    result[value['project_id']] = dict(kind=kind, status=value['status'], step=value.get('step'))
    return result


def dispatch_assets(parts, handler, method):
    from .web_routes import _error, _require_mutation
    if parts[:2] != ['api', 'asset-library']:
        return False
    allowed = 'GET, HEAD, OPTIONS' if len(parts) == 2 else 'POST, OPTIONS' if len(parts) == 3 else None
    if allowed is None:
        _error(handler, 404, 'asset_route_not_found')
        return True
    if method == 'OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method == 'OPTIONS' else 405, b'', 'application/json',
                            visual_review=True, extra_headers={'Allow': allowed})
        return True
    try:
        library = AssetLibrary(handler.server.automation_manager.application.projects)
        if method == 'POST':
            _require_mutation(handler.headers)
            body = read_json_object_request(handler, maximum_bytes=2048)
            if body.get('action') in ('archive', 'trash'):
                require_idle(handler.server.automation_manager, parts[2])
            result = library.change(parts[2], body)
        else:
            tasks = active_tasks(handler.server.automation_manager)
            result = dict(schema='autospine.asset-library/v1',
                          projects=[dict(p, current_task=tasks.get(p['id'])) for p in library.list()], authority='none')
        handler._send_visual_json(200, result)
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        reason = getattr(exc, 'reason_code', 'asset_request_failed')
        _error(handler, 403 if reason in ('forbidden_origin', 'forbidden_intent') else 409, reason)
    return True
