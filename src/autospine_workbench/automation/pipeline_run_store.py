"""Append-only PipelineRun snapshots; identity is independent of old artifacts."""

from pathlib import Path

from .pipeline_run import PipelineRunError, create_run, transition, validate_transition
from .pipeline_run_validation import require_run_id, validate_run
from .storage_io import directory, publish_document, read_document
from .target_version import LEGACY_TARGET_VERSION


class PipelineConflict(PipelineRunError):
    def __init__(self):
        super().__init__("pipeline_revision_conflict")


class PipelineRunStore:
    def __init__(self, state_root):
        self.root = Path(state_root) / "jobs" / "pipeline-runs-v1"

    def _path(self, run_id, *, create=False):
        require_run_id(run_id)
        return directory(self.root / run_id, create=create)

    def create(self, project_id, profile, source_addresses, *, target_version=LEGACY_TARGET_VERSION):
        run = create_run(project_id, profile, source_addresses, target_version=target_version)
        path = self._path(run["run_id"], create=True)
        events = directory(path / "events", create=True)
        publish_document(events / "000000.json", run, staging=path / "staging")
        loaded = self.load(run["run_id"])
        if loaded["source_addresses"] != source_addresses or loaded["project_id"] != project_id \
                or loaded["profile"] != profile or loaded["engine"] != run["engine"]:
            raise PipelineRunError("pipeline_history_invalid")
        return loaded

    def load(self, run_id):
        events = directory(self._path(run_id) / "events")
        paths = []
        for path in events.iterdir():
            paths.append(path)
            if len(paths) > 1025:
                raise PipelineRunError("pipeline_history_limit")
        paths.sort(key=lambda path: path.name)
        if not paths:
            raise PipelineRunError("pipeline_history_invalid")
        previous = None
        for revision, path in enumerate(paths):
            if path.name != f"{revision:06d}.json":
                raise PipelineRunError("pipeline_history_invalid")
            current = read_document(path)
            validate_run(current)
            if current["run_id"] != run_id or current["revision"] != revision:
                raise PipelineRunError("pipeline_history_invalid")
            if previous is not None:
                validate_transition(previous, current)
            previous = current
        return previous

    def append(self, run_id, expected_sha256, action, **kwargs):
        before = self.load(run_id)
        if before["state_sha256"] != expected_sha256:
            raise PipelineConflict()
        after = transition(before, action, **kwargs)
        path = self._path(run_id)
        destination = path / "events" / f"{after['revision']:06d}.json"
        if not publish_document(destination, after, staging=path / "staging"):
            raise PipelineConflict()
        # Verify the committed snapshot even if a concurrent cancel has advanced it.
        if read_document(destination) != after:
            raise PipelineRunError("pipeline_storage_invalid")
        return after
