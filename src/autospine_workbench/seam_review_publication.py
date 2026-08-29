"""Package-bound P10.5c publication from one current P10.5b decision."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any

from .motion_policy_seam_review_entry import (
    MANUAL_REVIEW_REQUIRED,
    MotionPolicySeamReviewEntryError,
    MotionPolicySeamReviewEntryNotFoundError,
    build_motion_policy_seam_review_entry,
)
from .reviewed_seam_anchor_set_commands import (
    ReviewedSeamAnchorSetCommandError,
    compile_reviewed_seam_anchor_set_command,
    verify_reviewed_seam_anchor_set_command,
)
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_application import (
    SeamAnchorReviewApplication,
    SeamAnchorReviewApplicationError,
)
from .seam_review_publication_records import (
    SeamReviewPublicationRecordError,
    load_seam_review_publication_record,
    publish_seam_review_publication_record,
)


REQUEST_FORMAT = "autospine-seam-review-publication-request"
RECEIPT_FORMAT = "autospine-reviewed-seam-anchor-set-receipt"
FORMAT_VERSION = 1
INTENT_VALUE = "reviewed-seam-anchor-set-publication-v1"
_FIELDS = {
    "format", "format_version", "intent", "package_id",
    "candidate_sha256", "review_revision", "decision_sha256",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SeamReviewPublicationError(ValueError):
    """Raised when a P10.5c publication request is invalid."""


class SeamReviewPublicationPackageNotFoundError(SeamReviewPublicationError):
    """Raised when the exact P9 package cannot be replayed."""


class SeamReviewPublicationUnavailableError(RuntimeError):
    """Raised when the current review head cannot safely publish P10.5c."""


def publish_seam_review_package(
    state_root: Path, package_id: str, request: Mapping[str, Any],
) -> dict[str, Any]:
    """Reload package evidence, publish the current ready head, and replay it."""

    requested = _require_request(package_id, request)
    try:
        entry = build_motion_policy_seam_review_entry(state_root, package_id)
    except MotionPolicySeamReviewEntryNotFoundError as exc:
        raise SeamReviewPublicationPackageNotFoundError(
            "The exact motion-policy package is unavailable"
        ) from exc
    except MotionPolicySeamReviewEntryError as exc:
        raise SeamReviewPublicationUnavailableError(
            "The seam-review package could not be replayed"
        ) from exc
    try:
        if entry["status"] != MANUAL_REVIEW_REQUIRED \
                or entry["blocking_relationships"] \
                or entry["candidate_sha256"] != requested["candidate_sha256"]:
            raise SeamReviewPublicationUnavailableError(
                "The seam-review package is not ready for publication"
            )
        address = ExactSeamAnchorReviewAddress(
            entry["project_id"],
            entry["address"]["layer_manifest_sha256"],
            entry["address"]["p3_rig_sha256"],
            entry["address"]["p3_bundle_sha256"],
        )
        reused = _replay_record(
            state_root, package_id, requested, address,
        )
        if reused is not None:
            return reused
        service = SeamAnchorReviewApplication(state_root)
        prepared = service.prepare(address)
        history = prepared.history
        if prepared.candidate_sha256 != requested["candidate_sha256"] \
                or history.current_revision != requested["review_revision"] \
                or history.head_decision_sha256 != requested["decision_sha256"]:
            raced = _replay_record(
                state_root, package_id, requested, address,
            )
            if raced is not None:
                return raced
            raise SeamReviewPublicationUnavailableError(
                "The requested seam-review decision is not the current head"
            )
        exact = service.exact_decision(
            address,
            candidate_sha256=requested["candidate_sha256"],
            revision=requested["review_revision"],
            decision_sha256=requested["decision_sha256"],
        )
        if exact.decision_document.get("status") != \
                "reviewed_anchor_set_ready_for_compile":
            raise SeamReviewPublicationUnavailableError(
                "The current seam-review decision is blocked"
            )
        compiled = compile_reviewed_seam_anchor_set_command(
            state_root, entry["project_id"],
            layer_manifest_sha256=address.layer_manifest_sha256,
            p3_rig_sha256=address.p3_rig_sha256,
            p3_bundle_sha256=address.p3_bundle_sha256,
            candidate_sha256=requested["candidate_sha256"],
            review_revision=requested["review_revision"],
            decision_sha256=requested["decision_sha256"],
        )
        verified = verify_reviewed_seam_anchor_set_command(
            state_root, entry["project_id"],
            reviewed_set_sha256=compiled.reviewed_set_sha256,
            bundle_sha256=compiled.bundle_sha256,
        )
        _require_same_result(compiled, verified)
        receipt = _receipt(package_id, compiled, verified)
        return publish_seam_review_publication_record(
            state_root, address.project_id, package_id, requested, receipt,
        )
    except SeamReviewPublicationUnavailableError:
        raise
    except (
        ExactSeamAnchorReviewAddressError,
        KeyError,
        ReviewedSeamAnchorSetCommandError,
        SeamAnchorReviewApplicationError,
        SeamReviewPublicationRecordError,
        TypeError,
        ValueError,
    ) as exc:
        raise SeamReviewPublicationUnavailableError(
            "The current seam-review decision could not be published"
        ) from exc


def _require_request(path_package_id, request):
    if not isinstance(request, Mapping) or set(request) != _FIELDS \
            or type(path_package_id) is not str \
            or _SHA256.fullmatch(path_package_id) is None \
            or request.get("package_id") != path_package_id \
            or request.get("format") != REQUEST_FORMAT \
            or type(request.get("format_version")) is not int \
            or request.get("format_version") != FORMAT_VERSION \
            or request.get("intent") != INTENT_VALUE:
        raise SeamReviewPublicationError("Publication request is invalid")
    if _SHA256.fullmatch(str(request.get("candidate_sha256"))) is None \
            or _SHA256.fullmatch(str(request.get("decision_sha256"))) is None \
            or type(request.get("review_revision")) is not int \
            or not 1 <= request["review_revision"] <= 64:
        raise SeamReviewPublicationError("Publication identity is invalid")
    return dict(request)


def _require_same_result(compiled, verified):
    fields = (
        "project_id", "layer_manifest_sha256", "p3_rig_sha256",
        "p3_bundle_sha256", "candidate_sha256", "decision_sha256",
        "review_revision", "reviewed_set_sha256", "bundle_sha256",
        "artifact_status", "relationship_count", "anchor_pair_count",
    )
    if any(getattr(compiled, field) != getattr(verified, field) for field in fields):
        raise SeamReviewPublicationUnavailableError(
            "Published reviewed seam-anchor evidence differs on replay"
        )


def _replay_record(state_root, package_id, requested, address):
    stored = load_seam_review_publication_record(
        state_root, address.project_id, package_id, requested,
    )
    if stored is None:
        return None
    try:
        output = stored["address"]
        verified = verify_reviewed_seam_anchor_set_command(
            state_root, address.project_id,
            reviewed_set_sha256=output["reviewed_set_sha256"],
            bundle_sha256=output["bundle_sha256"],
        )
        if (
            verified.layer_manifest_sha256 != address.layer_manifest_sha256
            or verified.p3_rig_sha256 != address.p3_rig_sha256
            or verified.p3_bundle_sha256 != address.p3_bundle_sha256
            or verified.candidate_sha256 != requested["candidate_sha256"]
            or verified.review_revision != requested["review_revision"]
            or verified.decision_sha256 != requested["decision_sha256"]
        ):
            raise SeamReviewPublicationUnavailableError(
                "Stored seam publication differs from its exact request"
            )
        expected = _receipt(
            package_id, verified, verified,
            head_observation=_compile_time_observation(requested),
        )
        if stored != expected:
            raise SeamReviewPublicationUnavailableError(
                "Stored seam publication receipt is invalid"
            )
        return stored
    except SeamReviewPublicationUnavailableError:
        raise
    except (KeyError, ReviewedSeamAnchorSetCommandError, TypeError) as exc:
        raise SeamReviewPublicationUnavailableError(
            "Stored seam publication could not be replayed"
        ) from exc


def _compile_time_observation(requested):
    return {
        "method": "double_snapshot",
        "scope": "compile_time",
        "revision": requested["review_revision"],
        "head_decision_sha256": requested["decision_sha256"],
        "permanent_authority_claimed": False,
    }


def _receipt(package_id, compiled, verified, *, head_observation=None):
    observation = compiled.head_observation \
        if head_observation is None else head_observation
    return {
        "format": RECEIPT_FORMAT,
        "format_version": FORMAT_VERSION,
        "status": "passed",
        "package_id": package_id,
        "source": {
            "project_id": compiled.project_id,
            "candidate_sha256": compiled.candidate_sha256,
            "review_revision": compiled.review_revision,
            "decision_sha256": compiled.decision_sha256,
        },
        "address": {
            "project_id": verified.project_id,
            "reviewed_set_sha256": verified.reviewed_set_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "verification": {
            "status": "passed",
            "replayed_from_exact_upstreams": True,
            "head_observation": observation,
        },
        "release_gate": {
            "status": compiled.release_gate_status,
            "reason_codes": list(compiled.release_gate_reason_codes),
        },
        "summary": {
            "relationship_count": compiled.relationship_count,
            "anchor_pair_count": compiled.anchor_pair_count,
        },
    }
