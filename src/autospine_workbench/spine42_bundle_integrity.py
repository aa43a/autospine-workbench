"""Strict read-once snapshot integrity for immutable Spine 4.2 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    Spine42BundleContractError,
    build_spine42_bundle_contract,
)
from .spine42_bundle_files import (
    Spine42BundleFilesError,
    existing_bundle_path,
    read_bundle_files,
    require_real_directory,
)


class Spine42BundleIntegrityError(ValueError):
    """Raised when stored export bytes cannot prove their exact identity."""


@dataclass(frozen=True, slots=True)
class Spine42BundleSnapshot:
    directory: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedSpine42Bundle:
    path: Path
    project_id: str
    mode: str
    clip_id: str | None
    skeleton_json_sha256: str
    atlas_sha256: str
    png_sha256: str
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    bundle_sha256: str
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    _source_images: tuple[tuple[str, str], ...] = field(repr=False)

    def _json(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._document_items)[name])

    @property
    def skeleton_json(self) -> dict[str, Any]:
        return self._json("skeleton.json")

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self._json("run-manifest.json")

    @property
    def export_report(self) -> dict[str, Any]:
        return self._json("export-report.json")

    @property
    def source_image_sha256s(self) -> dict[str, str]:
        return dict(self._source_images)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)


class VerifiedSpine42BundleReader:
    """Locate, snapshot once, and verify one explicit content address."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def load(
        self,
        project_id: str,
        skeleton_json_sha256: str,
        bundle_sha256: str,
    ) -> VerifiedSpine42Bundle:
        try:
            project = require_safe_token(project_id, "Project id")
            skeleton_sha = require_sha256(
                skeleton_json_sha256, "Skeleton JSON SHA-256"
            )
            bundle_sha = require_sha256(bundle_sha256, "Spine bundle SHA-256")
            path = existing_bundle_path(
                self.state_root, project, skeleton_sha, bundle_sha
            )
            snapshot = Spine42BundleSnapshot(path, read_bundle_files(path))
            return verify_spine42_bundle_snapshot(
                snapshot,
                state_root=self.state_root,
                expected_project_id=project,
                expected_skeleton_json_sha256=skeleton_sha,
                expected_bundle_sha256=bundle_sha,
            )
        except Spine42BundleIntegrityError:
            raise
        except (LayerManifestError, Spine42BundleFilesError) as exc:
            raise Spine42BundleIntegrityError(
                f"Spine bundle reader rejected the requested address: {exc}"
            ) from exc


def verify_spine42_bundle_snapshot(
    snapshot: Spine42BundleSnapshot,
    *,
    state_root: Path,
    expected_project_id: str,
    expected_skeleton_json_sha256: str,
    expected_bundle_sha256: str,
) -> VerifiedSpine42Bundle:
    """Rebuild the pure contract from an admitted exact byte snapshot."""

    try:
        if not isinstance(snapshot, Spine42BundleSnapshot):
            raise Spine42BundleIntegrityError("Spine bundle snapshot is invalid")
        items = _exact_items(snapshot.document_items)
        raw = dict(items)
        skeleton = strict_json_object(raw["skeleton.json"], "skeleton.json")
        run = strict_json_object(raw["run-manifest.json"], "run-manifest.json")
        strict_json_object(raw["export-report.json"], "export-report.json")
        inputs = _object(run.get("inputs"), "run inputs")
        source_images = _source_images(inputs.get("source_images"))
        contract = build_spine42_bundle_contract(
            expected_project_id,
            _object(inputs.get("p3"), "P3 source"),
            skeleton,
            raw["skeleton.atlas"],
            raw["skeleton.png"],
            source_images,
            p5_source=inputs.get("p5"),
        )
        if contract.document_bytes != raw:
            raise Spine42BundleIntegrityError(
                "Spine bundle bytes are not the canonical contract snapshot"
            )
        if (
            contract.project_id != expected_project_id
            or contract.skeleton_json_sha256 != expected_skeleton_json_sha256
            or contract.bundle_sha256 != expected_bundle_sha256
        ):
            raise Spine42BundleIntegrityError(
                "Spine bundle differs from its requested content address"
            )
        expected_path = existing_bundle_path(
            state_root, contract.project_id, contract.skeleton_json_sha256,
            contract.bundle_sha256,
        )
        snapshot_path = Path(os.path.abspath(os.fspath(snapshot.directory)))
        expected_absolute = Path(os.path.abspath(os.fspath(expected_path)))
        require_real_directory(snapshot_path, "Spine snapshot directory")
        if snapshot_path != expected_absolute or \
                snapshot_path.resolve(strict=True) != expected_absolute.resolve(strict=True):
            raise Spine42BundleIntegrityError(
                "Spine bundle content-address path is invalid"
            )
        return VerifiedSpine42Bundle(
            expected_path, contract.project_id, contract.mode, contract.clip_id,
            contract.skeleton_json_sha256, contract.atlas_sha256,
            contract.png_sha256, contract.run_identity_sha256,
            contract.run_document_sha256, contract.report_sha256,
            contract.bundle_sha256, items,
            tuple(sorted(source_images.items())),
        )
    except Spine42BundleIntegrityError:
        raise
    except (
        KeyError, LayerManifestError, OSError, RuntimeError,
        SafeInputFileError, Spine42BundleContractError,
        Spine42BundleFilesError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42BundleIntegrityError(
            f"Spine bundle integrity verification failed: {exc}"
        ) from exc


def replay_verified_spine42_bundle(
    bundle: VerifiedSpine42Bundle,
):
    """Purely rebuild one verified P6 bundle and every exposed identity."""

    if type(bundle) is not VerifiedSpine42Bundle:
        raise Spine42BundleIntegrityError(
            "Spine bundle replay requires an exact verified bundle"
        )
    try:
        items = _exact_items(bundle._document_items)
        raw = dict(items)
        skeleton = strict_json_object(raw["skeleton.json"], "skeleton.json")
        run = strict_json_object(raw["run-manifest.json"], "run-manifest.json")
        strict_json_object(raw["export-report.json"], "export-report.json")
        inputs = _object(run.get("inputs"), "run inputs")
        source_images = _source_images(inputs.get("source_images"))
        contract = build_spine42_bundle_contract(
            bundle.project_id, _object(inputs.get("p3"), "P3 source"),
            skeleton, raw["skeleton.atlas"], raw["skeleton.png"],
            source_images, p5_source=inputs.get("p5"),
        )
        exposed = (
            bundle.project_id, bundle.mode, bundle.clip_id,
            bundle.skeleton_json_sha256, bundle.atlas_sha256,
            bundle.png_sha256, bundle.run_identity_sha256,
            bundle.run_document_sha256, bundle.report_sha256,
            bundle.bundle_sha256, bundle.source_image_sha256s,
        )
        expected = (
            contract.project_id, contract.mode, contract.clip_id,
            contract.skeleton_json_sha256, contract.atlas_sha256,
            contract.png_sha256, contract.run_identity_sha256,
            contract.run_document_sha256, contract.report_sha256,
            contract.bundle_sha256, contract.source_image_sha256s,
        )
        if contract.document_bytes != raw or exposed != expected:
            raise Spine42BundleIntegrityError(
                "Verified Spine bundle differs from exact replay"
            )
        return contract
    except Spine42BundleIntegrityError:
        raise
    except (
        KeyError, LayerManifestError, SafeInputFileError,
        Spine42BundleContractError, TypeError, ValueError,
    ) as exc:
        raise Spine42BundleIntegrityError(
            "Verified Spine bundle replay failed"
        ) from exc


def _exact_items(value: Any) -> tuple[tuple[str, bytes], ...]:
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise Spine42BundleIntegrityError("Spine snapshot inventory is invalid")
    result = []
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2:
            raise Spine42BundleIntegrityError("Spine snapshot inventory is invalid")
        name, data = item
        if name != DOCUMENT_NAMES[index] or type(data) is not bytes \
                or len(data) > DOCUMENT_LIMITS[index]:
            raise Spine42BundleIntegrityError("Spine snapshot inventory is invalid")
        result.append((name, data))
    return tuple(result)


def _source_images(value: Any) -> dict[str, str]:
    if type(value) is not list:
        raise Spine42BundleIntegrityError("Source image inventory is invalid")
    result: dict[str, str] = {}
    for item in value:
        if type(item) is not dict or set(item) != {"path", "sha256"} \
                or item["path"] in result:
            raise Spine42BundleIntegrityError("Source image inventory is invalid")
        result[item["path"]] = item["sha256"]
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise Spine42BundleIntegrityError(f"{label} must be an object")
    return value
