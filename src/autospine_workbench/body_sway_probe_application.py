"""Read-only, path-free application service for P10.2 structural probes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .current_project_chain import CurrentProjectChain
from .body_sway_canvas_adjustment_candidates import (
    BodySwayCanvasAdjustmentError,
    compile_body_sway_canvas_adjustment_candidates,
)
from .body_sway_derived_cache import (
    BodySwayDerivedCache,
    BodySwayDerivedCacheError,
    BodySwayDerivedResult,
    body_sway_derived_cache_key,
    process_body_sway_derived_cache,
)
from .body_sway_probe_http_models import body_sway_probe_entry
from .body_sway_probe_inputs import (
    BodySwayProbeInputError,
    require_body_sway_probe_inputs,
)
from .body_sway_probe_packages import (
    BodySwayProbePackageError,
    classify_body_sway_probe_head,
    list_body_sway_probe_packages,
)
from .body_sway_probe_preview import (
    BodySwayProbePreviewError,
    build_body_sway_probe_preview,
)
from .body_sway_remediation_analysis import (
    BodySwayRemediationAnalysisError,
    compile_body_sway_remediation_analysis,
)
from .body_sway_probe_report import (
    BodySwayProbeReportError,
)
from .capture_framing_candidate import (
    CaptureFramingCandidateError,
    compile_capture_framing_candidate,
)
from .idle_behavior_review_head import (
    IdleBehaviorReviewHeadError,
    read_idle_behavior_review_head,
    same_idle_behavior_review_head,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
    get_idle_behavior_review_address,
)
from .idle_behavior_review_replay import (
    IdleBehaviorReviewReplayError,
    replay_idle_behavior_review_package,
)


class BodySwayProbeApplicationError(RuntimeError):
    """Raised when an operator P10.2 request cannot complete safely."""


class BodySwayProbeApplicationNotFound(BodySwayProbeApplicationError):
    """Raised when the selected exact package is unavailable."""


class BodySwayProbeApplicationHeadChanged(BodySwayProbeApplicationError):
    """Raised when the P10.1 current head changes during compilation."""


class BodySwayProbeApplicationUnavailable(BodySwayProbeApplicationError):
    """Raised when exact evidence cannot produce a public diagnostic."""


class BodySwayProbeApplication:
    """Discover or compile diagnostics without publishing any state."""

    def __init__(
        self, state_root: Path, *,
        derived_cache: BodySwayDerivedCache | None = None,
    ) -> None:
        self.state_root = Path(state_root)
        if derived_cache is not None \
                and type(derived_cache) is not BodySwayDerivedCache:
            raise BodySwayProbeApplicationUnavailable(
                "Body-sway derived cache is invalid"
            )
        self.derived_cache = derived_cache or process_body_sway_derived_cache()

    def list_packages(
        self, *, project_ids: Iterable[str] | None = None,
        current_project_chains: Mapping[
            str, CurrentProjectChain
        ] | None = None,
    ) -> dict[str, Any]:
        """Return current exact readiness with one unique recommendation."""

        try:
            return list_body_sway_probe_packages(
                self.state_root,
                project_ids=project_ids,
                current_project_chains=current_project_chains,
            )
        except BodySwayProbePackageError as exc:
            raise BodySwayProbeApplicationUnavailable(
                "Body-sway probe inventory is unavailable"
            ) from exc

    def prepare(
        self, package_id: str, *,
        project_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Compile one current exact head and reject any concurrent change."""

        try:
            address = get_idle_behavior_review_address(
                self.state_root, package_id, project_ids=project_ids,
            )
        except IdleBehaviorReviewPackageError as exc:
            raise BodySwayProbeApplicationNotFound(
                "The exact body-sway probe package is unavailable"
            ) from exc
        try:
            evidence = replay_idle_behavior_review_package(
                self.state_root, address,
            )
            candidates = evidence.candidates.document
            before = read_idle_behavior_review_head(
                self.state_root, candidates,
            )
            feature = next(
                row for row in candidates["features"]
                if row["feature_id"] == "body_sway"
            )
            report = preview = canvas_adjustment = dynamic_viewport = None
            rebind_candidates = ()
            if classify_body_sway_probe_head(feature, before) == "probe_ready":
                if before.decision is None:
                    raise BodySwayProbeApplicationUnavailable(
                        "Body-sway probe-ready head has no decision"
                    )
                inputs = require_body_sway_probe_inputs(
                    evidence.manifest,
                    candidates,
                    before.decision.document,
                    evidence.mesh_bundle,
                    evidence.retarget_bundle,
                    evidence.reviewed_contract,
                )
                key = body_sway_derived_cache_key(
                    self.state_root, address,
                    evidence.candidates.sha256, before,
                )
                derived = self.derived_cache.get_or_compile(
                    key, lambda: _compile_derived(
                        inputs, before, address.package_id,
                    ),
                )
                canvas_adjustment = derived.canvas_adjustment
                report = canvas_adjustment.reviewed_report
                preview = derived.preview
                dynamic_viewport = derived.dynamic_viewport
                rebind_candidates = derived.rebind_candidates
                capture_framing = derived.capture_framing
            else:
                capture_framing = None
            current = replay_idle_behavior_review_package(
                self.state_root, address,
            )
            if current.candidates.sha256 != evidence.candidates.sha256:
                raise BodySwayProbeApplicationHeadChanged(
                    "Body-sway candidate changed during probe compilation"
                )
            after = read_idle_behavior_review_head(
                self.state_root, current.candidates.document,
            )
            if not same_idle_behavior_review_head(before, after):
                raise BodySwayProbeApplicationHeadChanged(
                    "P10.1 current head changed during probe compilation"
                )
            return body_sway_probe_entry(
                evidence, before, report=report, preview=preview,
                canvas_adjustment=canvas_adjustment,
                dynamic_viewport=dynamic_viewport,
                rebind_candidates=rebind_candidates,
                capture_framing=capture_framing,
                state_root=self.state_root,
            )
        except BodySwayProbeApplicationHeadChanged:
            raise
        except BodySwayProbeApplicationUnavailable:
            raise
        except _PREPARE_FAILURES as exc:
            raise BodySwayProbeApplicationUnavailable(
                "Body-sway structural probe could not be completed"
            ) from exc


_PREPARE_FAILURES = (
    AttributeError, BodySwayCanvasAdjustmentError, BodySwayDerivedCacheError,
    BodySwayProbeInputError, BodySwayProbePreviewError,
    BodySwayProbeReportError, BodySwayRemediationAnalysisError,
    CaptureFramingCandidateError,
    IdleBehaviorReviewHeadError,
    IdleBehaviorReviewReplayError, KeyError, OSError, OverflowError,
    RuntimeError, StopIteration, TypeError, UnicodeError, ValueError,
)


def _compile_derived(inputs, current_head, package_id) -> BodySwayDerivedResult:
    adjustment = compile_body_sway_canvas_adjustment_candidates(
        inputs, current_head,
    )
    preview = build_body_sway_probe_preview(
        inputs, adjustment.reviewed_report,
    )
    remediation = compile_body_sway_remediation_analysis(
        inputs, adjustment.reviewed_report,
    )
    framing = None
    report_document = adjustment.reviewed_report.document
    rejected = sorted(
        row["check_id"] for row in report_document["checks"]
        if row["status"] == "rejected"
    )
    if report_document["status"] == "structural_rejected" \
            and rejected == ["sampled_canvas_containment"] \
            and remediation.dynamic_viewport.document["fit_status"] == "fitted" \
            and adjustment.document["diagnosis"]["classification"] \
            == "upstream_base_motion_canvas_overflow" \
            and adjustment.capture_framing_envelopes is not None:
        framing = compile_capture_framing_candidate(
            inputs, adjustment.reviewed_report,
            remediation.dynamic_viewport, current_head,
            package_id=package_id,
            envelope_set=adjustment.capture_framing_envelopes,
        )
    return BodySwayDerivedResult.freeze(
        adjustment, preview, remediation.dynamic_viewport,
        remediation.rebind_candidates,
        framing,
    )
