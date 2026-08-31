"""Definite commit semantics for the replaceable override latest index."""

from __future__ import annotations

from typing import Any, Mapping

from .override_files import OverrideFileError, OverrideFiles


class OverrideRevisionCommitted(RuntimeError):
    """Signal that history committed even though its latest index stayed stale."""

    def __init__(self, document: Mapping[str, Any], reason: str) -> None:
        self.document = dict(document)
        self.revision = int(document["revision"])
        self.reason = reason
        super().__init__(
            f"Override revision {self.revision} committed; latest index repair failed"
        )


def refresh_latest_after_commit(
    files: OverrideFiles,
    *,
    history_path,
    latest_path,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Refresh latest, repairing it once from the authoritative history file."""

    try:
        files.write_latest(latest_path, document)
        return dict(document)
    except OverrideFileError:
        pass

    try:
        published = files.read(history_path)
    except OverrideFileError as exc:
        raise OverrideRevisionCommitted(document, "history_read_failed") from exc
    if published != document:
        raise OverrideRevisionCommitted(document, "history_readback_mismatch")
    try:
        files.write_latest(latest_path, published)
    except OverrideFileError as exc:
        raise OverrideRevisionCommitted(document, "latest_repair_failed") from exc
    return dict(document)
