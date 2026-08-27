"""Public error hierarchy for authoritative P10.5b seam review."""

from __future__ import annotations


class SeamAnchorReviewStoreError(RuntimeError):
    """Raised when authoritative seam-review state cannot be used safely."""


class SeamAnchorReviewHistoryError(SeamAnchorReviewStoreError):
    """Raised when the linear seam-review history is unsafe or stale."""


class SeamAnchorReviewRevisionConflict(SeamAnchorReviewHistoryError):
    """Expose bounded compare-and-swap conflict details to public adapters."""

    def __init__(
        self, message: str, *, requested_revision: int, current_revision: int,
        requested_head: str | None, current_head: str | None,
    ) -> None:
        super().__init__(message)
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        self.requested_head = requested_head
        self.current_head = current_head
