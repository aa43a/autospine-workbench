"""Compile immutable path-free PNG rows from one verified v2 execution."""

from __future__ import annotations

import hashlib

from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecution,
)
from .body_sway_visual_review_application_models_v2 import (
    BodySwayVisualReviewImageV2,
)
from .body_sway_visual_review_candidate_v2 import (
    BodySwayVisualReviewCandidateV2,
)


class BodySwayVisualReviewImageSnapshotV2Error(ValueError):
    pass


def compile_body_sway_visual_review_image_snapshot_v2(
    execution: VerifiedBodySwayRuntimeExecution,
    candidate: BodySwayVisualReviewCandidateV2,
) -> tuple[BodySwayVisualReviewImageV2, ...]:
    """Expose bytes only after the full execution and candidate were verified."""

    if type(execution) is not VerifiedBodySwayRuntimeExecution \
            or type(candidate) is not BodySwayVisualReviewCandidateV2:
        raise BodySwayVisualReviewImageSnapshotV2Error(
            "Visual review image snapshot requires exact evidence"
        )
    try:
        captures = execution.execution.capture.capture_bytes
        rows = []
        for case in candidate.document["cases"]:
            image = case["image"]
            raw = captures.get(image["path"])
            actual = (
                hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None,
                len(raw) if type(raw) is bytes else None,
            )
            if actual != (image["png_sha256"], image["size_bytes"]) \
                    or (image["width"], image["height"]) != (640, 640):
                raise BodySwayVisualReviewImageSnapshotV2Error(
                    "Visual review image bytes differ from evidence"
                )
            rows.append(BodySwayVisualReviewImageV2(
                candidate.sha256, case["case_id"], case["evidence_sha256"],
                image["png_sha256"], image["size_bytes"],
                image["width"], image["height"], raw,
            ))
        return tuple(rows)
    except BodySwayVisualReviewImageSnapshotV2Error:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise BodySwayVisualReviewImageSnapshotV2Error(
            "Visual review image snapshot is invalid"
        ) from exc


__all__ = [
    "BodySwayVisualReviewImageSnapshotV2Error",
    "compile_body_sway_visual_review_image_snapshot_v2",
]
