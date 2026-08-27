"""Read-only P10.7b sampled raster review application commands."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .safe_input_files import SafeInputFileError, read_real_file, strict_json_object
from .spine42_v3_bundle_reader import (
    VerifiedSpine42V3BundleReader,
    VerifiedSpine42V3BundleReaderError,
)
from .spine42_v3_raster_review import (
    Spine42V3RasterReviewError,
    build_spine42_v3_raster_review_decision,
    canonical_spine42_v3_raster_review_bytes,
    compile_spine42_v3_raster_review_candidate,
)
from .spine42_v3_runtime_reader import (
    Spine42V3RuntimeReaderError,
    VerifiedSpine42V3RuntimeReader,
)


MAX_REVIEW_INPUT_BYTES = 16 * 1024 * 1024


class P10Spine42V3RasterReviewCommandError(RuntimeError):
    """Fixed failure boundary for candidate and human decision commands."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3RasterReviewResult:
    mode: str
    project_id: str
    clip_id: str
    document_sha256: str
    status: str
    _document_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._document_json)


def prepare_spine42_v3_raster_review_command(
    state_root: Path,
    project_id: str,
    *,
    spine42_v3_bundle_sha256: str,
    capture_bundle_sha256: str,
) -> P10Spine42V3RasterReviewResult:
    """Replay source and capture addresses, then generate candidate-only rows."""

    try:
        capture = VerifiedSpine42V3RuntimeReader(state_root).load(
            project_id, spine42_v3_bundle_sha256,
            capture_bundle_sha256,
        )
        source = capture.evidence.manifest["source"]
        upstream = VerifiedSpine42V3BundleReader(state_root).load(
            project_id, source["skeleton_json_sha256"],
            spine42_v3_bundle_sha256,
        )
        if (
            upstream.project_id, upstream.clip_id,
            upstream.skeleton_json_sha256, upstream.bundle_sha256,
            upstream.run_document_sha256,
        ) != (
            capture.project_id, capture.evidence.clip_id,
            source["skeleton_json_sha256"],
            source["spine42_v3_bundle_sha256"],
            source["run_document_sha256"],
        ):
            raise P10Spine42V3RasterReviewCommandError(
                "Raster evidence differs from exact P10.7a source replay"
            )
        candidate = compile_spine42_v3_raster_review_candidate(
            capture.evidence.manifest, capture.evidence.metrics,
            capture_bundle_sha256=capture.capture_bundle_sha256,
        )
        return _result("candidate", candidate, "candidate_sha256")
    except P10Spine42V3RasterReviewCommandError:
        raise
    except _FAILURES as exc:
        raise P10Spine42V3RasterReviewCommandError(
            "Spine v3 raster review candidate preparation failed"
        ) from exc


def submit_spine42_v3_raster_review_command(
    state_root: Path,
    project_id: str,
    candidate_path: Path,
    review_input_path: Path,
    *,
    spine42_v3_bundle_sha256: str,
    capture_bundle_sha256: str,
    previous_decision_path: Path | None = None,
) -> P10Spine42V3RasterReviewResult:
    """Replay the exact candidate before compiling exhaustive human input."""

    try:
        candidate = _read(candidate_path, "raster review candidate")
        replayed = prepare_spine42_v3_raster_review_command(
            state_root, project_id,
            spine42_v3_bundle_sha256=spine42_v3_bundle_sha256,
            capture_bundle_sha256=capture_bundle_sha256,
        ).document
        if canonical_spine42_v3_raster_review_bytes(candidate) != \
                canonical_spine42_v3_raster_review_bytes(replayed):
            raise P10Spine42V3RasterReviewCommandError(
                "Raster review candidate differs from exact evidence replay"
            )
        review = _read(review_input_path, "raster review input")
        if set(review) != {
            "reviewer_id", "notes", "case_decisions",
            "attachment_decisions",
        }:
            raise P10Spine42V3RasterReviewCommandError(
                "Raster review input fields are unsupported"
            )
        previous = _read(
            previous_decision_path, "previous raster review decision"
        ) if previous_decision_path is not None else None
        decision = build_spine42_v3_raster_review_decision(
            candidate, reviewer_id=review["reviewer_id"],
            notes=review["notes"],
            case_decisions=review["case_decisions"],
            attachment_decisions=review["attachment_decisions"],
            previous_decision=previous,
        )
        return _result("decision", decision, "decision_sha256")
    except P10Spine42V3RasterReviewCommandError:
        raise
    except _FAILURES as exc:
        raise P10Spine42V3RasterReviewCommandError(
            "Spine v3 raster review decision compilation failed"
        ) from exc


def _read(path: Path, label: str) -> dict[str, Any]:
    return strict_json_object(
        read_real_file(Path(path), MAX_REVIEW_INPUT_BYTES, label), label
    )


def _result(mode, document, digest_field):
    canonical = json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
    return P10Spine42V3RasterReviewResult(
        mode, document["project_id"], document["clip_id"],
        document[digest_field], document["status"], canonical,
    )


_FAILURES = (
    AttributeError, KeyError, OSError, RuntimeError, SafeInputFileError,
    Spine42V3RasterReviewError, Spine42V3RuntimeReaderError,
    TypeError, ValueError, VerifiedSpine42V3BundleReaderError,
)


__all__ = [
    "P10Spine42V3RasterReviewCommandError",
    "P10Spine42V3RasterReviewResult",
    "prepare_spine42_v3_raster_review_command",
    "submit_spine42_v3_raster_review_command",
]
