"""Same-origin unified character jobs; no client paths or command fragments."""
from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .pipeline_run import PipelineRunError


def manager_for(server):
    from .sleeve_routes import manager_for as sleeve_manager
    from .character_jobs import CharacterJobs
    owner=server.automation_manager
    sleeves=sleeve_manager(server)
    with owner._lock:
        if owner._closed: raise PipelineRunError('pipeline_manager_closed')
        if owner._characters is None:
            owner._characters=CharacterJobs(owner.application.projects,sleeves)
        return owner._characters


def dispatch_character(tail,handler,method,project):
    from .web_routes import _error, _require_mutation
    allowed = 'GET, HEAD, POST, OPTIONS' if not tail else None
    if tail == ['regions']: allowed='GET, HEAD, POST, OPTIONS'
    if tail in (['final-regions'], ['post-component-regions'], ['component-mounts']): allowed='GET, HEAD, POST, OPTIONS'
    if tail == ['component-mount-plan']: allowed='POST, OPTIONS'
    if tail == ['order-review']: allowed='GET, HEAD, POST, OPTIONS'
    if len(tail)==2 and tail[0]=='jobs': allowed='GET, HEAD, OPTIONS'
    if len(tail)==3 and tail[0]=='jobs' and tail[2]=='download': allowed='GET, HEAD, OPTIONS'
    if len(tail)==3 and tail[0]=='jobs' and tail[2]=='cancel': allowed='POST, OPTIONS'
    if len(tail)==3 and tail[0]=='jobs' and tail[2] in {'visual-review','weighted-review','auto-binding-audit'}: allowed='GET, HEAD, POST, OPTIONS'
    if len(tail)>=4 and tail[0]=='jobs' and tail[2]=='view': allowed='GET, HEAD, OPTIONS'
    if allowed is None:
        _error(handler,404,'pipeline_route_not_found'); return True
    if method=='OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method=='OPTIONS' else 405,b'','application/json',
                            extra_headers={'Allow':allowed},visual_review=True); return True
    try:
        manager=manager_for(handler.server)
        if method=='POST':
            _require_mutation(handler.headers)
            body=read_json_object_request(handler,maximum_bytes=16384)
            if tail == ['order-review']:
                from .character_order_review import save
                value=save(manager,project,body)
            elif tail == ['component-mount-plan']:
                from .character_component_plan import prepare
                value=prepare(manager,project,body)
            elif tail == ['component-mounts']:
                from .character_component_mounts import save
                value=save(manager,project,body)
            elif tail in (['final-regions'],['post-component-regions']):
                from .character_final_regions import save
                value=save(manager,project,body,stage="after_components" if tail==["post-component-regions"] else "before_components")
            elif tail == ['regions']:
                from .character_region_decisions import save
                value=save(manager,project,body)
            elif not tail:
                if set(body)-{'motion_choice_id','residual_texture_profile','skirt_profile','shoulder_regions','residual_auto_profile'}!={'expected_resolved_sha256','expected_input_sha256','sleeve_job_id'}:
                    raise PipelineRunError('pipeline_request_invalid')
                value=manager.submit(project,**body)
            elif tail[2]=='auto-binding-audit':
                from .character_auto_audit import save
                value=save(manager,project,tail[1],body)
            elif tail[2]=='weighted-review':
                from .character_weighted_review import save
                value=save(manager,project,tail[1],body)
            elif tail[2]=='visual-review':
                from .character_visual_review import save
                value=save(manager,project,tail[1],body)
            else:
                if body: raise PipelineRunError('pipeline_request_invalid')
                value=manager.cancel(project,tail[1])
            handler._send_visual_json(202,value)
        elif tail == ['order-review']:
            from .character_order_review import overview
            handler._send_visual_json(200,overview(manager,project))
        elif tail == ['component-mounts']:
            from .character_component_mounts import overview
            handler._send_visual_json(200,overview(manager,project))
        elif tail in (['final-regions'],['post-component-regions']):
            from .character_final_regions import overview
            handler._send_visual_json(200,overview(manager,project,stage="after_components" if tail==["post-component-regions"] else "before_components"))
        elif tail == ['regions']:
            from .character_region_decisions import overview
            handler._send_visual_json(200,overview(manager,project))
        elif not tail: handler._send_visual_json(200,manager.overview(project))
        elif len(tail)==2: handler._send_visual_json(200,manager.get(project,tail[1]))
        elif tail[2]=='auto-binding-audit':
            from .character_auto_audit import overview
            handler._send_visual_json(200,overview(manager,project,tail[1]))
        elif tail[2]=='visual-review':
            from .character_visual_review import overview
            handler._send_visual_json(200,overview(manager,project,tail[1]))
        elif tail[2]=='weighted-review':
            from .character_weighted_review import overview
            handler._send_visual_json(200,overview(manager,project,tail[1]))
        elif tail[2]=='view':
            raw,mime=manager.review_file(project,tail[1],tail[3:])
            handler._send_bytes(200,raw,mime,visual_review=True)
        else:
            handler._send_bytes(200,manager.download(project,tail[1]),'application/zip',visual_review=True,
                               extra_headers={'Content-Disposition':'attachment; filename="character-spine-candidate.zip"'})
    except HttpJsonRequestError as exc: _error(handler,exc.status,exc.code)
    except (OSError,RuntimeError,ValueError,TypeError,KeyError) as exc:
        reason=getattr(exc,'reason_code','character_request_failed')
        status=403 if reason in {'forbidden_origin','forbidden_intent'} else 409 if reason in {
            'project_snapshot_stale','pipeline_preview_not_ready','character_source_changed','character_review_conflict'} else 404 if reason in {
            'pipeline_job_not_found','project_not_found'} else 400
        _error(handler,status,reason)
    return True
