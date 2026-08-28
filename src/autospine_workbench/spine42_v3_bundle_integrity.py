"""Read-once integrity verification for P10.7 Spine 4.2 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_v3_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_DOCUMENT_BYTES,
    Spine42V3BundleContract,
    Spine42V3BundleContractError,
    build_spine42_v3_bundle_contract,
)
from .spine42_v3_bundle_files import NAMESPACE


class Spine42V3BundleIntegrityError(ValueError):
    """Raised when five stored files cannot prove one exact contract."""


@dataclass(frozen=True, slots=True)
class Spine42V3BundleSnapshot:
    path: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedSpine42V3Bundle:
    """Frozen verified identities with copy-isolated document access."""

    path: Path
    project_id: str
    clip_id: str
    adapter_profile_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str
    admission_sha256: str
    motion_instance_v3_profile_sha256: str
    target_profile_sha256: str
    skeleton_json_sha256: str
    atlas_sha256: str
    png_sha256: str
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    bundle_sha256: str
    _source_images: tuple[tuple[str, str], ...] = field(repr=False)
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)

    @property
    def source_image_sha256s(self) -> dict[str, str]:
        return dict(self._source_images)

    @property
    def p3_source(self) -> dict[str, str]:
        return {
            "rig_sha256": self.p3_rig_sha256,
            "bundle_sha256": self.p3_bundle_sha256,
        }

    @property
    def motion_instance_v3_source(self) -> dict[str, str]:
        return {
            "motion_instance_v3_sha256": self.motion_instance_v3_sha256,
            "bundle_sha256": self.motion_instance_v3_bundle_sha256,
            "admission_sha256": self.admission_sha256,
            "profile_sha256": self.motion_instance_v3_profile_sha256,
            "target_profile_sha256": self.target_profile_sha256,
        }

    @property
    def skeleton_json(self) -> dict[str, Any]:
        return self._json(DOCUMENT_NAMES[0])

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self._json(DOCUMENT_NAMES[3])

    @property
    def export_report(self) -> dict[str, Any]:
        return self._json(DOCUMENT_NAMES[4])

    @property
    def contract_identities(self) -> dict[str, str]:
        return {
            name: getattr(self, name) for name in (
                "adapter_profile_sha256", "p3_rig_sha256",
                "p3_bundle_sha256", "motion_instance_v3_sha256",
                "motion_instance_v3_bundle_sha256", "admission_sha256",
                "motion_instance_v3_profile_sha256",
                "target_profile_sha256", "skeleton_json_sha256",
                "atlas_sha256", "png_sha256", "run_identity_sha256",
                "run_document_sha256", "report_sha256", "bundle_sha256",
            )
        }

    def _json(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._document_items)[name])


def verify_spine42_v3_bundle_snapshot(
    snapshot: Spine42V3BundleSnapshot,
    *,
    expected_project_id: str,
    expected_skeleton_json_sha256: str,
    expected_bundle_sha256: str,
    require_address_path: bool = True,
) -> VerifiedSpine42V3Bundle:
    """Rebuild all evidence and compare every stored byte and address."""

    try:
        if type(snapshot) is not Spine42V3BundleSnapshot:
            raise Spine42V3BundleIntegrityError(
                "Spine v3 snapshot type is invalid"
            )
        items = _exact_items(snapshot.document_items)
        raw = dict(items)
        skeleton = strict_json_object(raw[DOCUMENT_NAMES[0]], DOCUMENT_NAMES[0])
        run = strict_json_object(raw[DOCUMENT_NAMES[3]], DOCUMENT_NAMES[3])
        strict_json_object(raw[DOCUMENT_NAMES[4]], DOCUMENT_NAMES[4])
        inputs = _object(run.get("inputs"), "Spine v3 run inputs")
        source_images = _source_images(inputs.get("source_images"))
        contract = build_spine42_v3_bundle_contract(
            expected_project_id,
            run.get("clip_id"),
            _object(inputs.get("p3"), "P3 source"),
            _object(inputs.get("motion_instance_v3"), "MotionInstance v3 source"),
            skeleton,
            raw[DOCUMENT_NAMES[1]],
            raw[DOCUMENT_NAMES[2]],
            source_images,
        )
        _require_contract(snapshot, contract, raw, expected_project_id,
                          expected_skeleton_json_sha256,
                          expected_bundle_sha256, require_address_path)
        return _verified(snapshot.path, contract, items, source_images)
    except Spine42V3BundleIntegrityError:
        raise
    except (
        KeyError, OverflowError, RuntimeError, SafeInputFileError,
        Spine42V3BundleContractError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3BundleIntegrityError(
            f"Spine v3 bundle integrity verification failed: {exc}"
        ) from exc


def replay_verified_spine42_v3_bundle(
    bundle: VerifiedSpine42V3Bundle,
) -> Spine42V3BundleContract:
    """Purely rebuild one already verified bundle without consulting heads."""

    if type(bundle) is not VerifiedSpine42V3Bundle:
        raise Spine42V3BundleIntegrityError(
            "Spine v3 replay requires an exact verified bundle"
        )
    items = _exact_items(bundle._document_items)
    raw = dict(items)
    skeleton = strict_json_object(raw[DOCUMENT_NAMES[0]], DOCUMENT_NAMES[0])
    run = strict_json_object(raw[DOCUMENT_NAMES[3]], DOCUMENT_NAMES[3])
    inputs = _object(run.get("inputs"), "Spine v3 run inputs")
    try:
        contract = build_spine42_v3_bundle_contract(
            bundle.project_id, bundle.clip_id,
            _object(inputs.get("p3"), "P3 source"),
            _object(inputs.get("motion_instance_v3"), "MotionInstance v3 source"),
            skeleton, raw[DOCUMENT_NAMES[1]],
            raw[DOCUMENT_NAMES[2]], bundle.source_image_sha256s,
        )
    except (Spine42V3BundleContractError, TypeError, ValueError) as exc:
        raise Spine42V3BundleIntegrityError(
            "Verified Spine v3 bundle replay failed"
        ) from exc
    identities = {
        name: getattr(contract, name) for name in bundle.contract_identities
    }
    if contract.document_bytes != raw \
            or identities != bundle.contract_identities \
            or contract.project_id != bundle.project_id \
            or contract.clip_id != bundle.clip_id \
            or contract.source_image_sha256s != bundle.source_image_sha256s:
        raise Spine42V3BundleIntegrityError(
            "Verified Spine v3 bundle differs from exact replay"
        )
    return contract


def _require_contract(snapshot, contract, raw, project, skeleton_sha,
                      bundle_sha, require_address_path) -> None:
    if contract.document_bytes != raw:
        raise Spine42V3BundleIntegrityError(
            "Spine v3 bytes are not canonical contract snapshots"
        )
    if contract.project_id != project \
            or contract.skeleton_json_sha256 != skeleton_sha \
            or contract.bundle_sha256 != bundle_sha:
        raise Spine42V3BundleIntegrityError(
            "Spine v3 content differs from its explicit address"
        )
    if require_address_path:
        parts = tuple(
            snapshot.path.parents[index].name for index in range(4)
        )
        if (snapshot.path.name, *parts) != (
            contract.bundle_sha256, contract.skeleton_json_sha256,
            NAMESPACE, contract.project_id, "builds",
        ):
            raise Spine42V3BundleIntegrityError(
                "Spine v3 content-address path is invalid"
            )


def _verified(path, contract, items, source_images):
    return VerifiedSpine42V3Bundle(
        path, contract.project_id, contract.clip_id,
        contract.adapter_profile_sha256, contract.p3_rig_sha256,
        contract.p3_bundle_sha256, contract.motion_instance_v3_sha256,
        contract.motion_instance_v3_bundle_sha256,
        contract.admission_sha256,
        contract.motion_instance_v3_profile_sha256,
        contract.target_profile_sha256, contract.skeleton_json_sha256,
        contract.atlas_sha256, contract.png_sha256,
        contract.run_identity_sha256, contract.run_document_sha256,
        contract.report_sha256, contract.bundle_sha256,
        tuple(sorted(source_images.items())), items,
    )


def _exact_items(value: Any) -> tuple[tuple[str, bytes], ...]:
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise Spine42V3BundleIntegrityError("Spine v3 inventory is invalid")
    result, total = [], 0
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2 \
                or item[0] != DOCUMENT_NAMES[index] \
                or type(item[1]) is not bytes \
                or len(item[1]) > DOCUMENT_LIMITS[index]:
            raise Spine42V3BundleIntegrityError("Spine v3 inventory is invalid")
        total += len(item[1])
        result.append(item)
    if total > MAX_TOTAL_DOCUMENT_BYTES:
        raise Spine42V3BundleIntegrityError("Spine v3 byte limit exceeded")
    return tuple(result)


def _source_images(value: Any) -> dict[str, str]:
    if type(value) is not list:
        raise Spine42V3BundleIntegrityError("Source image inventory is invalid")
    result: dict[str, str] = {}
    for item in value:
        if type(item) is not dict or set(item) != {"path", "sha256"} \
                or item["path"] in result:
            raise Spine42V3BundleIntegrityError(
                "Source image inventory is invalid"
            )
        result[item["path"]] = item["sha256"]
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise Spine42V3BundleIntegrityError(f"{label} must be an object")
    return value


__all__ = [
    "Spine42V3BundleIntegrityError", "Spine42V3BundleSnapshot",
    "VerifiedSpine42V3Bundle", "replay_verified_spine42_v3_bundle",
    "verify_spine42_v3_bundle_snapshot",
]
