"""Resolve adopted P9 bundles into path-free P10 idle-review packages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .current_project_chain import CurrentProjectChain, chain_is_current
from .idle_behavior_adopted_runs import (
    AdoptedRun,
    AdoptedRunInventoryError,
    list_adopted_runs,
)
from .idle_behavior_review_address import IdleBehaviorReviewAddress
from .idle_behavior_review_profile import (
    FORMAT_VERSION,
    LIST_FORMAT,
    MAX_PACKAGES,
    PACKAGE_FORMAT,
)
from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    list_motion_policy_review_packages,
)


_SHA = re.compile(r"^[0-9a-f]{64}$")


class IdleBehaviorReviewPackageError(RuntimeError):
    """Raised when adopted P9 package inventory cannot be inspected safely."""


class IdleBehaviorReviewPackageStale(IdleBehaviorReviewPackageError):
    """Raised when a historical package is selected for mutation."""


@dataclass(frozen=True, slots=True)
class _ResolvedAddress:
    address: IdleBehaviorReviewAddress
    current: bool


def list_idle_behavior_review_packages(
    state_root: Path,
    *,
    project_ids: Iterable[str] | None = None,
    current_project_chains: Mapping[str, CurrentProjectChain] | None = None,
) -> dict[str, Any]:
    """Match validated review packages to every exact adopted P9 bundle."""

    allowed = set(project_ids) if project_ids is not None else None
    records, skipped = _resolved_addresses(
        state_root, allowed, current_project_chains,
    )
    records.sort(key=lambda row: (
        row.address.project_id, row.address.motion_id,
        row.address.p9_decision_sha256, row.address.package_id,
    ))
    if len(records) > MAX_PACKAGES:
        raise IdleBehaviorReviewPackageError(
            "Idle behavior review package count exceeds its limit"
        )
    rows = [_summary(record) for record in records]
    return {
        "format": LIST_FORMAT,
        "format_version": FORMAT_VERSION,
        "count": len(rows),
        "skipped_count": skipped,
        "recommended_package_id": _recommended(rows),
        "packages": rows,
    }


def list_idle_behavior_review_addresses(
    state_root: Path,
    *,
    project_ids: Iterable[str] | None = None,
) -> tuple[tuple[IdleBehaviorReviewAddress, ...], int]:
    """Return sorted exact addresses for trusted in-process consumers."""

    try:
        allowed = set(project_ids) if project_ids is not None else None
        records, skipped = _resolved_addresses(state_root, allowed, None)
        addresses = [record.address for record in records]
        addresses.sort(key=lambda row: (
            row.project_id, row.motion_id,
            row.p9_decision_sha256, row.package_id,
        ))
        if len(addresses) > MAX_PACKAGES:
            raise IdleBehaviorReviewPackageError(
                "Idle behavior review package count exceeds its limit"
            )
        return tuple(addresses), skipped
    except IdleBehaviorReviewPackageError:
        raise
    except (
        KeyError, MotionPolicyReviewPackageError, OSError, TypeError,
        ValueError,
    ) as exc:
        raise IdleBehaviorReviewPackageError(
            "Idle behavior review addresses could not be resolved"
        ) from exc


def list_current_idle_behavior_review_addresses(
    state_root: Path,
    *,
    project_ids: Iterable[str] | None = None,
    current_project_chains: Mapping[str, CurrentProjectChain],
) -> tuple[tuple[IdleBehaviorReviewAddress, ...], int]:
    """Return only adopted P9 addresses bound to current authoring bytes."""

    try:
        allowed = set(project_ids) if project_ids is not None else None
        records, skipped = _resolved_addresses(
            state_root, allowed, current_project_chains,
        )
        addresses = [record.address for record in records if record.current]
        addresses.sort(key=lambda row: (
            row.project_id, row.motion_id,
            row.p9_decision_sha256, row.package_id,
        ))
        if len(addresses) > MAX_PACKAGES:
            raise IdleBehaviorReviewPackageError(
                "Idle behavior review package count exceeds its limit"
            )
        return tuple(addresses), skipped
    except IdleBehaviorReviewPackageError:
        raise
    except (
        KeyError, MotionPolicyReviewPackageError, OSError, TypeError,
        ValueError,
    ) as exc:
        raise IdleBehaviorReviewPackageError(
            "Current idle behavior review addresses could not be resolved"
        ) from exc


def get_idle_behavior_review_address(
    state_root: Path,
    package_id: str,
    *,
    project_ids: Iterable[str] | None = None,
) -> IdleBehaviorReviewAddress:
    """Resolve one selected identity; never fall back to another adoption."""

    if not isinstance(package_id, str) or not _SHA.fullmatch(package_id):
        raise IdleBehaviorReviewPackageError(
            "Idle behavior review package id is invalid"
        )
    allowed = set(project_ids) if project_ids is not None else None
    records, _skipped = _resolved_addresses(state_root, allowed, None)
    matches = [
        row.address for row in records
        if row.address.package_id == package_id
    ]
    if len(matches) != 1:
        raise IdleBehaviorReviewPackageError(
            "The exact idle behavior review package is unavailable"
        )
    return matches[0]


def require_current_idle_behavior_review_address(
    state_root: Path,
    package_id: str,
    *,
    project_ids: Iterable[str] | None = None,
    current_project_chains: Mapping[str, CurrentProjectChain],
) -> IdleBehaviorReviewAddress:
    """Admit mutation only for one exact package on the current chain."""

    if not isinstance(package_id, str) or not _SHA.fullmatch(package_id):
        raise IdleBehaviorReviewPackageError(
            "Idle behavior review package id is invalid"
        )
    allowed = set(project_ids) if project_ids is not None else None
    records, _skipped = _resolved_addresses(
        state_root, allowed, current_project_chains,
    )
    matches = [
        row for row in records if row.address.package_id == package_id
    ]
    if len(matches) != 1:
        raise IdleBehaviorReviewPackageError(
            "The exact idle behavior review package is unavailable"
        )
    if not matches[0].current:
        raise IdleBehaviorReviewPackageStale(
            "Historical idle behavior review packages are read-only"
        )
    return matches[0].address


def _summary(record: _ResolvedAddress) -> dict[str, Any]:
    address = record.address
    return {
        "format": PACKAGE_FORMAT,
        "format_version": FORMAT_VERSION,
        "package_id": address.package_id,
        "project_id": address.project_id,
        "motion_id": address.motion_id,
        "clip_id": address.clip_id,
        "motion_policy_package_id": address.motion_policy_package_id,
        "p9_decision_sha256": address.p9_decision_sha256,
        "status": (
            "ready_for_candidate_replay"
            if record.current else "stale_for_current_project"
        ),
    }


def _resolved_addresses(
    state_root: Path,
    allowed: set[str] | None,
    current_project_chains: Mapping[str, CurrentProjectChain] | None,
) -> tuple[list[_ResolvedAddress], int]:
    try:
        policy_inventory = list_motion_policy_review_packages(state_root)
        runs, skipped_runs = _adopted_runs(state_root, allowed)
        result = []
        for package in policy_inventory["packages"]:
            if allowed is not None and package["project_id"] not in allowed:
                continue
            for run in runs:
                if _matches(package, run):
                    address = IdleBehaviorReviewAddress(
                        package["package_id"], run.project_id,
                        package["motion_id"], run.clip_id,
                        run.motion_instance_v2_sha256, run.bundle_sha256,
                        run.decision_sha256,
                    )
                    result.append(_ResolvedAddress(
                        address,
                        chain_is_current(
                            run.project_id,
                            run.resolved_project_sha256,
                            run.layer_manifest_sha256,
                            current_project_chains,
                        ),
                    ))
        return result, policy_inventory.get("skipped_count", 0) + skipped_runs
    except IdleBehaviorReviewPackageError:
        raise
    except (
        KeyError, MotionPolicyReviewPackageError, OSError, TypeError,
        ValueError,
    ) as exc:
        raise IdleBehaviorReviewPackageError(
            "Idle behavior review package addresses could not be resolved"
        ) from exc


def _matches(package: Mapping[str, Any], run: AdoptedRun) -> bool:
    identities = package.get("identities")
    return isinstance(identities, Mapping) \
        and package.get("project_id") == run.project_id \
        and package.get("clip_id") == run.clip_id \
        and identities.get("foot_candidates_sha256") == run.foot_sha256 \
        and identities.get("depth_candidates_sha256") == run.depth_sha256


def _recommended(rows: list[dict[str, Any]]) -> str | None:
    rows = [
        row for row in rows
        if row["status"] == "ready_for_candidate_replay"
    ]
    if not rows:
        return None
    groups: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["project_id"], row["clip_id"])
        groups[key] = groups.get(key, 0) + 1
    if any(count > 1 for count in groups.values()):
        return None
    return rows[0]["package_id"]


def _adopted_runs(
    state_root: Path, allowed: set[str] | None,
) -> tuple[list[AdoptedRun], int]:
    """Compatibility wrapper around the bounded adopted-run inventory."""
    try:
        return list_adopted_runs(state_root, allowed)
    except AdoptedRunInventoryError as exc:
        raise IdleBehaviorReviewPackageError(
            "Adopted P9 package inventory could not be inspected"
        ) from exc
