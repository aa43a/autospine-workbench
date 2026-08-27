"""Public project-store error types kept separate from the discovery facade."""

from __future__ import annotations

from typing import Any


class ProjectStoreError(RuntimeError):
    """Base error for project discovery and persistence."""


class ProjectNotFoundError(ProjectStoreError):
    def __init__(self, project_id: str):
        self.project_id = project_id
        super().__init__(f"Unknown project: {project_id}")


class AssetNotFoundError(ProjectStoreError):
    def __init__(self, project_id: str, asset: str):
        self.project_id = project_id
        self.asset = asset
        super().__init__(f"Asset not found for {project_id}: {asset}")


class RevisionConflictError(ProjectStoreError):
    def __init__(self, requested_revision: int, current_revision: int):
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        super().__init__(
            f"Revision conflict: requested {requested_revision}, current {current_revision}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "revision_conflict",
            "message": str(self),
            "requested_revision": self.requested_revision,
            "current_revision": self.current_revision,
        }


class ProjectStateError(ProjectStoreError):
    """Raised when persisted authoring state is unreadable or invalid."""


__all__ = [
    "AssetNotFoundError",
    "ProjectNotFoundError",
    "ProjectStateError",
    "ProjectStoreError",
    "RevisionConflictError",
]
