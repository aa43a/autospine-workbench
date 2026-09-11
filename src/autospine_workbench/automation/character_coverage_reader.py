"""Read existing exact preview inputs and publish a separate coverage artifact."""

import json

from .animated_input_index import inspect_registration, assert_registered_current
from .character_coverage import build_coverage, validate_coverage
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes


def read_job_coverage(manager, project_id, job_id):
    files = manager.files(project_id, job_id)
    run = manager.get(project_id, job_id)["run"]
    app = manager.application
    scope = json.loads(files["preview-manifest.json"])
    info = inspect_registration(app.projects, project_id)
    if info["source_addresses"] != scope["source_addresses"]:
        raise PipelineRunError("animated_input_changed")
    mesh_sha = run["steps"][1]["outputs"]["mesh_bundle_sha256"]
    if app.store.checkpoint(run["run_id"], "mesh") != mesh_sha:
        raise PipelineRunError("pipeline_artifact_invalid")
    mesh = json.loads(app.store.read(mesh_sha)["mesh.json"])
    if mesh.get("stage_identity") != app._stage_identity(run):
        raise PipelineRunError("animated_stage_identity_mismatch")
    replacements = {p["source_layer_id"]: p["layers"] for p in mesh.get("partitions", [])}
    expanded = [layer for original in info["candidate"]["layers"]
                for layer in replacements.get(original["layer_id"], [original])]
    ledger = build_coverage(info["candidate"], info["draft"], info["bindings"], expanded,
                            scope, run["steps"][2]["outputs"]["bundle_sha256"])
    digest = validate_coverage(ledger)
    artifact = app.store.publish({"character-coverage.json": canonical_bytes(ledger)})
    verified = json.loads(app.store.read_file(artifact, "character-coverage.json"))
    if validate_coverage(verified) != digest:
        raise PipelineRunError("pipeline_artifact_invalid")
    assert_registered_current(app.projects, project_id, scope["source_addresses"])
    return {"document": verified, "sha256": digest, "artifact_sha256": artifact}
