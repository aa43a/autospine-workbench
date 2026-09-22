"""Same-origin binary motion uploads and read-only source playback."""
from urllib.parse import unquote

from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .pipeline_run import PipelineRunError
from .motion_intake_jobs import MotionIntakeJobs


def _methods(tail):
    if len(tail) == 2 and tail[1] in ('stage-review', 'repair-draft'):
        return 'GET, HEAD, POST, OPTIONS'
    if tail == ['generate']:
        return 'POST, OPTIONS'
    if not tail:
        return 'GET, HEAD, POST, OPTIONS'
    if (len(tail) == 1 or len(tail) == 2 and tail[1] in ('preview', 'download', 'projection', 'projection.json', 'contacts', 'compare-views', 'compare-oblique', 'compare-targets')
            or len(tail) >= 3 and tail[1] == 'view'):
        return 'GET, HEAD, OPTIONS'
    if len(tail) == 2 and tail[1] in ('cancel', 'retry', 'adapt', 'reproject'):
        return 'POST, OPTIONS'
    return None


def _upload(manager, handler):
    lengths = handler.headers.get_all('Content-Length', [])
    names = handler.headers.get_all('X-Autospine-File-Name', [])
    views = handler.headers.get_all('X-Autospine-Motion-View', [])
    if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
            or len(names) != 1 or len(views) != 1
            or handler.headers.get_all('Transfer-Encoding', [])
            or handler.headers.get_all('Content-Type', []) != ['application/octet-stream']):
        raise PipelineRunError('motion_upload_headers_invalid')
    profiles = handler.headers.get_all('X-Autospine-Npz-Profile', [])
    rates = handler.headers.get_all('X-Autospine-Npz-Fps', [])
    settings = None
    if profiles or rates:
        if len(profiles) != 1 or len(rates) != 1:
            raise PipelineRunError('motion_upload_headers_invalid')
        settings = dict(profile=profiles[0], fps=rates[0])
    return manager.upload(handler.rfile, int(lengths[0]), unquote(names[0], errors='strict'), views[0], settings)


def dispatch_motions(parts, handler, method):
    from .web_routes import _error, _require_mutation
    if parts[:2] != ['api', 'motions']:
        return False
    tail = parts[2:]
    allowed = _methods(tail)
    if allowed is None:
        _error(handler, 404, 'motion_route_not_found')
        return True
    if method == 'OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method == 'OPTIONS' else 405, b'', 'application/json',
                            visual_review=True, extra_headers={'Allow': allowed})
        return True
    try:
        owner = handler.server.automation_manager
        with owner._lock:
            if owner._closed:
                raise PipelineRunError('pipeline_manager_closed')
            if owner._motions is None:
                owner._motions = MotionIntakeJobs(owner.application.projects)
                from .character_routes import manager_for
                server = handler.server
                owner._motions.character_manager = lambda: manager_for(server)
            manager = owner._motions
        if method == 'POST':
            _require_mutation(handler.headers)
            handler.connection.settimeout(30)
            if not tail:
                result = _upload(manager, handler)
            elif tail == ['generate']:
                from .motion_generation_jobs import submit
                result = submit(manager, read_json_object_request(handler, maximum_bytes=8192))
            elif tail[1] == 'adapt':
                from .motion_target_jobs import submit
                result = submit(manager, tail[0], read_json_object_request(handler, maximum_bytes=1024))
            elif tail[1] == 'stage-review':
                from .motion_stage_review import save
                result = save(manager, tail[0], read_json_object_request(handler, maximum_bytes=20000))
            elif tail[1] == 'repair-draft':
                from .motion_repair_draft import save
                result = save(manager, tail[0], read_json_object_request(handler, maximum_bytes=20000))
            elif tail[1] == 'reproject':
                from .motion_reproject import submit
                result = submit(manager, tail[0], read_json_object_request(handler, maximum_bytes=200))
            else:
                if read_json_object_request(handler, maximum_bytes=100):
                    raise PipelineRunError('motion_request_invalid')
                result = getattr(manager, tail[1])(tail[0])
            handler._send_visual_json(202, result)
        elif len(tail) == 2 and tail[1] == 'repair-draft':
            from .motion_repair_draft import inspect
            handler._send_visual_json(200, inspect(manager, tail[0]))
        elif len(tail) == 2 and tail[1] == 'stage-review':
            from .motion_stage_review import inspect
            handler._send_visual_json(200, inspect(manager, tail[0]))
        elif len(tail) == 2 and tail[1] == 'contacts':
            from .motion_contact_review import inspect
            handler._send_visual_json(200, inspect(manager, tail[0]))
        elif len(tail) == 2 and tail[1] == 'compare-views':
            from .motion_view_comparison import inspect
            handler._send_visual_json(200, inspect(manager, tail[0]))
        elif len(tail) == 2 and tail[1] == 'compare-oblique':
            from .motion_oblique_comparison import inspect
            handler._send_visual_json(200, inspect(manager, tail[0]))
        elif len(tail) == 2 and tail[1] == 'compare-targets':
            from .motion_target_comparison import inspect
            handler._send_visual_json(200, inspect(manager, tail[0]))
        elif len(tail) == 2 and tail[1] in ('projection', 'projection.json'):
            from .motion_projection_review import inspect, render
            report = inspect(manager, tail[0])
            if tail[1] == 'projection.json':
                handler._send_visual_json(200, report)
            else:
                handler._send_bytes(200, render(report), 'text/html; charset=utf-8', visual_review=True)
        elif len(tail) >= 3 and tail[1] == 'view':
            from .motion_target_jobs import review_file
            raw, mime = review_file(manager, tail[0], tail[2:])
            handler._send_bytes(200, raw, mime, visual_review=True)
        elif len(tail) == 2 and tail[1] == 'download':
            from .motion_target_jobs import download
            handler._send_bytes(200, download(manager, tail[0]), 'application/zip', visual_review=True,
                                extra_headers={'Content-Disposition': 'attachment; filename="motion-character-candidate.zip"'})
        elif len(tail) == 2:
            handler._send_bytes(200, manager.preview(tail[0]), 'application/json', visual_review=True)
        else:
            handler._send_visual_json(200, manager.get(tail[0]) if tail else manager.overview())
    except HttpJsonRequestError as exc:
        handler.close_connection = True
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        handler.close_connection = True
        reason = getattr(exc, 'reason_code', 'motion_request_failed')
        _error(handler, 403 if reason in ('forbidden_origin', 'forbidden_intent') else 400, reason)
    return True
