"""Discover exact adopted P9 runs without exposing filesystem paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import stat

from .idle_behavior_review_profile import MAX_PACKAGES
from .idle_behavior_review_replay_cache import (
    IdleBehaviorReviewReplayCacheError,
    load_cached_reviewed_motion_chain,
)
from .reviewed_motion_bundle_files import is_alias
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)


_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = "reviewed-motion-instances"


class AdoptedRunInventoryError(RuntimeError):
    """Raised when the adopted-run hierarchy cannot be read safely."""


@dataclass(frozen=True, slots=True)
class AdoptedRun:
    """Immutable identities required to align P9 with current authoring."""

    project_id: str
    clip_id: str
    motion_instance_v2_sha256: str
    bundle_sha256: str
    foot_sha256: str
    depth_sha256: str
    decision_sha256: str
    resolved_project_sha256: str
    layer_manifest_sha256: str


def list_adopted_runs(
    state_root: Path,
    allowed: set[str] | None,
) -> tuple[list[AdoptedRun], int]:
    """Return replay-verified runs and a count of rejected entries."""

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
                    result.append(_load_run(
                        state_root, project.name,
                        instance.name, bundle.name,
                    ))
                except (AdoptedRunInventoryError, OSError, ValueError):
                    skipped += 1
                if len(result) > MAX_PACKAGES:
                    raise AdoptedRunInventoryError(
                        "Adopted P9 package count exceeds its limit"
                    )
    return result, skipped


def _load_run(
    state_root: Path,
    project_id: str,
    instance_sha: str,
    bundle_sha: str,
) -> AdoptedRun:
    """Admit only a complete bundle replayed from its exact P3/P5 chain."""

    try:
        reader = VerifiedReviewedMotionBundleReader(state_root)
        chain = load_cached_reviewed_motion_chain(
            state_root, project_id, instance_sha, bundle_sha,
            lambda: reader.load_chain(
                project_id, instance_sha, bundle_sha,
            ),
        )
        verified = chain.reviewed_bundle
        return AdoptedRun(
            verified.project_id,
            verified.clip_id,
            verified.motion_instance_v2_sha256,
            verified.bundle_sha256,
            verified.foot_lock_candidates_sha256,
            verified.depth_order_candidates_sha256,
            verified.motion_policy_decision_sha256,
            chain.mesh_bundle.resolved_project_sha256,
            chain.mesh_bundle.layer_manifest_sha256,
        )
    except (
        IdleBehaviorReviewReplayCacheError,
        VerifiedReviewedMotionBundleReaderError,
    ) as exc:
        raise AdoptedRunInventoryError(
            "Adopted P9 bundle failed exact replay"
        ) from exc


def _optional_child(parent: Path, name: str) -> Path | None:
    matches = [
        item for item in _children(parent)
        if item.name.casefold() == name.casefold()
    ]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name:
        raise AdoptedRunInventoryError(
            "Idle review hierarchy contains a case alias"
        )
    return _real_directory(matches[0], name)


def _children(directory: Path) -> list[Path]:
    directory = _real_directory(directory, "Idle review directory")
    try:
        items = list(directory.iterdir())
    except OSError as exc:
        raise AdoptedRunInventoryError(
            "Idle review hierarchy cannot be enumerated"
        ) from exc
    folded = [item.name.casefold() for item in items]
    if len(folded) != len(set(folded)):
        raise AdoptedRunInventoryError(
            "Idle review hierarchy contains case aliases"
        )
    return items


def _real_directory(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
        if is_alias(path) or not stat.S_ISDIR(metadata.st_mode):
            raise AdoptedRunInventoryError(f"{label} is unsafe")
    except OSError as exc:
        raise AdoptedRunInventoryError(f"{label} is unavailable") from exc
    return path
