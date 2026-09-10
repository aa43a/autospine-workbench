"""PSD binary intake routes with same-origin intent and bounded request bodies."""
from urllib.parse import unquote
from .pipeline_run import PipelineRunError
from .psd_import_jobs import PsdImportJobs


def dispatch_imports(parts, handler, method):
    from .web_routes import _error, _require_mutation
    if parts[:2] != ['api', 'asset-imports']:
        return False
    allowed = 'POST, OPTIONS' if len(parts) == 2 else 'GET, HEAD, OPTIONS' if len(parts) == 3 else None
    if allowed is None:
        _error(handler, 404, 'psd_route_not_found')
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
            if owner._imports is None:
                owner._imports = PsdImportJobs(owner.application.projects)
            manager = owner._imports
        if method == 'POST':
            _require_mutation(handler.headers)
            lengths = handler.headers.get_all('Content-Length', [])
            names = handler.headers.get_all('X-Autospine-File-Name', [])
            if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
                or len(names) != 1 or handler.headers.get_all('Transfer-Encoding', [])
                or handler.headers.get_all('Content-Type', []) != ['application/octet-stream']):
                raise PipelineRunError('psd_upload_headers_invalid')
            handler.connection.settimeout(30)
            result = manager.upload(handler.rfile, int(lengths[0]), unquote(names[0], errors='strict'))
            handler._send_visual_json(202, result)
        else:
            handler._send_visual_json(200, manager.get(parts[2]))
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        handler.close_connection = True
        reason = getattr(exc, 'reason_code', 'psd_import_failed')
        _error(handler, 403 if reason in ('forbidden_origin', 'forbidden_intent') else 400, reason)
    return True
