"""Exact, read-only handoff from P10.2 canvas diagnosis to P10.1."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
from typing import Any

from .body_sway_probe_application import (
    BodySwayProbeApplication,
    BodySwayProbeApplicationError,
    BodySwayProbeApplicationHeadChanged,
    BodySwayProbeApplicationNotFound,
    BodySwayProbeApplicationUnavailable,
)
from .body_sway_derived_cache import (
    BodySwayDerivedCache,
    process_body_sway_derived_cache,
)
from .idle_behavior_review_application import (
    IdleBehaviorReviewApplication,
    IdleBehaviorReviewApplicationError,
    IdleBehaviorReviewApplicationNotFound,
    IdleBehaviorReviewApplicationUnavailable,
)


FORMAT = "autospine-idle-behavior-canvas-adjustment-draft-entry"
FORMAT_VERSION = 1
_SHA = re.compile(r"^[0-9a-f]{64}$")


class IdleBehaviorCanvasAdjustmentDraftError(RuntimeError):
    """Raised when a zero-authority adjustment handoff is unavailable."""


class IdleBehaviorCanvasAdjustmentDraftNotFound(
    IdleBehaviorCanvasAdjustmentDraftError
):
    """Raised when the requested package or adjustment identity is absent."""


class IdleBehaviorCanvasAdjustmentDraftStale(
    IdleBehaviorCanvasAdjustmentDraftError
):
    """Raised when the P10.1 head no longer matches the diagnostic."""


class IdleBehaviorCanvasAdjustmentDraftUnavailable(
    IdleBehaviorCanvasAdjustmentDraftError
):
    """Raised when exact evidence cannot be safely replayed."""


class IdleBehaviorCanvasAdjustmentDraftApplication:
    """Recompute and bind one P10.2 proposal to the current P10.1 entry."""

    def __init__(
        self, state_root: Path, *,
        derived_cache: BodySwayDerivedCache | None = None,
    ) -> None:
        self.state_root = Path(state_root)
        if derived_cache is not None \
                and type(derived_cache) is not BodySwayDerivedCache:
            raise IdleBehaviorCanvasAdjustmentDraftUnavailable(
                "Canvas adjustment derived cache is invalid"
            )
        self.derived_cache = derived_cache or process_body_sway_derived_cache()

    def prepare(
        self, package_id: str, candidate_sha256: str, *,
        project_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(candidate_sha256, str) \
                or not _SHA.fullmatch(candidate_sha256):
            raise IdleBehaviorCanvasAdjustmentDraftNotFound(
                "Canvas adjustment candidate identity is invalid"
            )
        try:
            probe = BodySwayProbeApplication(
                self.state_root, derived_cache=self.derived_cache,
            ).prepare(package_id, project_ids=project_ids)
            adjustment = probe.get("canvas_adjustment")
            if not isinstance(adjustment, dict) \
                    or adjustment.get("candidate_sha256") \
                    != candidate_sha256:
                raise IdleBehaviorCanvasAdjustmentDraftNotFound(
                    "Canvas adjustment candidate is no longer exact"
                )
            document = adjustment.get("document")
            proposals = document.get("adjustment_candidates") \
                if isinstance(document, dict) else None
            if not isinstance(proposals, list) or len(proposals) != 1:
                raise IdleBehaviorCanvasAdjustmentDraftNotFound(
                    "Canvas diagnosis has no applicable P10.1 draft"
                )
            entry = IdleBehaviorReviewApplication(self.state_root).prepare(
                package_id, project_ids=project_ids,
            )
            _require_current_binding(
                package_id, entry, probe, document,
            )
            return {
                "format": FORMAT,
                "format_version": FORMAT_VERSION,
                "status": "unvalidated_draft",
                "entry": entry,
                "canvas_adjustment": adjustment,
                "proposal": proposals[0],
            }
        except (
            IdleBehaviorCanvasAdjustmentDraftNotFound,
            IdleBehaviorCanvasAdjustmentDraftStale,
        ):
            raise
        except (
            BodySwayProbeApplicationHeadChanged,
        ) as exc:
            raise IdleBehaviorCanvasAdjustmentDraftStale(
                "P10.1 head changed during canvas adjustment handoff"
            ) from exc
        except (
            BodySwayProbeApplicationNotFound,
            IdleBehaviorReviewApplicationNotFound,
        ) as exc:
            raise IdleBehaviorCanvasAdjustmentDraftNotFound(
                "Canvas adjustment package is unavailable"
            ) from exc
        except (
            BodySwayProbeApplicationUnavailable,
            IdleBehaviorReviewApplicationUnavailable,
            BodySwayProbeApplicationError,
            IdleBehaviorReviewApplicationError,
            AttributeError, KeyError, TypeError, ValueError,
        ) as exc:
            raise IdleBehaviorCanvasAdjustmentDraftUnavailable(
                "Canvas adjustment handoff could not be prepared"
            ) from exc


def _require_current_binding(package_id, entry, probe, document) -> None:
    source = document["source"]["current_p10_1_head"]
    history = entry["history"]
    if probe["package"]["package_id"] != package_id \
            or entry["package"]["package_id"] != package_id \
            or entry["candidate_sha256"] != source["candidate_sha256"] \
            or probe["candidate_sha256"] != source["candidate_sha256"] \
            or history["current_revision"] != source["revision"] \
            or history["head_decision_sha256"] != source["decision_sha256"] \
            or probe["history"]["current_revision"] != source["revision"] \
            or probe["history"]["head_decision_sha256"] \
            != source["decision_sha256"]:
        raise IdleBehaviorCanvasAdjustmentDraftStale(
            "Canvas adjustment no longer matches the current P10.1 head"
        )
