"""Same-origin project automation routes, independent of certification APIs."""

from zipfile import BadZipFile

from ..http_json_request import HttpJsonRequestError, read_json_object_request
from .capability_resolver import resolve_capabilities
from .pipeline_run import PipelineRunError
from .project_snapshot import observe_project
from .review_queue import build_review_queue
from .web_download import download_job


def dispatch_automation(parts, handler, method):
    if len(parts) < 4 or parts[:2] != ["api", "projects"] or parts[3] != "automation":
        return False
    tail = parts[4:]
    allowed = None
    if not tail or (len(tail) == 2 and tail[0] == "jobs"):
        allowed = "GET, HEAD, OPTIONS"
    elif tail == ["preview"] or (len(tail) == 3 and tail[0] == "jobs" and tail[2] == "cancel"):
        allowed = "POST, OPTIONS"
    elif len(tail) == 3 and tail[0] == "jobs" and tail[2] == "download":
        allowed = "GET, HEAD, OPTIONS"
    if allowed is None:
        _error(handler, 404, "pipeline_route_not_found")
        return True
    if method == "OPTIONS" or method not in allowed.split(", "):
        handler._send_bytes(204 if method == "OPTIONS" else 405, b"", "application/json",
                            extra_headers={"Allow": allowed}, visual_review=True)
        return True
    try:
        manager = handler.server.automation_manager
        project_id = parts[2]
        if method == "POST":
            _require_mutation(handler.headers)
            body = read_json_object_request(handler, maximum_bytes=2048)
            if tail == ["preview"]:
                if set(body) != {"profile", "expected_resolved_sha256", "resume"}:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager.submit(project_id, **body)
            else:
                if body:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager.cancel(project_id, tail[1])
            handler._send_visual_json(202, result)
        elif not tail:
            with observe_project(manager.application.projects, project_id) as snapshot:
                result = {"capabilities": resolve_capabilities(snapshot),
                          "review_queue": build_review_queue(snapshot)}
            handler._send_visual_json(200, result)
        elif len(tail) == 2:
            handler._send_visual_json(200, manager.get(project_id, tail[1]))
        else:
            raw = download_job(manager, project_id, tail[1])
            handler._send_bytes(200, raw, "application/zip", visual_review=True,
                                extra_headers={"Content-Disposition": 'attachment; filename="spine-preview.zip"'})
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, BadZipFile) as exc:
        reason = getattr(exc, "reason_code", "pipeline_request_failed")
        status = 403 if reason in {"forbidden_origin", "forbidden_intent"} else 400
        if reason in {"pipeline_run_not_found", "pipeline_job_not_found", "project_not_found"}:
            status = 404
        if reason in {"pipeline_queue_full", "project_changed_during_snapshot", "pipeline_preview_not_ready"}:
            status = 409
        _error(handler, status, reason)
    return True


def _require_mutation(headers):
    host = headers.get_all("Host", [])
    origin = headers.get_all("Origin", [])
    if len(host) != 1 or origin != [f"http://{host[0]}"] \
            or headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
        raise PipelineRunError("forbidden_origin")
    if headers.get_all("X-Autospine-Intent", []) != ["pipeline-preview"]:
        raise PipelineRunError("forbidden_intent")


def _error(handler, status, reason):
    handler._send_visual_json(status, {"error": reason, "reason_code": reason,
                                      "message": reason, "authority": "none"})
