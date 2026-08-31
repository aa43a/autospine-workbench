"""Public errors for the independent P10.3c v2 review authority."""


class BodySwayVisualReviewHistoryV2Error(RuntimeError):
    pass


class BodySwayVisualReviewRevisionV2Conflict(
    BodySwayVisualReviewHistoryV2Error,
):
    def __init__(
        self, message: str, *, requested_revision: int | None,
        current_revision: int, requested_head: str | None,
        current_head: str | None,
    ) -> None:
        super().__init__(message)
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        self.requested_head = requested_head
        self.current_head = current_head


class BodySwayVisualReviewStoreV2Error(RuntimeError):
    pass
