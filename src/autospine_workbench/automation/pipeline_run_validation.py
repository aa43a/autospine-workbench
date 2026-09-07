"""Closed semantic validator for PipelineRun v1 snapshots."""

import re

from ..manifest_artifacts import LayerManifestError, require_safe_token
from ..resolved_project import canonical_sha256
from .pipeline_profile import PROFILE_NAMES
from .pipeline_run import (
    OPERATION, OUTPUTS, SCHEMA, SOURCES, STATUSES, STEPS,
    PipelineRunError, request_identity,
)
from .target_version import target_from_run

SHA = re.compile(r"[0-9a-f]{64}\Z")
REASON = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
KEYS = {
    "schema", "project_id", "profile", "operation", "engine", "source_addresses",
    "run_id", "revision", "previous_sha256", "authority", "status", "action",
    "steps", "state_sha256",
}


def require_sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        raise PipelineRunError("pipeline_address_invalid")
    return value


def require_run_id(value):
    if type(value) is not str or not value.startswith("run-"):
        raise PipelineRunError("pipeline_run_id_invalid")
    require_sha(value[4:])
    return value


def address_map(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise PipelineRunError("pipeline_address_invalid")
    for item in value.values():
        require_sha(item)


def validate_run(value):
    try:
        _validate(value)
    except PipelineRunError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, LayerManifestError) as exc:
        raise PipelineRunError("pipeline_run_invalid") from exc
    return value


def _validate(value):
    if type(value) is not dict or set(value) != KEYS:
        raise PipelineRunError("pipeline_run_invalid")
    if value["schema"] != SCHEMA or value["authority"] != "none" \
            or value["operation"] != OPERATION:
        raise PipelineRunError("pipeline_run_invalid")
    require_safe_token(value["project_id"], "pipeline project")
    if value["profile"] not in PROFILE_NAMES:
        raise PipelineRunError("unsupported_pipeline_profile")
    address_map(value["source_addresses"], SOURCES)
    identity = request_identity(value["project_id"], value["profile"], value["source_addresses"],
                                target_version=target_from_run(value))
    if value["run_id"] != "run-" + canonical_sha256(identity):
        raise PipelineRunError("pipeline_run_id_invalid")
    revision = value["revision"]
    if type(revision) is not int or not 0 <= revision <= 1024:
        raise PipelineRunError("pipeline_run_invalid")
    if revision == 0:
        if value["previous_sha256"] is not None or value["action"] != "create":
            raise PipelineRunError("pipeline_history_invalid")
    else:
        require_sha(value["previous_sha256"])
        if value["action"] not in {"start", "succeed", "block", "review", "fail", "cancel", "resume"}:
            raise PipelineRunError("pipeline_transition_invalid")
    steps = value["steps"]
    if type(steps) is not list or len(steps) != len(STEPS):
        raise PipelineRunError("pipeline_steps_invalid")
    open_step = False
    for i, row in enumerate(steps):
        if type(row) is not dict or set(row) != {"id", "status", "outputs", "reason_code"} \
                or row["id"] != STEPS[i] or row["status"] not in STATUSES:
            raise PipelineRunError("pipeline_steps_invalid")
        status = row["status"]
        if open_step and status != "pending":
            raise PipelineRunError("pipeline_step_order_invalid")
        open_step = open_step or status != "succeeded"
        if status == "succeeded":
            address_map(row["outputs"], OUTPUTS[i])
            if i == 0 and row["outputs"] != value["source_addresses"]:
                raise PipelineRunError("pipeline_address_invalid")
        elif row["outputs"] != {}:
            raise PipelineRunError("pipeline_outputs_invalid")
        if status in {"blocked", "failed", "needs_review", "canceled"}:
            if type(row["reason_code"]) is not str or not REASON.fullmatch(row["reason_code"]):
                raise PipelineRunError("pipeline_reason_invalid")
        elif row["reason_code"] is not None:
            raise PipelineRunError("pipeline_reason_invalid")
    derived = next((row["status"] for row in steps if row["status"] != "succeeded"), "succeeded")
    if value["status"] != derived or (revision == 0 and any(row["status"] != "pending" for row in steps)):
        raise PipelineRunError("pipeline_status_invalid")
    body = {key: item for key, item in value.items() if key != "state_sha256"}
    if value["state_sha256"] != canonical_sha256(body):
        raise PipelineRunError("pipeline_state_hash_invalid")
