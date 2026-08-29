"""Exact P9 adoption from one validated local review package."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any

from .http_json_request import HttpJsonRequestError, decode_json_object
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .motion_instance_v2_compiler import (
    MotionInstanceV2CompilerError,
    compile_motion_instance_v2,
)
from .motion_policy_decision import (
    MotionPolicyDecisionError,
    build_motion_policy_decision,
)
from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    get_motion_policy_review_package,
)
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .reviewed_motion_bundle_store import (
    ReviewedMotionBundleStore,
    ReviewedMotionBundleStoreError,
)
from .reviewed_motion_policy import (
    ReviewedMotionPolicyError,
    compile_reviewed_motion_policy,
)


REQUEST_FORMAT = "autospine-motion-policy-adoption-request"
RECEIPT_FORMAT = "autospine-motion-policy-adoption-receipt"
FORMAT_VERSION = 1
INTENT_VALUE = "motion-policy-adoption-v1"
_REQUEST_FIELDS = {
    "format", "format_version", "intent", "package_id", "review_input",
}
_REVIEW_FIELDS = {
    "review", "decisions", "root_release_keys", "draw_order_loop_reset",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")


class MotionPolicyAdoptionError(ValueError):
    """Raised when a human adoption request is structurally invalid."""


class MotionPolicyAdoptionPackageNotFoundError(MotionPolicyAdoptionError):
    """Raised when the requested exact package is no longer available."""


class MotionPolicyAdoptionUnavailableError(RuntimeError):
    """Raised when exact upstreams cannot safely publish or replay P9."""


def adopt_motion_policy_package(
    state_root: Path,
    package_id: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish and replay one explicit human adoption without path inputs."""

    requested_id, review = _require_request(package_id, request)
    try:
        package = get_motion_policy_review_package(state_root, requested_id)
    except MotionPolicyReviewPackageError as exc:
        raise MotionPolicyAdoptionPackageNotFoundError(
            "The exact motion-policy package is unavailable"
        ) from exc
    foot = _package_document(package, "foot_candidates_json")
    depth = _package_document(package, "depth_candidates_json")
    try:
        decision = build_motion_policy_decision(
            foot,
            depth,
            review=review["review"],
            decisions=review["decisions"],
            root_release_keys=review["root_release_keys"],
            draw_order_loop_reset=review["draw_order_loop_reset"],
        )
    except (KeyError, MotionPolicyDecisionError, TypeError, ValueError) as exc:
        raise MotionPolicyAdoptionError(
            "The human motion-policy review input is invalid"
        ) from exc
    try:
        project_id = package["project_id"]
        source = foot["source"]
        mesh = VerifiedMeshBundleReader(state_root).load(
            project_id,
            source["p3_rig_sha256"],
            source["p3_bundle_sha256"],
        )
        retarget = VerifiedMotionRetargetBundleReader(state_root).load(
            project_id,
            source["motion_instance_sha256"],
            source["retarget_bundle_sha256"],
        )
        policy = compile_reviewed_motion_policy(
            decision.document, foot, depth, mesh,
        )
        motion_v2 = compile_motion_instance_v2(
            retarget.motion_instance, retarget.target_profile, policy.document,
        )
        published = ReviewedMotionBundleStore(state_root).publish(
            project_id, foot, depth, decision.document, policy.document,
            motion_v2.document, mesh, retarget,
        )
        verified = VerifiedReviewedMotionBundleReader(state_root).load(
            project_id,
            published.motion_instance_v2_sha256,
            published.bundle_sha256,
            mesh_bundle=mesh,
            retarget_bundle=retarget,
        )
        _require_verified(package, published, verified)
    except (
        KeyError,
        MotionInstanceV2CompilerError,
        ReviewedMotionBundleStoreError,
        ReviewedMotionPolicyError,
        TypeError,
        ValueError,
        VerifiedMeshBundleReaderError,
        VerifiedMotionRetargetBundleReaderError,
        VerifiedReviewedMotionBundleReaderError,
    ) as exc:
        raise MotionPolicyAdoptionUnavailableError(
            "The exact motion-policy package could not be published"
        ) from exc
    return _receipt(package, published, verified)


def _require_request(
    path_package_id: str, request: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    if not isinstance(request, Mapping) or set(request) != _REQUEST_FIELDS:
        raise MotionPolicyAdoptionError("Adoption request fields are invalid")
    package_id = request.get("package_id")
    if not isinstance(path_package_id, str) or not _SHA.fullmatch(path_package_id) \
            or package_id != path_package_id:
        raise MotionPolicyAdoptionError("Adoption package identity is invalid")
    if request.get("format") != REQUEST_FORMAT \
            or type(request.get("format_version")) is not int \
            or request.get("format_version") != FORMAT_VERSION \
            or request.get("intent") != INTENT_VALUE:
        raise MotionPolicyAdoptionError("Adoption request contract is invalid")
    review = request.get("review_input")
    if not isinstance(review, Mapping) or set(review) != _REVIEW_FIELDS:
        raise MotionPolicyAdoptionError("Adoption review fields are invalid")
    return package_id, review


def _package_document(package: Mapping[str, Any], field: str) -> dict[str, Any]:
    value = package.get(field)
    if not isinstance(value, str):
        raise MotionPolicyAdoptionUnavailableError(
            "The exact motion-policy package is incomplete"
        )
    try:
        return decode_json_object(value.encode("utf-8"))
    except (HttpJsonRequestError, UnicodeError, ValueError) as exc:
        raise MotionPolicyAdoptionUnavailableError(
            "The exact motion-policy package is invalid"
        ) from exc


def _require_verified(package, published, verified) -> None:
    if verified.project_id != package["project_id"] \
            or verified.clip_id != package["clip_id"] \
            or verified.motion_instance_v2_sha256 != \
            published.motion_instance_v2_sha256 \
            or verified.bundle_sha256 != published.bundle_sha256 \
            or verified.identities["foot_lock_candidates_sha256"] != \
            package["identities"]["foot_candidates_sha256"] \
            or verified.identities["depth_order_candidates_sha256"] != \
            package["identities"]["depth_candidates_sha256"]:
        raise MotionPolicyAdoptionUnavailableError(
            "Published P9 evidence differs from the selected package"
        )


def _receipt(package, published, verified) -> dict[str, Any]:
    identities = dict(verified.identities)
    identities.update({
        "depth_pair_policy_sha256": package["identities"]["policy_sha256"],
        "candidate_ids_sha256": package["inventory"][
            "candidate_ids_sha256"
        ],
    })
    return {
        "format": RECEIPT_FORMAT,
        "format_version": FORMAT_VERSION,
        "status": "passed",
        "package_id": package["package_id"],
        "project_id": package["project_id"],
        "motion_id": package["motion_id"],
        "clip_id": package["clip_id"],
        "reused": published.reused,
        "address": {
            "project_id": verified.project_id,
            "motion_instance_v2_sha256": verified.motion_instance_v2_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "verification": {
            "status": "passed",
            "replayed_from_exact_upstreams": True,
        },
        "identities": identities,
    }
