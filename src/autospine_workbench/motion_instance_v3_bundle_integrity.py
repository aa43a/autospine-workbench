"""Exact historical replay for immutable MotionInstance v3 bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .motion_instance_v3_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_DOCUMENT_BYTES,
    MotionInstanceV3BundleContract,
    MotionInstanceV3BundleContractError,
    build_motion_instance_v3_bundle_contract,
)
from .motion_instance_v3_bundle_files import NAMESPACE
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .safe_input_files import SafeInputFileError, strict_json_object


class MotionInstanceV3BundleIntegrityError(ValueError):
    """Raised when stored bytes cannot be replayed from exact P10.6a/P9."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV3BundleSnapshot:
    """One read of each fixed-inventory file in a secured directory."""

    path: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedMotionInstanceV3Bundle:
    """Frozen verified identities with isolated document access."""

    path: Path
    project_id: str
    clip_id: str
    admission_sha256: str
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
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)

    @property
    def identities(self) -> dict[str, str]:
        return {
            "admission_sha256": self.admission_sha256,
            "motion_instance_v2_sha256": self.motion_instance_v2_sha256,
            "reviewed_motion_bundle_sha256":
                self.reviewed_motion_bundle_sha256,
            "motion_instance_v3_sha256": self.motion_instance_v3_sha256,
            "motion_instance_v3_profile_sha256":
                self.motion_instance_v3_profile_sha256,
            "motion_domain_sha256": self.motion_domain_sha256,
            "rotation_timeline_sha256": self.rotation_timeline_sha256,
            "base_channels_sha256": self.base_channels_sha256,
            "rig_ir_sha256": self.rig_ir_sha256,
            "target_profile_sha256": self.target_profile_sha256,
            "run_sha256": self.run_sha256,
            "bundle_sha256": self.bundle_sha256,
        }

    def document(self, name: str) -> dict[str, Any]:
        try:
            return json.loads(dict(self._document_items)[name])
        except KeyError as exc:
            raise KeyError(name) from exc


def replay_verified_motion_instance_v3_bundle(
    bundle: VerifiedMotionInstanceV3Bundle,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> MotionInstanceV3BundleContract:
    """Rebuild a verified historical value without observing current heads."""

    try:
        if type(bundle) is not VerifiedMotionInstanceV3Bundle:
            raise MotionInstanceV3BundleIntegrityError(
                "MotionInstance v3 replay requires an exact verified bundle"
            )
        raw = bundle.document_bytes
        if tuple(raw) != DOCUMENT_NAMES:
            raise MotionInstanceV3BundleIntegrityError(
                "Verified MotionInstance v3 inventory differs"
            )
        documents = {
            name: strict_json_object(raw[name], name)
            for name in DOCUMENT_NAMES
        }
        contract = build_motion_instance_v3_bundle_contract(
            bundle.project_id,
            documents[DOCUMENT_NAMES[0]],
            documents[DOCUMENT_NAMES[1]],
            reviewed_bundle,
        )
        if contract.project_id != bundle.project_id \
                or contract.clip_id != bundle.clip_id \
                or contract.inventory != bundle.inventory \
                or contract.identities != bundle.identities \
                or contract.document_bytes != raw:
            raise MotionInstanceV3BundleIntegrityError(
                "Verified MotionInstance v3 bundle differs from exact replay"
            )
        return contract
    except MotionInstanceV3BundleIntegrityError:
        raise
    except (
        MotionInstanceV3BundleContractError, SafeInputFileError,
        AttributeError, KeyError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise MotionInstanceV3BundleIntegrityError(
            f"MotionInstance v3 bundle replay failed: {exc}"
        ) from exc


def verify_motion_instance_v3_bundle_snapshot(
    snapshot: MotionInstanceV3BundleSnapshot,
    *,
    expected_project_id: str,
    expected_motion_instance_v3_sha256: str,
    expected_bundle_sha256: str,
    reviewed_bundle: VerifiedReviewedMotionBundle,
    require_address_path: bool = True,
) -> VerifiedMotionInstanceV3Bundle:
    """Rebuild all documents and compare every exact stored byte."""

    try:
        if type(snapshot) is not MotionInstanceV3BundleSnapshot:
            raise MotionInstanceV3BundleIntegrityError(
                "MotionInstance v3 snapshot type is invalid"
            )
        raw = _exact_items(snapshot.document_items)
        documents = {
            name: strict_json_object(raw[name], name)
            for name in DOCUMENT_NAMES
        }
        contract = build_motion_instance_v3_bundle_contract(
            expected_project_id,
            documents[DOCUMENT_NAMES[0]],
            documents[DOCUMENT_NAMES[1]],
            reviewed_bundle,
        )
        if contract.document_bytes != raw:
            raise MotionInstanceV3BundleIntegrityError(
                "MotionInstance v3 bytes are not strict canonical snapshots"
            )
        if contract.project_id != expected_project_id \
                or contract.motion_instance_v3_sha256 \
                != expected_motion_instance_v3_sha256 \
                or contract.bundle_sha256 != expected_bundle_sha256:
            raise MotionInstanceV3BundleIntegrityError(
                "MotionInstance v3 bundle differs from its explicit address"
            )
        if require_address_path:
            _require_address(snapshot.path, contract)
        return _verified(snapshot.path, contract, raw)
    except MotionInstanceV3BundleIntegrityError:
        raise
    except (
        MotionInstanceV3BundleContractError, SafeInputFileError,
        AttributeError, KeyError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise MotionInstanceV3BundleIntegrityError(
            f"MotionInstance v3 integrity verification failed: {exc}"
        ) from exc


def _verified(path, contract, raw) -> VerifiedMotionInstanceV3Bundle:
    return VerifiedMotionInstanceV3Bundle(
        path, contract.project_id, contract.clip_id,
        contract.admission_sha256, contract.motion_instance_v2_sha256,
        contract.reviewed_motion_bundle_sha256,
        contract.motion_instance_v3_sha256,
        contract.motion_instance_v3_profile_sha256,
        contract.motion_domain_sha256, contract.rotation_timeline_sha256,
        contract.base_channels_sha256, contract.rig_ir_sha256,
        contract.target_profile_sha256, contract.run_sha256,
        contract.bundle_sha256,
        tuple((name, raw[name]) for name in DOCUMENT_NAMES),
    )


def _exact_items(items) -> dict[str, bytes]:
    if type(items) is not tuple or len(items) != len(DOCUMENT_NAMES):
        raise MotionInstanceV3BundleIntegrityError(
            "MotionInstance v3 snapshot inventory is invalid"
        )
    result: dict[str, bytes] = {}
    total = 0
    for index, item in enumerate(items):
        if type(item) is not tuple or len(item) != 2 \
                or item[0] != DOCUMENT_NAMES[index] \
                or not isinstance(item[1], bytes):
            raise MotionInstanceV3BundleIntegrityError(
                "MotionInstance v3 snapshot order or type is invalid"
            )
        total += len(item[1])
        if len(item[1]) > DOCUMENT_LIMITS[index]:
            raise MotionInstanceV3BundleIntegrityError(
                f"{item[0]} exceeds its snapshot byte limit"
            )
        if total > MAX_TOTAL_DOCUMENT_BYTES:
            raise MotionInstanceV3BundleIntegrityError(
                "MotionInstance v3 snapshot exceeds its total byte limit"
            )
        result[item[0]] = item[1]
    return result


def _require_address(path: Path, contract) -> None:
    parts = (
        path.name,
        path.parent.name,
        path.parent.parent.name,
        path.parent.parent.parent.name,
        path.parent.parent.parent.parent.name,
    )
    expected = (
        contract.bundle_sha256,
        contract.motion_instance_v3_sha256,
        NAMESPACE,
        contract.project_id,
        "builds",
    )
    if parts != expected:
        raise MotionInstanceV3BundleIntegrityError(
            "MotionInstance v3 content-address path is invalid"
        )


__all__ = [
    "MotionInstanceV3BundleIntegrityError", "MotionInstanceV3BundleSnapshot",
    "VerifiedMotionInstanceV3Bundle",
    "replay_verified_motion_instance_v3_bundle",
    "verify_motion_instance_v3_bundle_snapshot",
]
