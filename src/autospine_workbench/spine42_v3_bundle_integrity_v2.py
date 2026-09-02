"""Read-once pure integrity checks for P10.7a v2 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_v3_bundle_contract_v2 import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_DOCUMENT_BYTES,
    Spine42V3BundleContractV2,
    Spine42V3BundleContractV2Error,
    build_spine42_v3_bundle_contract_v2,
)
from .spine42_v3_bundle_files_v2 import NAMESPACE


class Spine42V3BundleIntegrityV2Error(ValueError):
    """Raised when stored v2-source export bytes are not one contract."""


@dataclass(frozen=True, slots=True)
class Spine42V3BundleSnapshotV2:
    path: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


def verify_spine42_v3_bundle_snapshot_v2(
    snapshot: Spine42V3BundleSnapshotV2,
    *,
    expected_project_id: str,
    expected_skeleton_json_sha256: str,
    expected_bundle_sha256: str,
    require_address_path: bool = True,
) -> Spine42V3BundleContractV2:
    """Rebuild canonical evidence from one read-once five-file snapshot."""

    try:
        if type(snapshot) is not Spine42V3BundleSnapshotV2:
            raise Spine42V3BundleIntegrityV2Error(
                "P10.7a v2 snapshot type is invalid"
            )
        items = _exact_items(snapshot.document_items)
        raw = dict(items)
        skeleton = strict_json_object(raw[DOCUMENT_NAMES[0]], DOCUMENT_NAMES[0])
        run = strict_json_object(raw[DOCUMENT_NAMES[3]], DOCUMENT_NAMES[3])
        strict_json_object(raw[DOCUMENT_NAMES[4]], DOCUMENT_NAMES[4])
        inputs = _object(run.get("inputs"), "P10.7a v2 run inputs")
        source_images = _source_images(inputs.get("source_images"))
        contract = build_spine42_v3_bundle_contract_v2(
            expected_project_id,
            run.get("clip_id"),
            _object(inputs.get("p3"), "P3 source"),
            _object(
                inputs.get("motion_instance_v3_v2"),
                "P10.6b v2 MotionInstance v3 source",
            ),
            skeleton,
            raw[DOCUMENT_NAMES[1]],
            raw[DOCUMENT_NAMES[2]],
            source_images,
        )
        _require_contract(
            snapshot, contract, raw, expected_project_id,
            expected_skeleton_json_sha256, expected_bundle_sha256,
            require_address_path,
        )
        return contract
    except Spine42V3BundleIntegrityV2Error:
        raise
    except (
        KeyError, OverflowError, RuntimeError, SafeInputFileError,
        Spine42V3BundleContractV2Error, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3BundleIntegrityV2Error(
            "P10.7a v2 bundle integrity verification failed"
        ) from exc


def _require_contract(
    snapshot, contract, raw, project, skeleton_sha, bundle_sha,
    require_address_path,
) -> None:
    if contract.document_bytes != raw:
        raise Spine42V3BundleIntegrityV2Error(
            "P10.7a v2 files are not canonical contract snapshots"
        )
    if contract.project_id != project \
            or contract.skeleton_json_sha256 != skeleton_sha \
            or contract.bundle_sha256 != bundle_sha:
        raise Spine42V3BundleIntegrityV2Error(
            "P10.7a v2 content differs from its explicit address"
        )
    if require_address_path:
        parts = tuple(snapshot.path.parents[index].name for index in range(4))
        if (snapshot.path.name, *parts) != (
            contract.bundle_sha256, contract.skeleton_json_sha256,
            NAMESPACE, contract.project_id, "builds",
        ):
            raise Spine42V3BundleIntegrityV2Error(
                "P10.7a v2 content-address path is invalid"
            )


def _exact_items(value: Any) -> tuple[tuple[str, bytes], ...]:
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise Spine42V3BundleIntegrityV2Error(
            "P10.7a v2 inventory is invalid"
        )
    result, total = [], 0
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2 \
                or item[0] != DOCUMENT_NAMES[index] \
                or type(item[1]) is not bytes \
                or len(item[1]) > DOCUMENT_LIMITS[index]:
            raise Spine42V3BundleIntegrityV2Error(
                "P10.7a v2 inventory is invalid"
            )
        total += len(item[1])
        result.append(item)
    if total > MAX_TOTAL_DOCUMENT_BYTES:
        raise Spine42V3BundleIntegrityV2Error(
            "P10.7a v2 byte limit exceeded"
        )
    return tuple(result)


def _source_images(value: Any) -> dict[str, str]:
    if type(value) is not list:
        raise Spine42V3BundleIntegrityV2Error(
            "P10.7a v2 source image inventory is invalid"
        )
    result: dict[str, str] = {}
    for item in value:
        if type(item) is not dict \
                or set(item) != {"attachment_id", "sha256"} \
                or type(item["attachment_id"]) is not str \
                or not item["attachment_id"] \
                or item["attachment_id"] in result:
            raise Spine42V3BundleIntegrityV2Error(
                "P10.7a v2 source image inventory is invalid"
            )
        result[item["attachment_id"]] = item["sha256"]
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise Spine42V3BundleIntegrityV2Error(f"{label} must be an object")
    return value


__all__ = [
    "Spine42V3BundleIntegrityV2Error", "Spine42V3BundleSnapshotV2",
    "verify_spine42_v3_bundle_snapshot_v2",
]
