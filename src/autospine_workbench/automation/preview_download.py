"""Deterministic user-selected ZIP export of a verified setup preview."""

from io import BytesIO
import os
from pathlib import Path
import tempfile
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from ..safe_input_files import read_real_file
from ..spine42_v3_bundle_files import existing_exact_child
from .pipeline_run import PipelineRunError
from .pipeline_run_validation import validate_run
from .region_preview import verify_region_preview
from .storage_io import directory


def export_preview(state_root, run, destination):
    """Never replace an existing different file or trust a journal as evidence."""
    validate_run(run)
    if run["status"] != "succeeded":
        raise PipelineRunError("pipeline_preview_not_ready")
    outputs = run["steps"][2]["outputs"]
    sources = {"layer_manifest_sha256": run["source_addresses"]["layer_manifest_sha256"],
               **run["steps"][1]["outputs"]}
    try:
        bundle = verify_region_preview(state_root, run["project_id"], outputs["bundle_sha256"],
                                       expected_source_addresses=sources)
        if any(bundle.addresses[key] != value for key, value in outputs.items()):
            raise PipelineRunError("pipeline_artifact_invalid")
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise PipelineRunError("pipeline_artifact_invalid") from exc
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
        for name, content in sorted(bundle.files.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    data = buffer.getvalue()
    destination = Path(os.path.abspath(os.fspath(destination)))
    if destination.suffix.lower() != ".zip":
        raise PipelineRunError("pipeline_output_requires_zip")
    directory(destination.parent, create=True)
    try:
        existing = existing_exact_child(destination.parent, destination.name)
        if existing is not None:
            _same_file(existing, data)
            return
        descriptor, name = tempfile.mkstemp(prefix=".autospine-export-", dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                _same_file(destination, data)
        finally:
            temporary.unlink(missing_ok=True)
    except PipelineRunError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise PipelineRunError("pipeline_output_invalid") from exc


def _same_file(path, data):
    if read_real_file(path, len(data) + 1, "preview export") != data:
        raise PipelineRunError("pipeline_output_exists")
