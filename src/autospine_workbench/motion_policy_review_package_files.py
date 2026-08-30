"""Bounded filesystem access for local P9 review packages."""

from __future__ import annotations

from pathlib import Path
import re

from .bounded_review_evidence import (
    BoundedReviewEvidenceError,
    path_is_linklike,
    read_bounded_text,
    require_real_directory,
)


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
POLICY_FILE = "depth-pair-policy.json"
FOOT_FILES = (
    "foot-lock-candidates.envelope.json",
    "foot-lock-candidates.json",
)
DEPTH_FILES = (
    "depth-order-candidates.envelope.json",
    "depth-order-candidates.json",
)
MAX_POLICY_BYTES = 1024 * 1024
MAX_CANDIDATE_BYTES = 16 * 1024 * 1024


class MotionPolicyReviewPackageFilesError(ValueError):
    """Raised when package files cannot be traversed or read safely."""


def package_directories(state_root: Path) -> list[Path]:
    """Return deterministic real package directories below ``reviews``."""

    state = Path(state_root)
    if is_linklike(state):
        raise MotionPolicyReviewPackageFilesError(
            "Automatic review package root is unsafe"
        )
    root = state.resolve() / "reviews"
    try:
        root.lstat()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise MotionPolicyReviewPackageFilesError(
            "Automatic review package inventory is unreadable"
        ) from exc
    require_directory(root)
    result = []
    try:
        for motion in sorted(root.iterdir()):
            if is_linklike(motion):
                raise MotionPolicyReviewPackageFilesError(
                    "Automatic review package inventory contains a link"
                )
            if not motion.is_dir() or not IDENTIFIER_PATTERN.fullmatch(
                motion.name
            ):
                continue
            for path in sorted(motion.iterdir()):
                if is_linklike(path):
                    raise MotionPolicyReviewPackageFilesError(
                        "Automatic review package inventory contains a link"
                    )
                if path.is_dir() and IDENTIFIER_PATTERN.fullmatch(path.name) \
                        and path.name != "shared":
                    result.append(path)
    except OSError as exc:
        raise MotionPolicyReviewPackageFilesError(
            "Automatic review package inventory is unreadable"
        ) from exc
    return result


def read_first(directory: Path, names: tuple[str, ...], maximum: int) -> str:
    """Read the first existing allowed evidence filename."""

    for name in names:
        path = directory / name
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MotionPolicyReviewPackageFilesError(
                "Review evidence is unreadable"
            ) from exc
        return read_text(path, maximum, directory)
    raise MotionPolicyReviewPackageFilesError(
        "Required review evidence is missing"
    )


def read_documents(directory: Path) -> tuple[str, str, str]:
    """Read the policy and both candidate reports from one package."""

    return (
        read_text(directory / POLICY_FILE, MAX_POLICY_BYTES, directory),
        read_first(directory, FOOT_FILES, MAX_CANDIDATE_BYTES),
        read_first(directory, DEPTH_FILES, MAX_CANDIDATE_BYTES),
    )


def read_text(path: Path, maximum: int, root: Path) -> str:
    """Read UTF-8 evidence without following links or escaping ``root``."""

    try:
        return read_bounded_text(path, maximum, root)
    except BoundedReviewEvidenceError as exc:
        raise MotionPolicyReviewPackageFilesError(str(exc)) from exc


def require_directory(path: Path) -> None:
    """Require a real, non-link directory."""

    try:
        require_real_directory(path)
    except BoundedReviewEvidenceError as exc:
        raise MotionPolicyReviewPackageFilesError(str(exc)) from exc


def is_linklike(path: Path) -> bool:
    """Return whether ``path`` is a symlink or Windows junction."""

    try:
        return path_is_linklike(path)
    except BoundedReviewEvidenceError as exc:
        raise MotionPolicyReviewPackageFilesError(str(exc)) from exc


__all__ = [
    "DEPTH_FILES",
    "FOOT_FILES",
    "IDENTIFIER_PATTERN",
    "MAX_CANDIDATE_BYTES",
    "MAX_POLICY_BYTES",
    "MotionPolicyReviewPackageFilesError",
    "POLICY_FILE",
    "is_linklike",
    "package_directories",
    "read_documents",
    "read_first",
    "read_text",
    "require_directory",
]
