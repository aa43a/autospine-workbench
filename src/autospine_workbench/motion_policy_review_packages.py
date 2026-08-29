"""Discover validated local P9 review packages for the automated UI."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .bounded_review_evidence import (
    BoundedReviewEvidenceError,
    path_is_linklike,
    read_bounded_text,
    require_real_directory,
)
from .depth_order_candidate_validation import (
    FORMAT as DEPTH_FORMAT,
    depth_order_candidates_sha256,
)
from .depth_pair_policy import depth_pair_policy_sha256
from .foot_lock_candidate_validation import (
    FORMAT as FOOT_FORMAT,
    foot_lock_candidates_sha256,
)
from .http_json_request import decode_json_object
from .motion_policy_preflight import (
    CANDIDATE_INVENTORY,
    REQUEST_FORMAT,
    compile_motion_policy_preflight,
)


LIST_FORMAT = "autospine-motion-policy-package-list"
PACKAGE_FORMAT = "autospine-motion-policy-review-package"
FORMAT_VERSION = 1
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ENVELOPE_FIELDS = {
    "input_bundle_paths", "report_sha256", "report", "ok", "status",
}
_POLICY_FILE = "depth-pair-policy.json"
_FOOT_FILES = ("foot-lock-candidates.envelope.json", "foot-lock-candidates.json")
_DEPTH_FILES = ("depth-order-candidates.envelope.json", "depth-order-candidates.json")
_MAX_POLICY_BYTES = 1024 * 1024
_MAX_CANDIDATE_BYTES = 16 * 1024 * 1024


class MotionPolicyReviewPackageError(ValueError):
    """Raised when an on-disk automatic review package is unsafe or stale."""


def list_motion_policy_review_packages(state_root: Path) -> dict[str, Any]:
    """Return deterministic summaries for every strictly valid local package."""

    rows = []
    skipped = 0
    for directory in _package_directories(state_root):
        try:
            rows.append(_load_package(directory, include_documents=False))
        except ValueError:
            skipped += 1
    rows.sort(key=lambda row: (row["project_id"], row["motion_id"]))
    preferred = rows[0]["package_id"] if rows else None
    return {
        "format": LIST_FORMAT,
        "format_version": FORMAT_VERSION,
        "count": len(rows),
        "skipped_count": skipped,
        "recommended_package_id": preferred,
        "packages": rows,
    }


def get_motion_policy_review_package(
    state_root: Path, package_id: str,
) -> dict[str, Any]:
    """Return one exact package selected by its evidence-bound identity."""

    if not isinstance(package_id, str) or not _SHA.fullmatch(package_id):
        raise MotionPolicyReviewPackageError("package_id is invalid")
    for directory in _package_directories(state_root):
        try:
            package = _load_package(directory, include_documents=True)
        except ValueError:
            continue
        if package["package_id"] == package_id:
            return package
    raise MotionPolicyReviewPackageError(
        "No validated automatic review package has this identity"
    )


def _package_directories(state_root: Path) -> list[Path]:
    state = Path(state_root)
    if _is_linklike(state):
        raise MotionPolicyReviewPackageError(
            "Automatic review package root is unsafe"
        )
    root = state.resolve() / "reviews"
    try:
        root.lstat()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise MotionPolicyReviewPackageError(
            "Automatic review package inventory is unreadable"
        ) from exc
    _require_real_directory(root)
    result = []
    try:
        motions = sorted(root.iterdir())
        for motion in motions:
            if _is_linklike(motion):
                raise MotionPolicyReviewPackageError(
                    "Automatic review package inventory contains a link"
                )
            if not motion.is_dir():
                continue
            if not _ID.fullmatch(motion.name):
                continue
            for path in sorted(motion.iterdir()):
                if _is_linklike(path):
                    raise MotionPolicyReviewPackageError(
                        "Automatic review package inventory contains a link"
                    )
                if path.is_dir() and _ID.fullmatch(path.name) \
                        and path.name != "shared":
                    result.append(path)
    except OSError as exc:
        raise MotionPolicyReviewPackageError(
            "Automatic review package inventory is unreadable"
        ) from exc
    return result


def _load_package(directory: Path, *, include_documents: bool) -> dict[str, Any]:
    _require_real_directory(directory)
    _require_real_directory(directory.parent)
    _require_real_directory(directory.parent.parent)
    project_id = _identifier(directory.name, "project_id")
    motion_id = _identifier(directory.parent.name, "motion_id")
    policy_text = _read_text(
        directory / _POLICY_FILE, _MAX_POLICY_BYTES, directory,
    )
    foot_text = _read_first(directory, _FOOT_FILES, _MAX_CANDIDATE_BYTES)
    depth_text = _read_first(directory, _DEPTH_FILES, _MAX_CANDIDATE_BYTES)
    policy = _object(policy_text, "policy")
    foot, foot_envelope_sha = _candidate_report(
        _object(foot_text, "foot candidates"), FOOT_FORMAT,
    )
    depth, depth_envelope_sha = _candidate_report(
        _object(depth_text, "depth candidates"), DEPTH_FORMAT,
    )
    canonical_foot = _json_text(foot)
    canonical_depth = _json_text(depth)
    identities = {
        "policy_sha256": depth_pair_policy_sha256(policy),
        "foot_candidates_sha256": foot_lock_candidates_sha256(foot),
        "depth_candidates_sha256": depth_order_candidates_sha256(depth),
    }
    if foot_envelope_sha not in {None, identities["foot_candidates_sha256"]} \
            or depth_envelope_sha not in {
                None, identities["depth_candidates_sha256"],
            }:
        raise MotionPolicyReviewPackageError(
            "Candidate envelope identity differs from canonical report"
        )
    try:
        result = compile_motion_policy_preflight({
            "format": REQUEST_FORMAT,
            "format_version": FORMAT_VERSION,
            "operation": CANDIDATE_INVENTORY,
            "policy_json": policy_text,
            "foot_candidates_json": canonical_foot,
            "depth_candidates_json": canonical_depth,
            "declared": identities,
        })
    except (TypeError, ValueError) as exc:
        raise MotionPolicyReviewPackageError(
            "Review evidence failed semantic validation"
        ) from exc
    if result["project_id"] != project_id:
        raise MotionPolicyReviewPackageError(
            "Review directory and candidate project identities differ"
        )
    package_id = _package_id(
        project_id, motion_id, result["clip_id"], identities,
        result["inventory"]["candidate_ids_sha256"],
    )
    package = {
        "format": PACKAGE_FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": project_id,
        "package_id": package_id,
        "motion_id": motion_id,
        "clip_id": result["clip_id"],
        "identities": identities,
        "inventory": result["inventory"],
        "automation_profile": "safe-assist-v1",
    }
    if include_documents:
        package.update({
            "policy_json": policy_text,
            "foot_candidates_json": canonical_foot,
            "depth_candidates_json": canonical_depth,
        })
    return package


def _read_first(directory: Path, names: tuple[str, ...], maximum: int) -> str:
    for name in names:
        path = directory / name
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MotionPolicyReviewPackageError(
                "Review evidence is unreadable"
            ) from exc
        return _read_text(path, maximum, directory)
    raise MotionPolicyReviewPackageError("Required review evidence is missing")


def _read_text(path: Path, maximum: int, root: Path) -> str:
    try:
        return read_bounded_text(path, maximum, root)
    except BoundedReviewEvidenceError as exc:
        raise MotionPolicyReviewPackageError(str(exc)) from exc


def _require_real_directory(path: Path) -> None:
    try:
        require_real_directory(path)
    except BoundedReviewEvidenceError as exc:
        raise MotionPolicyReviewPackageError(str(exc)) from exc


def _is_linklike(path: Path) -> bool:
    try:
        return path_is_linklike(path)
    except BoundedReviewEvidenceError as exc:
        raise MotionPolicyReviewPackageError(str(exc)) from exc


def _candidate_report(
    value: Mapping[str, Any], expected: str,
) -> tuple[Mapping[str, Any], str | None]:
    if value.get("format") == expected:
        return value, None
    if set(value) != _ENVELOPE_FIELDS or value.get("ok") is not True \
            or value.get("status") != "passed":
        raise MotionPolicyReviewPackageError("Candidate envelope is invalid")
    report = value.get("report")
    if not isinstance(report, Mapping) or report.get("format") != expected:
        raise MotionPolicyReviewPackageError("Candidate envelope report is invalid")
    envelope_sha = value.get("report_sha256")
    if not isinstance(envelope_sha, str) or not _SHA.fullmatch(envelope_sha):
        raise MotionPolicyReviewPackageError("Candidate envelope SHA is invalid")
    return report, envelope_sha


def _package_id(
    project_id: str, motion_id: str, clip_id: str,
    identities: Mapping[str, str], candidate_ids_sha256: str,
) -> str:
    value = json.dumps({
        "domain": "autospine-motion-policy-review-package-id/v1",
        "project_id": project_id,
        "motion_id": motion_id,
        "clip_id": clip_id,
        "identities": dict(identities),
        "candidate_ids_sha256": candidate_ids_sha256,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _object(text: str, label: str) -> Mapping[str, Any]:
    try:
        return decode_json_object(text.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise MotionPolicyReviewPackageError(f"{label} JSON is invalid") from exc


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"),
    )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise MotionPolicyReviewPackageError(f"{label} is invalid")
    return value
