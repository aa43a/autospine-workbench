"""Public error hierarchy for authoritative body-sway visual review."""

from __future__ import annotations


class BodySwayVisualReviewStoreError(RuntimeError):
    """Raised when authoritative visual-review state cannot be used safely."""


class BodySwayVisualReviewHistoryError(BodySwayVisualReviewStoreError):
    """Raised when the linear human-decision history is unsafe or stale."""


class BodySwayVisualReviewRevisionConflict(BodySwayVisualReviewHistoryError):
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
