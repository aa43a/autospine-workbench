"""Path-free discovery and readiness classification for P10.2 probes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .current_project_chain import CurrentProjectChain
from .idle_behavior_review_head import (
    IdleBehaviorReviewHeadError,
    read_idle_behavior_review_head,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
    list_idle_behavior_review_addresses,
    list_current_idle_behavior_review_addresses,
)
from .idle_behavior_review_replay import (
    IdleBehaviorReviewReplayError,
    replay_idle_behavior_review_package,
)


LIST_FORMAT = "autospine-body-sway-probe-package-list"
PACKAGE_FORMAT = "autospine-body-sway-probe-package"
FORMAT_VERSION = 1


class BodySwayProbePackageError(RuntimeError):
    """Raised when the P10.2 package inventory cannot be resolved safely."""


def list_body_sway_probe_packages(
    state_root: Path,
    *,
    project_ids: Iterable[str] | None = None,
    current_project_chains: Mapping[str, CurrentProjectChain] | None = None,
) -> dict[str, Any]:
    """Classify exact current P10.1 heads and recommend one unique ready row."""

    try:
        if current_project_chains is None:
            addresses, skipped = list_idle_behavior_review_addresses(
                state_root, project_ids=project_ids,
            )
        else:
            addresses, skipped = list_current_idle_behavior_review_addresses(
                state_root,
                project_ids=project_ids,
                current_project_chains=current_project_chains,
            )
        rows = []
        for address in addresses:
            try:
                evidence = replay_idle_behavior_review_package(
                    state_root, address,
                )
                head = read_idle_behavior_review_head(
                    state_root, evidence.candidates.document,
                )
                rows.append(_row(evidence, head))
            except (
                IdleBehaviorReviewHeadError,
                IdleBehaviorReviewReplayError,
            ):
                skipped += 1
        ready = [row for row in rows if row["status"] == "probe_ready"]
        counts = {
            status: sum(row["status"] == status for row in rows)
            for status in (
                "probe_ready", "not_applicable", "p10_1_review_required",
            )
        }
        return {
            "format": LIST_FORMAT,
            "format_version": FORMAT_VERSION,
            "count": len(rows),
            "ready_count": counts["probe_ready"],
            "not_applicable_count": counts["not_applicable"],
            "review_required_count": counts["p10_1_review_required"],
            "skipped_count": skipped,
            "recommended_package_id": (
                ready[0]["package_id"]
                if current_project_chains is not None
                and len(ready) == 1 and skipped == 0 else None
            ),
            "packages": rows,
        }
    except BodySwayProbePackageError:
        raise
    except (
        AttributeError, IdleBehaviorReviewPackageError, KeyError,
        OSError, OverflowError, StopIteration, TypeError, ValueError,
    ) as exc:
        raise BodySwayProbePackageError(
            "Body-sway probe packages could not be resolved"
        ) from exc


def _row(evidence, head) -> dict[str, Any]:
    address, candidates = evidence.address, evidence.candidates
    feature = next(
        row for row in candidates.document["features"]
        if row["feature_id"] == "body_sway"
    )
    decision = head.decision.document["decisions"][0] \
        if head.decision is not None else None
    status = classify_body_sway_probe_head(feature, head)
    return {
        "format": PACKAGE_FORMAT,
        "format_version": FORMAT_VERSION,
        "package_id": address.package_id,
        "project_id": address.project_id,
        "motion_id": address.motion_id,
        "clip_id": address.clip_id,
        "p9_decision_sha256": address.p9_decision_sha256,
        "candidate_sha256": candidates.sha256,
        "current_revision": head.current_revision,
        "decision_sha256": head.decision_sha256,
        "action": decision["action"] if decision is not None else None,
        "probe_status": (
            decision["probe_status"] if decision is not None else None
        ),
        "status": status,
    }


def classify_body_sway_probe_head(feature, head) -> str:
    """Map exact candidate/head evidence to one operator-facing state."""

    if head.decision is None:
        return (
            "p10_1_review_required"
            if feature["availability"] == "candidate"
            else "not_applicable"
        )
    decision = head.decision.document["decisions"][0]
    if decision["action"] == "adjust" \
            and decision["probe_status"] == "pending_probe":
        return "probe_ready"
    return "not_applicable"
