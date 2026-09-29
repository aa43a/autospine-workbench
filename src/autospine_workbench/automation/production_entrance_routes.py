"""Same-origin source-to-production handoff routes."""
from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .pipeline_run import PipelineRunError


def manager_for(server):
    from .production_routes import manager_for as production_for
    from .psd_import_jobs import PsdImportJobs
    from .production_entrance import ProductionEntrances
    owner = server.automation_manager
    with owner._lock:
        if owner._closed:
            raise PipelineRunError('pipeline_manager_closed')
        if owner._imports is None:
            owner._imports = PsdImportJobs(owner.application.projects)
        if owner._production_entrances is None:
            owner._production_entrances = ProductionEntrances(production_for(server),owner._imports)
        return owner._production_entrances


def dispatch_entrances(parts, handler, method):
    if parts[:2] != ['api','production-entrances']:
        return False
    from .web_routes import _error, _require_mutation
    tail = parts[2:]
    allowed = ('GET, HEAD, POST, OPTIONS' if not tail else 'GET, HEAD, OPTIONS' if len(tail)==1
               else 'POST, OPTIONS' if len(tail)==2 and tail[1] in ('resume','cancel') else None)
    if allowed is None:
        _error(handler,404,'production_entrance_route_not_found');return True
    if method=='OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method=='OPTIONS' else 405,b'','application/json',
            visual_review=True,extra_headers={'Allow':allowed});return True
    try:
        if method=='POST':
            _require_mutation(handler.headers)
        manager=manager_for(handler.server)
        if method=='POST':
            body=read_json_object_request(handler,maximum_bytes=128000)
            if not tail:
                value=manager.submit(body)
            else:
                if set(body)!={'expected_revision'}:
                    raise PipelineRunError('production_entrance_request_invalid')
                value=getattr(manager,tail[1])(tail[0],body['expected_revision'])
            handler._send_visual_json(202,value)
        else:
            value=manager.options() if tail==['options'] else manager.get(tail[0]) if tail else dict(entrances=manager.list())
            handler._send_visual_json(200,value)
    except HttpJsonRequestError as exc:
        _error(handler,exc.status,exc.code)
    except (OSError,RuntimeError,ValueError,KeyError,TypeError) as exc:
        reason=getattr(exc,'reason_code','production_entrance_failed')
        _error(handler,403 if reason in ('forbidden_origin','forbidden_intent') else 409,reason)
    return True
