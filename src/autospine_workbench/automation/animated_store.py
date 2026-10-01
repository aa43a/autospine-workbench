"""Immutable, bounded stage files for animated preview recovery and downloads."""

import hashlib
import os
from pathlib import Path
import tempfile

from ..manifest_artifacts import require_sha256
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from .animated_jobs import safe_file
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

MAX_FILE = 64 << 20
MAX_TOTAL = 256 << 20


def _publish_bytes(path, raw):
    directory(path.parent, create=True)
    if path.exists():
        if read_real_file(path, MAX_FILE, "animated stage") != raw:
            raise PipelineRunError("pipeline_artifact_invalid")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".animated-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if read_real_file(path, MAX_FILE, "animated stage") != raw:
                raise PipelineRunError("pipeline_artifact_invalid")
    finally:
        Path(temporary).unlink(missing_ok=True)


class AnimatedStore:
    def __init__(self, state_root):
        self.root = Path(state_root) / "builds" / "animated-preview-v1"
        self.runs = Path(state_root) / "jobs" / "animated-pipeline-v1"

    def run_path(self, run_id):
        if not isinstance(run_id, str) or not run_id.startswith("run-"):
            raise PipelineRunError("pipeline_run_id_invalid")
        require_sha256(run_id[4:], "Animated run")
        return directory(self.runs / run_id, create=True)

    def publish(self, files):
        if not files or len(files) > 1024 or sum(len(raw) for raw in files.values()) > MAX_TOTAL:
            raise PipelineRunError("animated_resource_limit")
        inventory = {}
        for name, raw in files.items():
            safe_file(name)
            if type(raw) is not bytes or len(raw) > MAX_FILE:
                raise PipelineRunError("animated_resource_limit")
            inventory[name] = hashlib.sha256(raw).hexdigest()
        digest = canonical_sha256(inventory)
        folder = directory(self.root / digest, create=True)
        for name, raw in files.items():
            _publish_bytes(folder / name, raw)
        publish_document(folder / "inventory.json", inventory, staging=folder / "staging")
        if self.read(digest) != files:
            raise PipelineRunError("pipeline_artifact_invalid")
        return digest

    def read(self, digest):
        require_sha256(digest, "Animated bundle")
        folder = directory(self.root / digest)
        from ._animated_read_cohort import read_verified
        return read_verified(folder, digest, max_file=MAX_FILE, max_total=MAX_TOTAL)

    def read_file(self, digest, name):
        """Verify the addressed inventory and requested file, without N full ZIP reads."""
        require_sha256(digest, "Animated bundle")
        safe_file(name)
        folder = directory(self.root / digest)
        inventory = read_document(folder / "inventory.json")
        if canonical_sha256(inventory) != digest or not 0 < len(inventory) <= 1024:
            raise PipelineRunError("pipeline_artifact_invalid")
        for key, value in inventory.items():
            safe_file(key)
            require_sha256(value, "Animated file")
        if name not in inventory:
            raise PipelineRunError("animated_file_not_found")
        directory((folder / name).parent)
        raw = read_real_file(folder / name, MAX_FILE, "animated file")
        if hashlib.sha256(raw).hexdigest() != inventory[name]:
            raise PipelineRunError("pipeline_artifact_invalid")
        return raw

    def checkpoint(self, run_id, stage, digest=None):
        if stage not in {"mesh", "preview"}:
            raise PipelineRunError("animated_stage_invalid")
        folder = self.run_path(run_id)
        path = folder / (stage + ".json")
        if digest is not None:
            value = {"stage": stage, "bundle_sha256": digest}
            publish_document(path, value, staging=folder / "staging")
            if read_document(path) != value:
                raise PipelineRunError("pipeline_artifact_invalid")
        if not path.exists():
            return None
        value = read_document(path)
        if set(value) != {"stage", "bundle_sha256"} or value["stage"] != stage:
            raise PipelineRunError("pipeline_artifact_invalid")
        self.read(value["bundle_sha256"])
        return value["bundle_sha256"]
