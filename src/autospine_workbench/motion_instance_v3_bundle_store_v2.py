"""Current-head-gated atomic publication for P10.6b v2 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadCheckV2Error,
    require_current_body_sway_dynamic_seam_heads_v2,
)
from .immutable_bundle_fs import ImmutableBundleFSError
from .motion_instance_v3_bundle_contract_v2 import (
    MotionInstanceV3BundleContractV2Error,
    build_motion_instance_v3_bundle_contract_v2,
)
from .motion_instance_v3_bundle_fs_v2 import (
    MotionInstanceV3BundleFSV2Error,
    motion_instance_v3_bundle_fs_v2,
)
from .motion_instance_v3_bundle_reader_v2 import (
    MotionInstanceV3BundleReaderV2,
    MotionInstanceV3BundleReaderV2Error,
)
from .motion_instance_v3_prepared_v2 import PreparedMotionInstanceV3V2
from .project_store import ProjectStore, ProjectStoreError
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import canonical_json_bytes


class MotionInstanceV3BundleStoreV2Error(RuntimeError):
    """Raised when P10.6b v2 cannot publish under unchanged heads."""


@dataclass(frozen=True, slots=True)
class PublishedMotionInstanceV3BundleV2:
    path: Path
    project_id: str
    clip_id: str
    admission_sha256: str
    dynamic_seam_probe_sha256: str
    dynamic_seam_bundle_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    motion_instance_v3_sha256: str
    bundle_sha256: str
    run_sha256: str
    reused: bool


class MotionInstanceV3BundleStoreV2:
    """Seal current visual-v2/seam-v1 heads before any filesystem write."""

    def __init__(self, capture_job_reader, project_store: ProjectStore) -> None:
        self.capture_job_reader = capture_job_reader
        self.project_store = project_store

    def publish(
        self,
        prepared: PreparedMotionInstanceV3V2,
        motion_instance_v3: Mapping[str, Any],
        dynamic_bundle: VerifiedBodySwayDynamicSeamBundleV2,
        reviewed_bundle: VerifiedReviewedMotionBundle,
    ) -> PublishedMotionInstanceV3BundleV2:
        """Build between two current-head reads, then publish/read back."""

        try:
            _require_inputs(
                self.capture_job_reader, self.project_store, prepared,
                dynamic_bundle, reviewed_bundle,
            )
            before = require_current_body_sway_dynamic_seam_heads_v2(
                self.capture_job_reader, self.project_store,
                dynamic_bundle.source,
            )
            _require_admission_head(prepared, before)
            contract = build_motion_instance_v3_bundle_contract_v2(
                prepared, motion_instance_v3, dynamic_bundle, reviewed_bundle,
            )
            after = require_current_body_sway_dynamic_seam_heads_v2(
                self.capture_job_reader, self.project_store,
                dynamic_bundle.source,
            )
            _require_unchanged_heads(prepared, before, after)
        except MotionInstanceV3BundleStoreV2Error:
            raise
        except _PREFLIGHT_FAILURES as exc:
            raise MotionInstanceV3BundleStoreV2Error(
                "P10.6b v2 input or current-head authority is invalid"
            ) from exc
        try:
            filesystem = motion_instance_v3_bundle_fs_v2(
                self.project_store.state_root, contract.project_id,
            )
            published = filesystem.publish(
                contract.motion_instance_v3_sha256,
                contract.bundle_sha256,
                contract.document_bytes,
            )
            verified = MotionInstanceV3BundleReaderV2(
                self.project_store.state_root,
            ).load(
                contract.project_id, contract.motion_instance_v3_sha256,
                contract.bundle_sha256, dynamic_bundle=dynamic_bundle,
                reviewed_bundle=reviewed_bundle, prepared=prepared,
            )
            if verified.document_bytes != contract.document_bytes \
                    or verified.identities != contract.identities:
                raise MotionInstanceV3BundleStoreV2Error(
                    "Published P10.6b v2 bytes differ on exact readback"
                )
            return PublishedMotionInstanceV3BundleV2(
                published.path, contract.project_id, contract.clip_id,
                contract.admission_sha256,
                contract.dynamic_seam_probe_sha256,
                contract.dynamic_seam_bundle_sha256,
                contract.motion_instance_v2_sha256,
                contract.reviewed_motion_bundle_sha256,
                contract.motion_instance_v3_sha256,
                contract.bundle_sha256, contract.run_sha256,
                published.reused,
            )
        except MotionInstanceV3BundleStoreV2Error:
            raise
        except (
            ImmutableBundleFSError, MotionInstanceV3BundleFSV2Error,
            MotionInstanceV3BundleReaderV2Error, OSError, RuntimeError,
            TypeError, ValueError,
        ) as exc:
            raise MotionInstanceV3BundleStoreV2Error(
                "P10.6b v2 atomic publication failed"
            ) from exc


def _require_inputs(capture, store, prepared, dynamic, reviewed):
    if type(store) is not ProjectStore \
            or not callable(getattr(capture, "get", None)) \
            or type(prepared) is not PreparedMotionInstanceV3V2 \
            or type(dynamic) is not VerifiedBodySwayDynamicSeamBundleV2 \
            or type(reviewed) is not VerifiedReviewedMotionBundle:
        raise MotionInstanceV3BundleStoreV2Error(
            "P10.6b v2 publication requires exact issued inputs"
        )


def _require_admission_head(prepared, observed):
    try:
        heads = prepared.admission["head_observations"]
        expected = heads["before"]["observation"]
        if expected != heads["after"]["observation"] \
                or canonical_json_bytes(expected) != observed.canonical_bytes \
                or expected["identity_sha256"] != observed.identity_sha256:
            raise MotionInstanceV3BundleStoreV2Error(
                "P10.6b v2 admission is no longer the current review head"
            )
    except MotionInstanceV3BundleStoreV2Error:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise MotionInstanceV3BundleStoreV2Error(
            "P10.6b v2 admission head evidence is invalid"
        ) from exc


def _require_unchanged_heads(prepared, before, after):
    _require_admission_head(prepared, after)
    if before.identity_sha256 != after.identity_sha256 \
            or before.canonical_bytes != after.canonical_bytes:
        raise MotionInstanceV3BundleStoreV2Error(
            "P10.6b v2 current review heads changed before publication"
        )


_PREFLIGHT_FAILURES = (
    AttributeError, BodySwayDynamicSeamHeadCheckV2Error, KeyError,
    MotionInstanceV3BundleContractV2Error, OSError, OverflowError,
    ProjectStoreError, RecursionError, RuntimeError, TypeError,
    UnicodeError, ValueError,
)


__all__ = [
    "MotionInstanceV3BundleStoreV2",
    "MotionInstanceV3BundleStoreV2Error",
    "PublishedMotionInstanceV3BundleV2",
]
