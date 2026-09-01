"""Fast current-head verification for an exact persisted Preview v2 mount."""

from __future__ import annotations

import hashlib

from .capture_framing_verified_head import (
    CaptureFramingVerifiedHeadError, read_capture_framing_verified_head,
)
from .current_project_chain import CurrentProjectChainError
from .idle_behavior_review_head import (
    IdleBehaviorReviewHeadError, read_idle_behavior_review_head,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
)
from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError, get_motion_policy_review_package,
)
from .p10_preview_v2_cache import P10PreviewV2CacheRecord
from .p10_preview_v2_current_scope import (
    P10PreviewV2CurrentScopeError, current_p10_preview_v2_scope,
)
from .p10_preview_v2_service import _record_key
from .p10_preview_v2_upstream_address import (
    P10PreviewV2UpstreamAddressError,
    require_current_p10_preview_v2_upstreams,
)
from .project_store import ProjectStore, ProjectStoreError
from .reviewed_motion_bundle_contract import (
    ReviewedMotionBundleContractError,
    reviewed_motion_bundle_address_sha256,
)
from .reviewed_motion_bundle_files import (
    ReviewedMotionBundleFilesError, existing_bundle_path, read_bundle_files,
)
from .reviewed_motion_bundle_run import (
    ReviewedMotionBundleRunError, require_reviewed_motion_bundle_run,
)
from .safe_input_files import SafeInputFileError, strict_json_object


class P10VisualReviewV2MountCurrentError(RuntimeError):
    """Raised when a persisted mount no longer names the current source."""


def require_current_p10_visual_review_v2_mount(
    store: ProjectStore,
    record: P10PreviewV2CacheRecord,
) -> None:
    """Check current authoring and human heads without rebuilding Preview v2."""

    if type(store) is not ProjectStore \
            or type(record) is not P10PreviewV2CacheRecord:
        raise P10VisualReviewV2MountCurrentError(
            "Visual review mount currentness input is invalid"
        )
    try:
        result = record.result
        preview = result.document
        candidates = record.candidates
        address = record.address
        project = result.project_id
        source = candidates.document["source"]
        preview_source = preview["source"]
        p9 = source["p9"]
        _require_static_bindings(record, project, source, preview_source)

        before = current_p10_preview_v2_scope(store, record)
        _require_current_record(store, record, before)
        package = get_motion_policy_review_package(
            store.state_root, address.motion_policy_package_id,
            current_project_chains=before.chains,
            project_ids=frozenset(before.project_ids),
        )
        _require_policy_and_p9(package, record, p9)
        require_current_p10_preview_v2_upstreams(
            store.state_root, record,
        )
        after = current_p10_preview_v2_scope(store, record)
        if after != before:
            raise P10VisualReviewV2MountCurrentError(
                "Visual review mount source changed during verification"
            )
        _require_current_record(store, record, after)
    except P10VisualReviewV2MountCurrentError:
        raise
    except _ERRORS as exc:
        raise P10VisualReviewV2MountCurrentError(
            "Visual review mount currentness could not be verified"
        ) from exc


def _require_current_record(store, record, scope):
    p10 = read_idle_behavior_review_head(
        store.state_root, record.candidates.document,
    )
    framing = read_capture_framing_verified_head(
        store.state_root, record.framing_candidate,
    )
    if _record_key(
        record.key.locator, scope.project_ids, scope.chains,
        record.address, record, p10, framing,
    ) != record.key:
        raise P10VisualReviewV2MountCurrentError(
            "Visual review mount cache inventory is historical"
        )


def _require_static_bindings(record, project, source, preview_source):
    result, address, key = record.result, record.address, record.key
    expected_p10 = preview_source["current_p10_1_head"]
    expected = (
        address.package_id, address.project_id, address.clip_id,
        address.motion_instance_v2_sha256,
        address.reviewed_motion_bundle_sha256,
        address.p9_decision_sha256,
    )
    actual = (
        result.package_id, project, result.clip_id,
        source["p9"]["motion_instance_v2_sha256"],
        source["p9"]["bundle_sha256"],
        source["p9"]["motion_policy_decision_sha256"],
    )
    if actual != expected \
            or preview_source["idle_behavior_candidates_sha256"] \
                != record.candidates.sha256 \
            or expected_p10["candidate_sha256"] != record.candidates.sha256 \
            or preview_source["capture_framing_candidate_sha256"] \
                != record.framing_candidate.sha256 \
            or (key.p10_candidate_sha256, key.p10_decision_sha256,
                key.p10_revision) != (
                    record.candidates.sha256,
                    expected_p10["decision_sha256"], expected_p10["revision"],
                ) \
            or (key.framing_candidate_sha256,
                key.framing_decision_sha256, key.framing_revision) != (
                    record.framing_candidate.sha256,
                    preview_source["capture_framing_decision_sha256"],
                    preview_source["capture_framing_revision"],
                ):
        raise P10VisualReviewV2MountCurrentError(
            "Visual review mount static identities are cross-wired"
        )


def _require_policy_and_p9(package, record, p9):
    address = record.address
    if package.get("authoring_alignment") != "current" \
            or (package.get("project_id"), package.get("motion_id"),
                package.get("clip_id")) != (
                    address.project_id, address.motion_id, address.clip_id,
                ) \
            or package.get("identities", {}).get(
                "foot_candidates_sha256"
            ) != p9["foot_lock_candidates_sha256"] \
            or package.get("identities", {}).get(
                "depth_candidates_sha256"
            ) != p9["depth_order_candidates_sha256"]:
        raise P10VisualReviewV2MountCurrentError(
            "Visual review mount policy package differs"
        )
    directory = existing_bundle_path(
        record.result._state_root, address.project_id,
        address.motion_instance_v2_sha256,
        address.reviewed_motion_bundle_sha256,
    )
    items = read_bundle_files(directory)
    if reviewed_motion_bundle_address_sha256(
        address.project_id, address.motion_instance_v2_sha256, items,
    ) != address.reviewed_motion_bundle_sha256:
        raise P10VisualReviewV2MountCurrentError(
            "Visual review mount P9 bytes differ from their address"
        )
    raw = dict(items)["run-manifest.json"]
    run = strict_json_object(raw, "reviewed-motion run")
    require_reviewed_motion_bundle_run(run)
    inputs, outputs = run["inputs"], run["outputs"]
    source = record.candidates.document["source"]
    if run["project_id"] != address.project_id \
            or run["clip_id"] != address.clip_id \
            or hashlib.sha256(raw).hexdigest() != p9["run_sha256"] \
            or inputs["p3"] != {
                "rig_sha256": source["p3"]["rig_sha256"],
                "bundle_sha256": source["p3"]["bundle_sha256"],
            } \
            or inputs["p5"] != {
                "instance_sha256": source["p5"]["instance_sha256"],
                "bundle_sha256": source["p5"]["bundle_sha256"],
                "target_profile_sha256": source["p5"][
                    "target_profile_sha256"
                ],
            } \
            or inputs["foot_lock_candidates_sha256"] \
                != p9["foot_lock_candidates_sha256"] \
            or inputs["depth_order_candidates_sha256"] \
                != p9["depth_order_candidates_sha256"] \
            or inputs["motion_policy_decision_sha256"] \
                != p9["motion_policy_decision_sha256"] \
            or outputs != {
                "reviewed_motion_policy_sha256":
                    p9["reviewed_motion_policy_sha256"],
                "motion_instance_v2_sha256":
                    p9["motion_instance_v2_sha256"],
            }:
        raise P10VisualReviewV2MountCurrentError(
            "Visual review mount P9 provenance differs"
        )


_ERRORS = (
    CaptureFramingVerifiedHeadError, CurrentProjectChainError,
    IdleBehaviorReviewHeadError, IdleBehaviorReviewPackageError, KeyError,
    MotionPolicyReviewPackageError, OSError, ProjectStoreError,
    P10PreviewV2CurrentScopeError,
    P10PreviewV2UpstreamAddressError,
    ReviewedMotionBundleContractError,
    ReviewedMotionBundleFilesError, ReviewedMotionBundleRunError,
    SafeInputFileError, TypeError, ValueError,
)


__all__ = [
    "P10VisualReviewV2MountCurrentError",
    "require_current_p10_visual_review_v2_mount",
]
