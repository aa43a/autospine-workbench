"""Authoritative execution and candidate replay for P10.3c v2."""

from __future__ import annotations

from pathlib import Path

from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecution,
    VerifiedBodySwayRuntimeExecutionReader,
)
from .body_sway_visual_review_candidate_v2 import (
    BodySwayVisualReviewCandidateV2,
)
from .body_sway_visual_review_candidate_validation_v2 import (
    require_body_sway_visual_review_candidate_v2,
)
from .body_sway_visual_review_profile_v2 import CANDIDATE_NAMESPACE
from .body_sway_visual_review_store_files import exact_payload, read_document
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


class BodySwayVisualReviewBindingV2Error(RuntimeError):
    """Raised when supplied values differ from exact authoritative replay."""


def reload_authoritative_runtime_execution_v2(
    state_root: Path, supplied: VerifiedBodySwayRuntimeExecution,
) -> VerifiedBodySwayRuntimeExecution:
    try:
        if type(supplied) is not VerifiedBodySwayRuntimeExecution:
            raise BodySwayVisualReviewBindingV2Error(
                "Visual review v2 execution representation is invalid"
            )
        source = supplied.execution.document["source"]
        loaded = VerifiedBodySwayRuntimeExecutionReader(state_root).load(
            supplied.project_id, source["temporary_preview_v2_sha256"],
            supplied.bundle_sha256, supplied.artifact_set_sha256,
        )
        if loaded.execution.canonical_bytes \
                != supplied.execution.canonical_bytes \
                or loaded.execution.capture.canonical_bytes \
                != supplied.execution.capture.canonical_bytes \
                or loaded.execution.capture.capture_bytes \
                != supplied.execution.capture.capture_bytes:
            raise BodySwayVisualReviewBindingV2Error(
                "Supplied execution differs from authoritative replay"
            )
        return loaded
    except BodySwayVisualReviewBindingV2Error:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError,
            TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayVisualReviewBindingV2Error(
            f"Authoritative runtime execution v2 replay failed: {exc}"
        ) from exc


def reload_authoritative_visual_review_candidate_v2(
    state_root: Path, supplied: BodySwayVisualReviewCandidateV2,
    execution: VerifiedBodySwayRuntimeExecution,
    preview: TemporaryBodySwayPreviewV2,
) -> tuple[BodySwayVisualReviewCandidateV2, VerifiedBodySwayRuntimeExecution]:
    try:
        if type(supplied) is not BodySwayVisualReviewCandidateV2:
            raise BodySwayVisualReviewBindingV2Error(
                "Visual review candidate v2 representation is invalid"
            )
        loaded = reload_authoritative_runtime_execution_v2(
            state_root, execution,
        )
        document = supplied.document
        require_body_sway_visual_review_candidate_v2(
            document, execution=loaded, preview=preview,
        )
        expected = exact_payload(
            supplied.canonical_bytes, document, supplied.sha256,
        )
        actual = read_document(
            state_root, document["project_id"], CANDIDATE_NAMESPACE,
            loaded.bundle_sha256, supplied.sha256,
        )
        if actual != expected:
            raise BodySwayVisualReviewBindingV2Error(
                "Candidate v2 differs from authoritative store replay"
            )
        return BodySwayVisualReviewCandidateV2(
            actual.decode("utf-8")
        ), loaded
    except BodySwayVisualReviewBindingV2Error:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError,
            TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayVisualReviewBindingV2Error(
            f"Authoritative visual candidate v2 replay failed: {exc}"
        ) from exc


__all__ = [
    "BodySwayVisualReviewBindingV2Error",
    "reload_authoritative_runtime_execution_v2",
    "reload_authoritative_visual_review_candidate_v2",
]
