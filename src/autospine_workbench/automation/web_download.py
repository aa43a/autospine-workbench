"""Bounded ZIP readback against the exact preview file inventory."""

import hashlib
from io import BytesIO
import json
from zipfile import ZipFile

from ..safe_input_files import read_real_file
from .pipeline_run import PipelineRunError
from .region_preview import verify_region_preview
from .region_preview_store import FILES, LIMITS, _digest


def download_job(manager, project_id, job_id):
    result = manager.get(project_id, job_id)
    if result["status"] != "succeeded" or "run" not in result:
        raise PipelineRunError("pipeline_preview_not_ready")
    raw = read_real_file(manager._path(job_id) / "preview.zip", 110 << 20, "preview ZIP")
    if hashlib.sha256(raw).hexdigest() != result.get("zip_sha256"):
        raise PipelineRunError("pipeline_artifact_invalid")
    run = result["run"]
    with ZipFile(BytesIO(raw)) as archive:
        if len(archive.infolist()) != len(FILES) or set(archive.namelist()) != FILES:
            raise PipelineRunError("pipeline_artifact_invalid")
        files = {}
        for item in archive.infolist():
            if item.file_size > LIMITS[item.filename] or item.compress_type != 0:
                raise PipelineRunError("pipeline_artifact_invalid")
            files[item.filename] = archive.read(item)
    if _digest(files) != run["steps"][2]["outputs"]["bundle_sha256"]:
        raise PipelineRunError("pipeline_artifact_invalid")
    source = json.loads(files["source.json"])
    expected = {"layer_manifest_sha256": run["source_addresses"]["layer_manifest_sha256"],
                **run["steps"][1]["outputs"]}
    if source.get("source_addresses") != expected or source.get("project_id") != project_id:
        raise PipelineRunError("pipeline_artifact_invalid")
    # Journal hashes identify requests; they cannot attest to compilation.
    try:
        verified = verify_region_preview(
            manager.application.state_root, project_id,
            run["steps"][2]["outputs"]["bundle_sha256"], expected_source_addresses=expected,
        )
        if verified.files != files:
            raise PipelineRunError("pipeline_artifact_invalid")
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise PipelineRunError("pipeline_artifact_invalid") from exc
    return raw
