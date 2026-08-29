"""Read-only P9-package handoff into one exact seam review."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .http_json_request import decode_json_object
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    get_motion_policy_review_package,
)
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_application import (
    SeamAnchorReviewApplication,
    SeamAnchorReviewApplicationError,
)


FORMAT = "autospine-seam-review-entry"
FORMAT_VERSION = 1
MANUAL_REVIEW_REQUIRED = "manual_review_required"
BLOCKED_UNOBSERVABLE = "blocked_unobservable"


class MotionPolicySeamReviewEntryError(RuntimeError):
    """Raised when an exact P9 package cannot safely enter seam review."""


class MotionPolicySeamReviewEntryNotFoundError(
    MotionPolicySeamReviewEntryError
):
    """Raised when the requested content-addressed package is unavailable."""


def build_motion_policy_seam_review_entry(
    state_root: Path,
    package_id: str,
) -> dict[str, Any]:
    """Replay authoritative P3 inputs and return a path-free review entry."""

    try:
        package = get_motion_policy_review_package(state_root, package_id)
    except MotionPolicyReviewPackageError as exc:
        raise MotionPolicySeamReviewEntryNotFoundError(
            "The exact motion-policy package is unavailable"
        ) from exc
    try:
        foot = _package_document(package, "foot_candidates_json")
        depth = _package_document(package, "depth_candidates_json")
        project_id, p3 = _require_shared_p3(package, foot, depth)
        mesh = VerifiedMeshBundleReader(state_root).load(
            project_id, p3["rig_sha256"], p3["bundle_sha256"],
        )
        if mesh.layer_manifest_sha256 != p3["layer_manifest_sha256"]:
            raise MotionPolicySeamReviewEntryError(
                "Package and verified P3 Layer Manifest differ"
            )
        address = ExactSeamAnchorReviewAddress(
            project_id=project_id,
            layer_manifest_sha256=mesh.layer_manifest_sha256,
            p3_rig_sha256=mesh.rig_sha256,
            p3_bundle_sha256=mesh.bundle_sha256,
        )
        prepared = SeamAnchorReviewApplication(state_root).prepare(address)
        return _entry(package, address, prepared)
    except MotionPolicySeamReviewEntryError:
        raise
    except (
        ExactSeamAnchorReviewAddressError,
        KeyError,
        OSError,
        SeamAnchorReviewApplicationError,
        TypeError,
        UnicodeError,
        ValueError,
        VerifiedMeshBundleReaderError,
    ) as exc:
        raise MotionPolicySeamReviewEntryError(
            "The exact seam-review entry could not be replayed"
        ) from exc


def _package_document(package: Mapping[str, Any], field: str) -> dict[str, Any]:
    value = package.get(field)
    if not isinstance(value, str):
        raise MotionPolicySeamReviewEntryError(
            "The exact motion-policy package is incomplete"
        )
    return decode_json_object(value.encode("utf-8"))


def _require_shared_p3(package, foot, depth):
    project_id = package.get("project_id")
    clip_id = package.get("clip_id")
    foot_source = foot.get("source")
    depth_source = depth.get("source")
    if not isinstance(foot_source, Mapping) \
            or not isinstance(depth_source, Mapping):
        raise MotionPolicySeamReviewEntryError(
            "Motion-policy package source is incomplete"
        )
    p3 = depth_source.get("p3")
    if not isinstance(p3, Mapping) \
            or foot.get("project_id") != project_id \
            or depth.get("project_id") != project_id \
            or foot.get("clip_id") != clip_id \
            or depth.get("clip_id") != clip_id \
            or foot_source.get("p3_rig_sha256") != p3.get("rig_sha256") \
            or foot_source.get("p3_bundle_sha256") != p3.get("bundle_sha256"):
        raise MotionPolicySeamReviewEntryError(
            "Motion-policy package P3 sources differ"
        )
    return project_id, p3


def _entry(package, address, prepared):
    candidate = prepared.candidate_document
    relationships = candidate.get("relationships")
    summary = candidate.get("summary")
    if not isinstance(relationships, list) or not isinstance(summary, Mapping):
        raise MotionPolicySeamReviewEntryError(
            "Seam candidate summary is incomplete"
        )
    blockers = [{
        "relationship_id": row["relationship_id"],
        "reason_codes": list(row["reason_codes"]),
    } for row in relationships if row.get("status") == "unobservable"]
    if len(relationships) != 6 \
            or len(blockers) != summary.get("unobservable_count") \
            or summary.get("relationship_count") != 6 \
            or summary.get("review_required_count") + len(blockers) != 6:
        raise MotionPolicySeamReviewEntryError(
            "Seam candidate observability summary is inconsistent"
        )
    status = BLOCKED_UNOBSERVABLE if blockers else MANUAL_REVIEW_REQUIRED
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "package_id": package["package_id"],
        "project_id": package["project_id"],
        "address": address.public_document(),
        "candidate_sha256": prepared.candidate_sha256,
        "status": status,
        "summary": {
            "relationship_count": 6,
            "review_required_count": summary["review_required_count"],
            "unobservable_count": summary["unobservable_count"],
        },
        "blocking_relationships": blockers,
    }
