"""Pure, pinned PipelineRun v1 state transitions; never release credentials."""

from copy import deepcopy

from ..resolved_project import canonical_sha256
from .pipeline_profile import build_pipeline_profile
from .target_version import LEGACY_TARGET_VERSION, engine_for_target

SCHEMA = "autospine.pipeline-run/v1"
OPERATION = "region-spine-preview"
ENGINE = "region-spine-preview-v1"
STEPS = ("resolve-project", "build-region-rig", "compile-spine-preview")
STATUSES = ("pending", "running", "needs_review", "succeeded", "blocked", "failed", "canceled")
SOURCES = ("resolved_project_sha256", "layer_manifest_sha256", "input_identity_sha256")
OUTPUTS = (
    SOURCES,
    ("rig_sha256", "rig_bundle_sha256"),
    ("bundle_sha256", "skeleton_json_sha256", "atlas_sha256", "png_sha256", "qa_sha256"),
)


class PipelineRunError(RuntimeError):
    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__(reason_code)


def request_identity(project_id, profile, source_addresses, *, target_version=LEGACY_TARGET_VERSION):
    return {
        "project_id": project_id, "profile": profile,
        "operation": OPERATION, "engine": engine_for_target(target_version),
        "source_addresses": deepcopy(source_addresses),
    }


def seal(document):
    result = deepcopy(document)
    result.pop("state_sha256", None)
    result["state_sha256"] = canonical_sha256(result)
    return result


def create_run(project_id, profile, source_addresses, *, target_version=LEGACY_TARGET_VERSION):
    from .pipeline_run_validation import validate_run

    build_pipeline_profile(profile)
    identity = request_identity(project_id, profile, source_addresses, target_version=target_version)
    document = seal({
        "schema": SCHEMA, **identity,
        "run_id": "run-" + canonical_sha256(identity),
        "revision": 0, "previous_sha256": None,
        "authority": "none", "status": "pending", "action": "create",
        "steps": [{"id": name, "status": "pending", "outputs": {},
                   "reason_code": None} for name in STEPS],
    })
    validate_run(document)
    return document


def transition(run, action, *, outputs=None, reason_code=None):
    from .pipeline_run_validation import validate_run

    validate_run(run)
    if type(action) is not str:
        raise PipelineRunError("pipeline_transition_invalid")
    if run["revision"] >= 1024 or run["status"] in {"succeeded", "canceled"}:
        raise PipelineRunError("pipeline_transition_invalid")
    result = deepcopy(run)
    index = next(i for i, row in enumerate(run["steps"]) if row["status"] != "succeeded")
    row = result["steps"][index]
    status = run["status"]
    if action == "start" and status == "pending":
        row["status"] = "running"
    elif action == "succeed" and status == "running":
        row.update(status="succeeded", outputs=deepcopy(outputs), reason_code=None)
    elif action in {"block", "review", "fail"} and status in {"pending", "running"}:
        row.update(status={"block": "blocked", "review": "needs_review", "fail": "failed"}[action],
                   outputs={}, reason_code=reason_code)
    elif action == "resume" and status in {"running", "blocked", "failed", "needs_review"}:
        row.update(status="pending", outputs={}, reason_code=None)
    elif action == "cancel":
        row.update(status="canceled", outputs={}, reason_code="pipeline_canceled")
    else:
        raise PipelineRunError("pipeline_transition_invalid")
    if action != "succeed" and outputs is not None:
        raise PipelineRunError("pipeline_transition_invalid")
    if action not in {"block", "review", "fail"} and reason_code is not None:
        raise PipelineRunError("pipeline_transition_invalid")
    result.update(
        revision=run["revision"] + 1, previous_sha256=run["state_sha256"], action=action,
        status=next((step["status"] for step in result["steps"]
                     if step["status"] != "succeeded"), "succeeded"),
    )
    result = seal(result)
    validate_run(result)
    return result


def validate_transition(previous, current):
    from .pipeline_run_validation import validate_run

    validate_run(previous)
    validate_run(current)
    index = next((i for i, row in enumerate(previous["steps"])
                  if row["status"] != "succeeded"), None)
    if index is None:
        raise PipelineRunError("pipeline_transition_invalid")
    step = current["steps"][index]
    expected = transition(
        previous, current["action"],
        outputs=step["outputs"] if current["action"] == "succeed" else None,
        reason_code=step["reason_code"] if current["action"] in {"block", "review", "fail"} else None,
    )
    if current != expected:
        raise PipelineRunError("pipeline_history_invalid")
