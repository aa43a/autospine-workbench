"""Resolve adopted P9 bundles into path-free P10 idle-review packages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import stat
from typing import Any

from .idle_behavior_review_address import IdleBehaviorReviewAddress
from .idle_behavior_review_profile import (
    FORMAT_VERSION,
    LIST_FORMAT,
    MAX_PACKAGES,
    PACKAGE_FORMAT,
)
from .idle_behavior_review_replay_cache import (
    IdleBehaviorReviewReplayCacheError,
    load_cached_reviewed_motion_chain,
)
from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    list_motion_policy_review_packages,
)
from .reviewed_motion_bundle_files import is_alias
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)


_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = "reviewed-motion-instances"


class IdleBehaviorReviewPackageError(RuntimeError):
    """Raised when adopted P9 package inventory cannot be inspected safely."""


@dataclass(frozen=True, slots=True)
class _AdoptedRun:
    project_id: str
    clip_id: str
    motion_instance_v2_sha256: str
    bundle_sha256: str
    foot_sha256: str
    depth_sha256: str
    decision_sha256: str


def list_idle_behavior_review_packages(
    state_root: Path,
    *,
    project_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Match validated review packages to every exact adopted P9 bundle."""

    try:
        allowed = set(project_ids) if project_ids is not None else None
        addresses, skipped = _resolved_addresses(state_root, allowed)
        rows = [_summary(address) for address in addresses]
        rows.sort(key=lambda row: (
            row["project_id"], row["motion_id"],
            row["p9_decision_sha256"], row["package_id"],
        ))
        if len(rows) > MAX_PACKAGES:
            raise IdleBehaviorReviewPackageError(
                "Idle behavior review package count exceeds its limit"
            )
        recommended = _recommended(rows)
        return {
            "format": LIST_FORMAT,
            "format_version": FORMAT_VERSION,
            "count": len(rows),
            "skipped_count": (
                skipped
            ),
            "recommended_package_id": recommended,
            "packages": rows,
        }
    except IdleBehaviorReviewPackageError:
        raise
    except (
        KeyError, MotionPolicyReviewPackageError, OSError, TypeError,
        ValueError,
    ) as exc:
        raise IdleBehaviorReviewPackageError(
            "Idle behavior review packages could not be resolved"
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
    addresses, _skipped = _resolved_addresses(state_root, allowed)
    matches = [row for row in addresses if row.package_id == package_id]
    if len(matches) != 1:
        raise IdleBehaviorReviewPackageError(
            "The exact idle behavior review package is unavailable"
        )
    return matches[0]


def _summary(address: IdleBehaviorReviewAddress) -> dict[str, Any]:
    return {
        "format": PACKAGE_FORMAT,
        "format_version": FORMAT_VERSION,
        "package_id": address.package_id,
        "project_id": address.project_id,
        "motion_id": address.motion_id,
        "clip_id": address.clip_id,
        "motion_policy_package_id": address.motion_policy_package_id,
        "p9_decision_sha256": address.p9_decision_sha256,
        "status": "ready_for_candidate_replay",
    }


def _resolved_addresses(
    state_root: Path, allowed: set[str] | None,
) -> tuple[list[IdleBehaviorReviewAddress], int]:
    policy_inventory = list_motion_policy_review_packages(state_root)
    runs, skipped_runs = _adopted_runs(state_root, allowed)
    result = []
    for package in policy_inventory["packages"]:
        if allowed is not None and package["project_id"] not in allowed:
            continue
        for run in runs:
            if _matches(package, run):
                result.append(IdleBehaviorReviewAddress(
                    package["package_id"], run.project_id,
                    package["motion_id"], run.clip_id,
                    run.motion_instance_v2_sha256, run.bundle_sha256,
                    run.decision_sha256,
                ))
    return result, policy_inventory.get("skipped_count", 0) + skipped_runs


def _matches(package: Mapping[str, Any], run: _AdoptedRun) -> bool:
    identities = package.get("identities")
    return isinstance(identities, Mapping) \
        and package.get("project_id") == run.project_id \
        and package.get("clip_id") == run.clip_id \
        and identities.get("foot_candidates_sha256") == run.foot_sha256 \
        and identities.get("depth_candidates_sha256") == run.depth_sha256


def _recommended(rows: list[dict[str, Any]]) -> str | None:
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
) -> tuple[list[_AdoptedRun], int]:
    root = _real_directory(Path(state_root), "Idle review state root")
    builds = _optional_child(root, "builds")
    if builds is None:
        return [], 0
    result, skipped = [], 0
    for project in _children(builds):
        if allowed is not None and project.name not in allowed:
            continue
        namespace = _optional_child(project, _NAMESPACE)
        if namespace is None:
            continue
        for instance in _children(namespace):
            if not _SHA.fullmatch(instance.name):
                skipped += 1
                continue
            for bundle in _children(instance):
                if not _SHA.fullmatch(bundle.name):
                    skipped += 1
                    continue
                try:
                    result.append(_run(
                        state_root, project.name,
                        instance.name, bundle.name,
                    ))
                except (IdleBehaviorReviewPackageError, OSError, ValueError):
                    skipped += 1
                if len(result) > MAX_PACKAGES:
                    raise IdleBehaviorReviewPackageError(
                        "Adopted P9 package count exceeds its limit"
                    )
    return result, skipped


def _run(
    state_root: Path, project_id: str,
    instance_sha: str, bundle_sha: str,
) -> _AdoptedRun:
    """Admit only a complete six-file bundle replayed from exact P3/P5."""

    try:
        reader = VerifiedReviewedMotionBundleReader(state_root)
        chain = load_cached_reviewed_motion_chain(
            state_root, project_id, instance_sha, bundle_sha,
            lambda: reader.load_chain(
                project_id, instance_sha, bundle_sha,
            ),
        )
        verified = chain.reviewed_bundle
        return _AdoptedRun(
            verified.project_id, verified.clip_id,
            verified.motion_instance_v2_sha256, verified.bundle_sha256,
            verified.foot_lock_candidates_sha256,
            verified.depth_order_candidates_sha256,
            verified.motion_policy_decision_sha256,
        )
    except (
        IdleBehaviorReviewReplayCacheError,
        VerifiedReviewedMotionBundleReaderError,
    ) as exc:
        raise IdleBehaviorReviewPackageError(
            "Adopted P9 bundle failed exact replay"
        ) from exc


def _optional_child(parent: Path, name: str) -> Path | None:
    matches = [item for item in _children(parent)
               if item.name.casefold() == name.casefold()]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name:
        raise IdleBehaviorReviewPackageError(
            "Idle review hierarchy contains a case alias"
        )
    return _real_directory(matches[0], name)


def _children(directory: Path) -> list[Path]:
    directory = _real_directory(directory, "Idle review directory")
    try:
        items = list(directory.iterdir())
    except OSError as exc:
        raise IdleBehaviorReviewPackageError(
            "Idle review hierarchy cannot be enumerated"
        ) from exc
    folded = [item.name.casefold() for item in items]
    if len(folded) != len(set(folded)):
        raise IdleBehaviorReviewPackageError(
            "Idle review hierarchy contains case aliases"
        )
    return items


def _real_directory(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
        if is_alias(path) or not stat.S_ISDIR(metadata.st_mode):
            raise IdleBehaviorReviewPackageError(f"{label} is unsafe")
    except OSError as exc:
        raise IdleBehaviorReviewPackageError(f"{label} is unavailable") from exc
    return path
