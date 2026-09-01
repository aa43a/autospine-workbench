"""Pure exact-address application service for P10.3c v2 human review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecutionReader,
)
from .body_sway_visual_review_address_v2 import ExactVisualReviewAddressV2
from .body_sway_visual_review_application_models_v2 import (
    BodySwayVisualReviewImageV2, ExactBodySwayVisualReviewDecisionV2,
    PreparedBodySwayVisualReviewV2, SubmittedBodySwayVisualReviewV2,
)
from .body_sway_visual_review_application_support_v2 import (
    load_previous_visual_review_decision_v2,
    require_consistent_visual_review_history_v2,
    require_visual_review_compare_and_swap_v2,
    submitted_visual_review_result_v2,
)
from .body_sway_visual_review_candidate_v2 import (
    compile_body_sway_visual_review_candidate_v2,
)
from .body_sway_visual_review_decision_v2 import (
    build_body_sway_visual_review_decision_v2,
)
from .body_sway_visual_review_errors_v2 import (
    BodySwayVisualReviewRevisionV2Conflict,
)
from .body_sway_visual_review_image_snapshot_v2 import (
    compile_body_sway_visual_review_image_snapshot_v2,
)
from .body_sway_visual_review_profile_v2 import MAX_VISUAL_REVIEW_REVISIONS
from .body_sway_visual_review_store_v2 import BodySwayVisualReviewStoreV2
from .body_sway_visual_review_submission import (
    require_body_sway_visual_review_submission,
)
from .manifest_artifacts import require_safe_token, require_sha256
from .p10_preview_v2_commands import (
    P10PreviewV2CommandResult, require_exact_preview_v2_for_mount,
)
from .p10_visual_review_v2_verified_mount import (
    VerifiedP10VisualReviewV2Mount,
)


PreviewMountInput = (
    P10PreviewV2CommandResult | VerifiedP10VisualReviewV2Mount
)


class BodySwayVisualReviewApplicationV2Error(RuntimeError):
    pass


class BodySwayVisualReviewApplicationV2NotFound(
    BodySwayVisualReviewApplicationV2Error,
):
    pass


class BodySwayVisualReviewApplicationV2InvalidSubmission(
    BodySwayVisualReviewApplicationV2Error,
):
    pass


class BodySwayVisualReviewApplicationV2:
    """Compile current evidence and CAS only explicit human choices."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self._reader = VerifiedBodySwayRuntimeExecutionReader(self.state_root)
        self._store = BodySwayVisualReviewStoreV2(self.state_root)

    def prepare(
        self, address: ExactVisualReviewAddressV2,
        preview_result: PreviewMountInput,
    ) -> PreparedBodySwayVisualReviewV2:
        try:
            execution, preview, candidate = self._load_candidate(
                address, preview_result,
            )
            history = self._store.snapshot_history(
                candidates=candidate, execution=execution, preview=preview,
            )
            require_consistent_visual_review_history_v2(candidate, history)
            return PreparedBodySwayVisualReviewV2(
                address, candidate.sha256,
                candidate.canonical_bytes.decode("utf-8"), history,
            )
        except BodySwayVisualReviewApplicationV2Error:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationV2Error(
                "Visual review v2 preparation failed"
            ) from exc

    def image_evidence(
        self, address: ExactVisualReviewAddressV2,
        preview_result: PreviewMountInput, *,
        candidate_sha256: str, case_id: str, png_sha256: str,
    ) -> BodySwayVisualReviewImageV2:
        images = self.prepare_image_snapshot(
            address, preview_result,
            candidate_sha256=candidate_sha256,
        )
        try:
            expected_case = require_safe_token(case_id, "Visual review v2 case")
            expected_png = require_sha256(png_sha256, "Visual review v2 PNG")
            rows = [row for row in images if row.case_id == expected_case]
            if len(rows) != 1 or rows[0].png_sha256 != expected_png:
                raise BodySwayVisualReviewApplicationV2NotFound(
                    "Visual review image v2 identity is cross-wired"
                )
            return rows[0]
        except BodySwayVisualReviewApplicationV2Error:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationV2Error(
                "Visual review image v2 load failed"
            ) from exc

    def prepare_image_snapshot(
        self, address: ExactVisualReviewAddressV2,
        preview_result: PreviewMountInput, *,
        candidate_sha256: str,
    ) -> tuple[BodySwayVisualReviewImageV2, ...]:
        """Replay one candidate once and expose its verified immutable PNGs."""

        try:
            candidate_address = require_sha256(
                candidate_sha256, "Visual review candidate v2",
            )
            execution, _preview, candidate = self._load_candidate(
                address, preview_result,
            )
            if candidate.sha256 != candidate_address:
                raise BodySwayVisualReviewApplicationV2NotFound(
                    "Visual review candidate v2 address is stale"
                )
            return compile_body_sway_visual_review_image_snapshot_v2(
                execution, candidate,
            )
        except BodySwayVisualReviewApplicationV2Error:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationV2Error(
                "Visual review image v2 snapshot failed"
            ) from exc

    def exact_decision(
        self, address: ExactVisualReviewAddressV2,
        preview_result: PreviewMountInput, *,
        candidate_sha256: str, revision: int, decision_sha256: str,
    ) -> ExactBodySwayVisualReviewDecisionV2:
        try:
            candidate_address = require_sha256(
                candidate_sha256, "Visual review candidate v2",
            )
            decision_address = require_sha256(
                decision_sha256, "Visual review decision v2",
            )
            if type(revision) is not int \
                    or not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
                raise BodySwayVisualReviewApplicationV2Error(
                    "Visual review revision v2 address is invalid"
                )
            execution, preview, candidate = self._load_candidate(
                address, preview_result,
            )
            if candidate.sha256 != candidate_address:
                raise BodySwayVisualReviewApplicationV2NotFound(
                    "Visual review candidate v2 address is stale"
                )
            history = self._store.snapshot_history(
                candidates=candidate, execution=execution, preview=preview,
            )
            require_consistent_visual_review_history_v2(candidate, history)
            if revision > history.current_revision \
                    or history.rows[revision - 1].decision_sha256 \
                    != decision_address:
                raise BodySwayVisualReviewApplicationV2NotFound(
                    "Visual review decision v2 is not an exact revision"
                )
            decision = self._store.load_decision(
                address.project_id, candidate.sha256, decision_address,
                candidates=candidate, execution=execution, preview=preview,
            )
            if decision.document["review"]["revision"] != revision:
                raise BodySwayVisualReviewApplicationV2Error(
                    "Visual review decision v2 revision is inconsistent"
                )
            return ExactBodySwayVisualReviewDecisionV2(
                address, candidate.sha256, decision.sha256, revision,
                decision.canonical_bytes.decode("utf-8"),
            )
        except BodySwayVisualReviewApplicationV2Error:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationV2Error(
                "Visual review decision v2 load failed"
            ) from exc

    def submit(
        self, address: ExactVisualReviewAddressV2,
        preview_result: PreviewMountInput,
        payload: dict[str, Any],
    ) -> SubmittedBodySwayVisualReviewV2:
        try:
            submission = require_body_sway_visual_review_submission(payload)
            execution, preview, candidate = self._load_candidate(
                address, preview_result,
            )
            if submission.candidate_sha256 != candidate.sha256:
                raise BodySwayVisualReviewApplicationV2InvalidSubmission(
                    "Visual review v2 submission candidate is stale"
                )
            history = self._store.snapshot_history(
                candidates=candidate, execution=execution, preview=preview,
            )
            require_consistent_visual_review_history_v2(candidate, history)
            previous = load_previous_visual_review_decision_v2(
                self._store, submission, candidate, execution, preview, history,
            )
            decision = build_body_sway_visual_review_decision_v2(
                candidate.document, review=submission.review,
                decisions=list(submission.decisions),
                previous_decision=(previous.document if previous else None),
            )
            require_visual_review_compare_and_swap_v2(
                submission, decision.sha256, history,
            )
            self._store.publish_candidate(candidate, execution, preview)
            published = self._store.publish_decision(
                decision, candidates=candidate,
                execution=execution, preview=preview,
            )
            loaded = self._store.load_decision(
                address.project_id, candidate.sha256, published.sha256,
                candidates=candidate, execution=execution, preview=preview,
            )
            if loaded.canonical_bytes != decision.canonical_bytes:
                raise BodySwayVisualReviewApplicationV2Error(
                    "Visual review decision v2 readback differs"
                )
            return submitted_visual_review_result_v2(
                address, candidate, loaded.document, loaded.sha256,
                published.reused,
            )
        except BodySwayVisualReviewRevisionV2Conflict:
            raise
        except BodySwayVisualReviewApplicationV2Error:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationV2Error(
                "Visual review v2 submission failed"
            ) from exc

    def _load_candidate(self, address, preview_result):
        if type(address) is not ExactVisualReviewAddressV2:
            raise BodySwayVisualReviewApplicationV2Error(
                "Visual review v2 requires an exact four-part address"
            )
        if type(preview_result) is VerifiedP10VisualReviewV2Mount:
            result = preview_result.result
            preview = preview_result.preview
            execution = preview_result.execution
        else:
            result = None
            preview = require_exact_preview_v2_for_mount(preview_result)
            execution = None
        if (
            result is not None and (
                result.temporary_preview_v2_sha256
                    != address.temporary_preview_v2_sha256
                or result.project_id != address.project_id
            )
        ) or preview.sha256 != address.temporary_preview_v2_sha256 \
                or preview.document["project_id"] != address.project_id:
            raise BodySwayVisualReviewApplicationV2Error(
                "Current Preview v2 differs from the execution address"
            )
        if execution is None:
            execution = self._reader.load(*address.reader_arguments)
        candidate = compile_body_sway_visual_review_candidate_v2(
            execution, preview,
        )
        return execution, preview, candidate

_APPLICATION_ERRORS = (
    AttributeError, KeyError, OSError, OverflowError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)
