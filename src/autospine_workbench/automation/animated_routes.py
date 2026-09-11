"""Same-origin routes for project-level candidate animation previews."""

from .animated_jobs import AnimatedWebJobs, safe_file
from .pipeline_run import PipelineRunError
from ..http_json_request import HttpJsonRequestError, read_json_object_request


def manager_for(server):
    owner = server.automation_manager
    with owner._lock:
        if owner._closed:
            raise PipelineRunError("pipeline_manager_closed")
        if owner._animated is None:
            owner._animated = AnimatedWebJobs(owner.application.projects)
        return owner._animated


def dispatch_animated(tail, handler, method, project_id):
    if tail[:1] == ['preparation']:
        from .input_preparation_routes import dispatch_preparation
        return dispatch_preparation(tail[1:], handler, method, project_id)
    from .web_routes import _error, _require_mutation
    allowed = None
    if tail in (["joints"], ["rig-plan"]):
        allowed = "GET, HEAD, POST, OPTIONS"
    elif not tail or (len(tail) == 2 and tail[0] == "jobs"):
        allowed = "GET, HEAD, OPTIONS"
    elif tail in (["preview"], ["review"], ["rebase"], ["complete-bindings"]) or (len(tail) == 3 and tail[0] == "jobs" and tail[2] == "cancel"):
        allowed = "POST, OPTIONS"
    elif len(tail) == 3 and tail[0] == "jobs" and tail[2] in {"download", "coverage"} \
            or len(tail) >= 4 and tail[0] == "jobs" and tail[2] == "files":
        allowed = "GET, HEAD, OPTIONS"
    if allowed is None:
        _error(handler, 404, "pipeline_route_not_found")
        return True
    if method == "OPTIONS" or method not in allowed.split(", "):
        handler._send_bytes(204 if method == "OPTIONS" else 405, b"", "application/json",
                            extra_headers={"Allow": allowed}, visual_review=True)
        return True
    try:
        if method == "POST":
            _require_mutation(handler.headers)
            body = read_json_object_request(handler, maximum_bytes=256 * 1024 if tail in (["review"], ["joints"]) else 2048)
            if tail == ["preview"]:
                if set(body) != {"expected_resolved_sha256", "clip", "resume"}:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager_for(handler.server).submit(project_id, **body)
            elif tail == ["rig-plan"]:
                if set(body) != {"expected_resolved_sha256", "expected_input_sha256"}:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager_for(handler.server).application.prepare_rig_plan(project_id, **body)
            elif tail == ["complete-bindings"]:
                if set(body) != {"expected_resolved_sha256", "expected_input_sha256"}:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager_for(handler.server).application.complete_bindings(project_id, **body)
            elif tail == ["rebase"]:
                if set(body) != {"expected_resolved_sha256", "expected_registration_sha256"}:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager_for(handler.server).application.rebase(project_id, **body)
            elif tail == ["joints"]:
                if set(body) != {"expected_resolved_sha256", "expected_input_sha256", "records", "reviewed_joint_ids"}:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager_for(handler.server).application.review_joints(project_id, **body)
            elif tail == ["review"]:
                if set(body) != {"expected_resolved_sha256", "expected_input_sha256", "records"} \
                        or type(body["records"]) is not list or len(body["records"]) > 256:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager_for(handler.server).application.review(project_id, **body)
            else:
                if body:
                    raise PipelineRunError("pipeline_request_invalid")
                result = manager_for(handler.server).cancel(project_id, tail[1])
            handler._send_visual_json(202, result)
        else:
            manager = manager_for(handler.server)
            if tail == ["rig-plan"]:
                handler._send_visual_json(200, manager.application.rig_plan(project_id))
            elif tail == ["joints"]:
                handler._send_visual_json(200, manager.application.joints(project_id))
            elif not tail:
                handler._send_visual_json(200, manager.application.overview(project_id))
            elif len(tail) == 2:
                handler._send_visual_json(200, manager.get(project_id, tail[1]))
            elif tail[2] == "coverage":
                from .character_coverage_reader import read_job_coverage
                handler._send_visual_json(200, read_job_coverage(manager, project_id, tail[1]))
            elif tail[2] == "download":
                raw = manager.download(project_id, tail[1])
                handler._send_bytes(200, raw, "application/zip", visual_review=True,
                                    extra_headers={"Content-Disposition": 'attachment; filename="spine-animated-preview.zip"'})
            else:
                name = safe_file("/".join(tail[3:]))
                raw = manager.file(project_id, tail[1], name)
                mime = "image/png" if name.endswith(".png") else "application/json" \
                    if name.endswith(".json") else "text/plain; charset=utf-8"
                handler._send_bytes(200, raw, mime, visual_review=True)
    except HttpJsonRequestError as exc:
        _error(handler, exc.status, exc.code)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        reason = getattr(exc, "reason_code", "pipeline_request_failed")
        status = 403 if reason in {"forbidden_origin", "forbidden_intent"} else 400
        if reason in {"pipeline_run_not_found", "pipeline_job_not_found", "project_not_found", "animated_file_not_found"}:
            status = 404
        if reason in {"pipeline_queue_full", "project_changed_during_snapshot", "project_snapshot_stale",
                      "pipeline_preview_not_ready"}:
            status = 409
        _error(handler, status, reason)
    return True
