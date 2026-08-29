"""Atomic immutable publication for pinned Spine 4.2 export bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from .atomic_staging import create_same_parent_staging
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_bundle_contract import (
    Spine42BundleContract,
    Spine42BundleContractError,
    build_spine42_bundle_contract,
)
from .spine42_bundle_files import (
    Spine42BundleFilesError,
    existing_exact_child,
    publication_parent,
    read_bundle_files,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)


class Spine42BundleStoreError(RuntimeError):
    """Raised when a Spine export cannot be published or reused safely."""


@dataclass(frozen=True, slots=True)
class PublishedSpine42Bundle:
    path: Path
    project_id: str
    mode: str
    clip_id: str | None
    skeleton_json_sha256: str
    atlas_sha256: str
    png_sha256: str
    run_document_sha256: str
    report_sha256: str
    bundle_sha256: str
    reused: bool


class Spine42BundleStore:
    """Publish the fixed inventory under skeleton JSON and bundle SHAs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        project_id: str,
        p3_source: Mapping[str, Any],
        skeleton_json: Mapping[str, Any],
        atlas_bytes: bytes,
        png_bytes: bytes,
        source_image_sha256s: Mapping[str, str],
        *,
        p5_source: Mapping[str, Any] | None = None,
    ) -> PublishedSpine42Bundle:
        try:
            contract = build_spine42_bundle_contract(
                project_id, p3_source, skeleton_json, atlas_bytes, png_bytes,
                source_image_sha256s, p5_source=p5_source,
            )
        except Spine42BundleContractError as exc:
            raise Spine42BundleStoreError(
                "Spine bundle publication input is invalid"
            ) from exc
        parent: Path | None = None
        staging: Path | None = None
        try:
            parent = publication_parent(
                self.state_root, contract.project_id,
                contract.skeleton_json_sha256,
            )
            destination = existing_exact_child(parent, contract.bundle_sha256)
            if destination is not None:
                verify_spine42_bundle_directory(destination, contract)
                return _published(destination, contract, reused=True)
            staging = create_same_parent_staging(
                parent, prefix=f".{contract.bundle_sha256[:12]}.",
            )
            require_real_directory(staging, "Spine bundle staging directory")
            for name, data in contract.document_bytes.items():
                write_file(staging / name, data)
            verify_spine42_bundle_directory(staging, contract, staging=True)
            sync_directory(staging)
            try:
                destination = parent / contract.bundle_sha256
                os.rename(staging, destination)
                staging = None
                sync_directory(parent)
                reused = False
            except OSError:
                destination = existing_exact_child(parent, contract.bundle_sha256)
                if destination is None:
                    raise
                verify_spine42_bundle_directory(destination, contract)
                reused = True
            verify_spine42_bundle_directory(destination, contract)
            return _published(destination, contract, reused=reused)
        except Spine42BundleStoreError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise Spine42BundleStoreError(
                "Could not atomically publish Spine bundle"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def verify_spine42_bundle_directory(
    directory: Path,
    contract: Spine42BundleContract,
    *,
    staging: bool = False,
) -> tuple[tuple[str, bytes], ...]:
    """Verify exact bytes and a semantic rebuild from one safe read snapshot."""

    try:
        directory = require_real_directory(directory, "Spine bundle directory")
        if not staging and directory.name != contract.bundle_sha256:
            raise Spine42BundleStoreError(
                "Spine bundle has the wrong content-address path"
            )
        items = read_bundle_files(directory)
        raw = dict(items)
        if raw != contract.document_bytes:
            raise Spine42BundleStoreError("Spine bundle document bytes changed")
        skeleton = strict_json_object(raw["skeleton.json"], "skeleton.json")
        run = strict_json_object(raw["run-manifest.json"], "run-manifest.json")
        strict_json_object(raw["export-report.json"], "export-report.json")
        source_images = _source_images(run)
        rebuilt = build_spine42_bundle_contract(
            contract.project_id,
            run["inputs"]["p3"],
            skeleton,
            raw["skeleton.atlas"],
            raw["skeleton.png"],
            source_images,
            p5_source=run["inputs"]["p5"],
        )
        if rebuilt != contract or rebuilt.document_bytes != raw:
            raise Spine42BundleStoreError("Spine bundle semantic identity changed")
        return items
    except Spine42BundleStoreError:
        raise
    except (
        KeyError, SafeInputFileError, Spine42BundleContractError,
        Spine42BundleFilesError, TypeError, ValueError,
    ) as exc:
        raise Spine42BundleStoreError(
            "Spine bundle semantic rebuild failed"
        ) from exc


def _source_images(run: Mapping[str, Any]) -> dict[str, str]:
    values = run["inputs"]["source_images"]
    if type(values) is not list:
        raise Spine42BundleStoreError("Source image inventory is invalid")
    result: dict[str, str] = {}
    for value in values:
        if type(value) is not dict or set(value) != {"path", "sha256"} \
                or value["path"] in result:
            raise Spine42BundleStoreError("Source image inventory is invalid")
        result[value["path"]] = value["sha256"]
    return result


def _published(path, contract, *, reused):
    return PublishedSpine42Bundle(
        path, contract.project_id, contract.mode, contract.clip_id,
        contract.skeleton_json_sha256, contract.atlas_sha256,
        contract.png_sha256, contract.run_document_sha256,
        contract.report_sha256, contract.bundle_sha256, reused,
    )
