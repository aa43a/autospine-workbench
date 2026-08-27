"""Read-only current-head input boundary for P10.5c compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable

from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_binding_validation import (
    ReviewedSeamAnchorSetBindingValidationError,
    require_bound_reviewed_seam_anchor_set,
)
from .reviewed_seam_anchor_set_compiler import (
    ReviewedSeamAnchorSet,
    ReviewedSeamAnchorSetCompilerError,
    compile_reviewed_seam_anchor_set,
)
from .reviewed_seam_anchor_set_input_checks import (
    INPUT_CHECK_FAILURES,
    ReviewedSeamAnchorSetInputCheckError,
    require_current_ready_seam_anchor_snapshot,
    require_exact_seam_anchor_decision,
    require_reviewed_seam_anchor_set_input_content,
)
from .reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    reviewed_seam_anchor_set_sha256,
)
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_application import (
    SeamAnchorReviewApplication,
    SeamAnchorReviewApplicationError,
)
from .seam_anchor_review_application_models import (
    ExactSeamAnchorReviewDecision,
    PreparedSeamAnchorReview,
)
from .seam_anchor_review_candidate_binding import (
    BoundSeamAnchorReviewCandidate,
    SeamAnchorReviewCandidateBindingError,
    load_bound_seam_anchor_review_candidate,
)
from .seam_anchor_review_history_models import SeamAnchorReviewHistorySnapshot
from .seam_anchor_review_json import canonical_json_bytes


class ReviewedSeamAnchorSetInputsError(RuntimeError):
    """Raised when an exact current review head cannot be compiled safely."""


@dataclass(frozen=True, slots=True)
class ReviewedSeamAnchorSetInputs:
    """Frozen detached inputs observed as current only during this compile."""

    address: ExactSeamAnchorReviewAddress
    candidate_sha256: str
    review_revision: int
    decision_sha256: str
    history_before: SeamAnchorReviewHistorySnapshot
    history_after: SeamAnchorReviewHistorySnapshot
    _candidate_json: str = field(repr=False)
    _decision_json: str = field(repr=False)
    _rig_json: str = field(repr=False)

    @property
    def candidate_document(self) -> dict[str, Any]:
        return json.loads(self._candidate_json)

    @property
    def decision_document(self) -> dict[str, Any]:
        return json.loads(self._decision_json)

    @property
    def rig_document(self) -> dict[str, Any]:
        return json.loads(self._rig_json)


@dataclass(frozen=True, slots=True)
class PreparedReviewedSeamAnchorSet:
    """Frozen path-free set; its head observation has compile-time scope."""

    inputs: ReviewedSeamAnchorSetInputs = field(repr=False)
    reviewed_seam_anchor_set_sha256: str
    _reviewed_set_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._reviewed_set_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._reviewed_set_json.encode("utf-8")

    @property
    def head_observation(self) -> dict[str, Any]:
        return {
            "method": "double_snapshot",
            "scope": "compile_time",
            "revision": self.inputs.review_revision,
            "head_decision_sha256": self.inputs.decision_sha256,
            "permanent_authority_claimed": False,
        }


def prepare_current_head_reviewed_seam_anchor_set(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
    *,
    candidate_sha256: str,
    revision: int,
    decision_sha256: str,
    application=None,
    candidate_loader: Callable | None = None,
    compiler: Callable | None = None,
) -> PreparedReviewedSeamAnchorSet:
    """Read A, exact decision, exact P3/compile, then read matching B."""

    try:
        if type(address) is not ExactSeamAnchorReviewAddress:
            raise ReviewedSeamAnchorSetInputsError(
                "Reviewed seam compilation requires an exact address"
            )
        state = Path(state_root)
        service = application or SeamAnchorReviewApplication(state)
        load_candidate = candidate_loader \
            or load_bound_seam_anchor_review_candidate
        compile_set = compiler or compile_reviewed_seam_anchor_set

        before = service.prepare(address)
        require_current_ready_seam_anchor_snapshot(
            before, address, candidate_sha256, revision, decision_sha256
        )
        exact = service.exact_decision(
            address, candidate_sha256=candidate_sha256,
            revision=revision, decision_sha256=decision_sha256,
        )
        require_exact_seam_anchor_decision(
            exact, address, candidate_sha256, revision, decision_sha256,
            history=before.history,
        )
        bound = load_candidate(state, address)
        _require_bound_candidate(before, bound, address, candidate_sha256)
        compiled = compile_set(
            bound.candidates.document, exact.decision_document, bound.rig
        )
        _require_compiled(compiled, bound, exact)

        after = service.prepare(address)
        inputs = build_reviewed_seam_anchor_set_inputs(
            before, exact, bound, after,
            address=address, candidate_sha256=candidate_sha256,
            revision=revision, decision_sha256=decision_sha256,
        )
        return PreparedReviewedSeamAnchorSet(
            inputs, compiled.sha256,
            compiled.canonical_bytes.decode("utf-8"),
        )
    except ReviewedSeamAnchorSetInputsError:
        raise
    except _FAILURES as exc:
        raise ReviewedSeamAnchorSetInputsError(
            f"Current-head reviewed seam compilation failed: {exc}"
        ) from exc


def build_reviewed_seam_anchor_set_inputs(
    before: PreparedSeamAnchorReview,
    exact: ExactSeamAnchorReviewDecision,
    bound: BoundSeamAnchorReviewCandidate,
    after: PreparedSeamAnchorReview,
    *,
    address: ExactSeamAnchorReviewAddress,
    candidate_sha256: str,
    revision: int,
    decision_sha256: str,
) -> ReviewedSeamAnchorSetInputs:
    """Freeze exact application values after their second observation."""

    try:
        if type(before) is not PreparedSeamAnchorReview \
                or type(exact) is not ExactSeamAnchorReviewDecision \
                or type(bound) is not BoundSeamAnchorReviewCandidate \
                or type(after) is not PreparedSeamAnchorReview:
            raise ReviewedSeamAnchorSetInputsError(
                "Reviewed seam input values have unsupported representations"
            )
        if before != after:
            raise ReviewedSeamAnchorSetInputsError(
                "Seam-review application values changed between snapshots"
            )
        require_current_ready_seam_anchor_snapshot(
            before, address, candidate_sha256, revision, decision_sha256
        )
        _require_bound_candidate(before, bound, address, candidate_sha256)
        require_exact_seam_anchor_decision(
            exact, address, candidate_sha256, revision, decision_sha256,
            history=before.history,
        )
        value = ReviewedSeamAnchorSetInputs(
            address, candidate_sha256, revision, decision_sha256,
            before.history, after.history,
            bound.candidates.canonical_bytes.decode("utf-8"),
            canonical_json_bytes(exact.decision_document).decode("utf-8"),
            canonical_json_bytes(bound.rig).decode("utf-8"),
        )
        return require_reviewed_seam_anchor_set_inputs(value)
    except ReviewedSeamAnchorSetInputsError:
        raise
    except _FAILURES as exc:
        raise ReviewedSeamAnchorSetInputsError(
            f"Reviewed seam input build failed: {exc}"
        ) from exc


def require_reviewed_seam_anchor_set_inputs(
    value: ReviewedSeamAnchorSetInputs,
) -> ReviewedSeamAnchorSetInputs:
    """Revalidate frozen input bytes without granting later head authority."""

    try:
        if type(value) is not ReviewedSeamAnchorSetInputs \
                or type(value.address) is not ExactSeamAnchorReviewAddress:
            raise ReviewedSeamAnchorSetInputsError(
                "Reviewed seam input has the wrong representation"
            )
        require_reviewed_seam_anchor_set_input_content(value)
        return value
    except ReviewedSeamAnchorSetInputsError:
        raise
    except _FAILURES as exc:
        raise ReviewedSeamAnchorSetInputsError(
            f"Reviewed seam input validation failed: {exc}"
        ) from exc


def _require_bound_candidate(before, bound, address, candidate_sha) -> None:
    source = bound.candidates.document["source"] \
        if type(bound) is BoundSeamAnchorReviewCandidate else {}
    if type(bound) is not BoundSeamAnchorReviewCandidate \
            or bound.candidates.sha256 != candidate_sha \
            or bound.candidates.canonical_bytes \
                != canonical_json_bytes(before.candidate_document) \
            or bound.candidates.document["project_id"] != address.project_id \
            or source.get("layer_manifest_sha256") \
                != address.layer_manifest_sha256 \
            or source.get("rig_sha256") != address.p3_rig_sha256 \
            or source.get("bundle_sha256") != address.p3_bundle_sha256 \
            or canonical_sha256(bound.rig) != address.p3_rig_sha256 \
            or canonical_json_bytes(bound.rig).decode("utf-8") \
                != bound._rig_json:
        raise ReviewedSeamAnchorSetInputsError(
            "Exact P3 replay differs from the first candidate snapshot"
        )


def _require_compiled(compiled, bound, exact) -> None:
    if type(compiled) is not ReviewedSeamAnchorSet:
        raise ReviewedSeamAnchorSetInputsError(
            "Reviewed seam compiler returned an unsupported value"
        )
    candidate, decision, rig = (
        bound.candidates.document, exact.decision_document, bound.rig
    )
    require_bound_reviewed_seam_anchor_set(
        compiled.document, candidate, decision, rig
    )
    if reviewed_seam_anchor_set_sha256(compiled.document) != compiled.sha256:
        raise ReviewedSeamAnchorSetInputsError(
            "Reviewed seam compiler identity is inconsistent"
        )


_FAILURES = (
    AttributeError, *INPUT_CHECK_FAILURES,
    ReviewedSeamAnchorSetBindingValidationError,
    ReviewedSeamAnchorSetCompilerError,
    ReviewedSeamAnchorSetInputCheckError,
    ReviewedSeamAnchorSetValidationError,
    SeamAnchorReviewApplicationError,
    SeamAnchorReviewCandidateBindingError,
)
