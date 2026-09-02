"""Strict three-document P10.6b v2 immutable bundle contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .body_sway_motion_consumer_profile_v2 import (
    MAX_DOCUMENT_BYTES as MAX_ADMISSION_BYTES,
)
from .immutable_bundle_fs import framed_bundle_sha256
from .manifest_artifacts import LayerManifestError, require_safe_token
from .motion_instance_v3_bundle_run_v2 import (
    MAX_RUN_BYTES,
    MotionInstanceV3BundleRunV2Error,
    build_motion_instance_v3_bundle_run_v2,
)
from .motion_instance_v3_prepared_v2 import (
    PreparedMotionInstanceV3V2,
)
from .motion_instance_v3_validation_v2 import (
    MAX_DOCUMENT_BYTES as MAX_INSTANCE_BYTES,
    MotionInstanceV3V2ValidationError,
    motion_instance_v3_canonical_bytes_v2,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle


BUNDLE_ADDRESS_DOMAIN = (
    "autospine-body-sway-motion-instance-v3-bundle-address/v2"
)
DOCUMENT_NAMES = (
    "body-sway-motion-consumer-admission-v2.json",
    "motion-instance-v3.json",
    "run-manifest-v2.json",
)
DOCUMENT_LIMITS = (
    MAX_ADMISSION_BYTES,
    MAX_INSTANCE_BYTES,
    MAX_RUN_BYTES,
)
MAX_FILE_BYTES = max(DOCUMENT_LIMITS)
MAX_TOTAL_BYTES = sum(DOCUMENT_LIMITS)


class MotionInstanceV3BundleContractV2Error(ValueError):
    """Raised when v2 bundle bytes cannot be reproduced exactly."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV3BundleContractV2:
    project_id: str
    clip_id: str
    admission_sha256: str
    source_set_sha256: str
    source_document_sha256: str
    dynamic_seam_probe_sha256: str
    dynamic_seam_bundle_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_profile_sha256: str
    motion_domain_sha256: str
    rotation_timeline_sha256: str
    base_channels_sha256: str
    rig_ir_sha256: str
    target_profile_sha256: str
    run_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def identities(self) -> dict[str, str]:
        return {
            name: getattr(self, name) for name in (
                "admission_sha256", "source_set_sha256",
                "source_document_sha256", "dynamic_seam_probe_sha256",
                "dynamic_seam_bundle_sha256", "motion_instance_v2_sha256",
                "reviewed_motion_bundle_sha256",
                "motion_instance_v3_sha256",
                "motion_instance_v3_profile_sha256",
                "motion_domain_sha256", "rotation_timeline_sha256",
                "base_channels_sha256", "rig_ir_sha256",
                "target_profile_sha256", "run_sha256", "bundle_sha256",
            )
        }


def build_motion_instance_v3_bundle_contract_v2(
    prepared: PreparedMotionInstanceV3V2,
    motion_instance_v3: Mapping[str, Any],
    dynamic_bundle: VerifiedBodySwayDynamicSeamBundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> MotionInstanceV3BundleContractV2:
    """Replay admission/P10.5d/P9/v3 and freeze the exact inventory."""

    try:
        if type(prepared) is not PreparedMotionInstanceV3V2:
            raise MotionInstanceV3BundleContractV2Error(
                "P10.6b v2 requires an issued prepared source"
            )
        project = require_safe_token(prepared.project_id, "Project id")
        admission_bytes = prepared.admission_bytes
        instance_bytes = motion_instance_v3_canonical_bytes_v2(
            motion_instance_v3, prepared=prepared,
        )
        instance = json.loads(instance_bytes)
        source = instance["source"]
        instance_sha = hashlib.sha256(instance_bytes).hexdigest()
        _require_exact_sources(
            project, source, prepared, dynamic_bundle, reviewed_bundle,
        )
        run = build_motion_instance_v3_bundle_run_v2(
            project, prepared.clip_id,
            admission_sha256=prepared.admission_sha256,
            dynamic_seam={
                "source_set_sha256": dynamic_bundle.source_set_sha256,
                "source_document_sha256":
                    dynamic_bundle.source_document_sha256,
                "probe_sha256": dynamic_bundle.probe_sha256,
                "bundle_sha256": dynamic_bundle.bundle_sha256,
            },
            p9={
                "motion_instance_v2_sha256":
                    reviewed_bundle.motion_instance_v2_sha256,
                "bundle_sha256": reviewed_bundle.bundle_sha256,
            },
            motion_domain_sha256=source["motion_domain_sha256"],
            rotation_timeline_sha256=source["rotation_timeline_sha256"],
            base_channels_sha256=source["base_channels_sha256"],
            rig_ir_sha256=source["rig_ir_sha256"],
            target_profile_sha256=source["target_profile_sha256"],
            motion_instance_v3_sha256=instance_sha,
            motion_instance_v3_profile_sha256=
                source["motion_instance_v3_profile_sha256"],
        )
        files = dict(zip(
            DOCUMENT_NAMES,
            (admission_bytes, instance_bytes, run.canonical_bytes),
            strict=True,
        ))
        _require_limits(files)
        bundle_sha = framed_bundle_sha256(
            BUNDLE_ADDRESS_DOMAIN, DOCUMENT_NAMES, files,
        )
        values = (
            project, prepared.clip_id, prepared.admission_sha256,
            dynamic_bundle.source_set_sha256,
            dynamic_bundle.source_document_sha256,
            dynamic_bundle.probe_sha256, dynamic_bundle.bundle_sha256,
            reviewed_bundle.motion_instance_v2_sha256,
            reviewed_bundle.bundle_sha256, instance_sha,
            source["motion_instance_v3_profile_sha256"],
            source["motion_domain_sha256"],
            source["rotation_timeline_sha256"],
            source["base_channels_sha256"], source["rig_ir_sha256"],
            source["target_profile_sha256"], run.sha256, bundle_sha,
        )
        return MotionInstanceV3BundleContractV2(
            *values, tuple((name, files[name]) for name in DOCUMENT_NAMES),
        )
    except MotionInstanceV3BundleContractV2Error:
        raise
    except (
        AttributeError, KeyError, LayerManifestError,
        MotionInstanceV3BundleRunV2Error,
        MotionInstanceV3V2ValidationError, OverflowError, RecursionError,
        RuntimeError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3BundleContractV2Error(
            "MotionInstance v3 v2 bundle contract failed"
        ) from exc


def _require_exact_sources(project, source, prepared, dynamic, reviewed):
    if project != dynamic.project_id or project != reviewed.project_id \
            or prepared.clip_id != dynamic.clip_id \
            or prepared.clip_id != reviewed.clip_id \
            or prepared.dynamic_seam_probe_sha256 != dynamic.probe_sha256 \
            or prepared.dynamic_seam_bundle_sha256 != dynamic.bundle_sha256 \
            or prepared.motion_instance_v2_sha256 \
                != reviewed.motion_instance_v2_sha256 \
            or prepared.reviewed_motion_bundle_sha256 \
                != reviewed.bundle_sha256 \
            or source["body_sway_motion_consumer_admission_sha256"] \
                != prepared.admission_sha256 \
            or source["p9"] != {
                "motion_instance_v2_sha256":
                    reviewed.motion_instance_v2_sha256,
                "bundle_sha256": reviewed.bundle_sha256,
            }:
        raise MotionInstanceV3BundleContractV2Error(
            "MotionInstance v3 v2 sources differ from exact bundles"
        )


def _require_limits(files):
    if tuple(files) != DOCUMENT_NAMES:
        raise MotionInstanceV3BundleContractV2Error(
            "MotionInstance v3 v2 inventory is invalid"
        )
    total = 0
    for (name, data), limit in zip(files.items(), DOCUMENT_LIMITS, strict=True):
        if not isinstance(data, bytes) or len(data) > limit:
            raise MotionInstanceV3BundleContractV2Error(
                f"{name} exceeds its byte limit"
            )
        total += len(data)
    if total > MAX_TOTAL_BYTES:
        raise MotionInstanceV3BundleContractV2Error(
            "MotionInstance v3 v2 bundle exceeds its total byte limit"
        )


__all__ = [
    "BUNDLE_ADDRESS_DOMAIN", "DOCUMENT_LIMITS", "DOCUMENT_NAMES",
    "MAX_FILE_BYTES", "MAX_TOTAL_BYTES",
    "MotionInstanceV3BundleContractV2",
    "MotionInstanceV3BundleContractV2Error",
    "build_motion_instance_v3_bundle_contract_v2",
]
