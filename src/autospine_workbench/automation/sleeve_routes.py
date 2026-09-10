"""Fixed project sleeve workflow endpoints; no client-supplied paths or commands."""
from .sleeve_web_jobs import SleeveWebJobs
from .pipeline_run import PipelineRunError
from ..http_json_request import HttpJsonRequestError,read_json_object_request


def manager_for(server):
    owner=server.automation_manager
    with owner._lock:
        if owner._closed:raise PipelineRunError('pipeline_manager_closed')
        if owner._sleeves is None:owner._sleeves=SleeveWebJobs(owner.application.projects)
        return owner._sleeves


def dispatch_sleeves(tail,handler,method,project):
    from .web_routes import _error,_require_mutation
    allowed='GET, HEAD, POST, OPTIONS' if not tail else None
    if len(tail)==2 and tail[0]=='jobs':allowed='GET, HEAD, OPTIONS'
    if len(tail)==4 and tail[0]=='jobs' and tail[2]=='download' and tail[3].isascii() and tail[3].isdigit():
        allowed='GET, HEAD, OPTIONS'
    if allowed is None:
        _error(handler,404,'pipeline_route_not_found');return True
    if method=='OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method=='OPTIONS' else 405,b'','application/json',visual_review=True,extra_headers={'Allow':allowed});return True
    try:
        if method=='POST':
            _require_mutation(handler.headers)
            body=read_json_object_request(handler,maximum_bytes=2048)
            if set(body)!={'expected_resolved_sha256'}:raise PipelineRunError('pipeline_request_invalid')
            handler._send_visual_json(202,manager_for(handler.server).submit(project,**body))
        else:
            manager=manager_for(handler.server)
            if not tail:handler._send_visual_json(200,manager.overview(project))
            elif len(tail)==2:handler._send_visual_json(200,manager.get(project,tail[1]))
            else:
                raw=manager.download(project,tail[1],int(tail[3]))
                handler._send_bytes(200,raw,'application/zip',visual_review=True,
                    extra_headers={'Content-Disposition':'attachment; filename="sleeve-candidate.zip"'})
    except HttpJsonRequestError as exc:_error(handler,exc.status,exc.code)
    except (OSError,RuntimeError,ValueError,TypeError,KeyError) as exc:
        reason=getattr(exc,'reason_code','sleeve_request_failed')
        status=403 if reason in ('forbidden_origin','forbidden_intent') else 409
        _error(handler,status,reason)
    return True
