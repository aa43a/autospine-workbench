"""Validate public job receipts separately from authoritative pipeline artifacts."""

import re

from ..manifest_artifacts import require_safe_token
from .pipeline_run import PipelineRunError, STATUSES
from .pipeline_run_validation import require_sha, validate_run
from .pipeline_profile import build_pipeline_profile
from .target_version import require_target_version, target_from_run


def validate_request(request):
    required = {"project_id", "profile", "expected_resolved_sha256", "resume"}
    if not isinstance(request, dict) or not required <= request.keys() \
            or request.keys() - required - {"target_version"} or type(request["resume"]) is not bool:
        raise PipelineRunError("pipeline_storage_invalid")
    require_safe_token(request["project_id"], "project")
    build_pipeline_profile(request["profile"])
    require_sha(request["expected_resolved_sha256"])
    return require_target_version(request.get("target_version", "4.2"))


def validate_job(result, job_id, request):
    target = validate_request(request)
    required = {"schema", "job_id", "project_id", "status", "authority"}
    if "target_version" in request:
        required.add("target_version")
    allowed = required | {"run", "reason_code", "zip_sha256", "cancel_requested", "target_version"}
    if not isinstance(result, dict) or not required <= result.keys() or result.keys() - allowed:
        raise PipelineRunError("pipeline_storage_invalid")
    if require_target_version(result.get("target_version", "4.2")) != target:
        raise PipelineRunError("pipeline_storage_invalid")
    if result["schema"] != "autospine.pipeline-web-job/v1" or result["job_id"] != job_id \
            or result["project_id"] != request["project_id"] or result["authority"] != "none" \
            or result["status"] not in STATUSES:
        raise PipelineRunError("pipeline_storage_invalid")
    require_safe_token(result["project_id"], "project")
    if "cancel_requested" in result and type(result["cancel_requested"]) is not bool:
        raise PipelineRunError("pipeline_storage_invalid")
    if "reason_code" in result and (type(result["reason_code"]) is not str or not re.fullmatch(
        r"[a-z][a-z0-9_]{0,79}", result["reason_code"],
    )):
        raise PipelineRunError("pipeline_storage_invalid")
    if "run" in result:
        run = result["run"]
        validate_run(run)
        if run["project_id"] != request["project_id"] or run["profile"] != request["profile"] \
                or run["status"] != result["status"] or run["source_addresses"][
                    "resolved_project_sha256"
                ] != request["expected_resolved_sha256"] or target_from_run(run) != target:
            raise PipelineRunError("pipeline_storage_invalid")
    if result["status"] == "succeeded":
        if "run" not in result:
            raise PipelineRunError("pipeline_storage_invalid")
        require_sha(result.get("zip_sha256"))
    elif "zip_sha256" in result:
        raise PipelineRunError("pipeline_storage_invalid")
    return result
