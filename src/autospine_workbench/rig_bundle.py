"""Immutable publication of a validated RigIR setup bundle."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from .layer_manifest import sha256_file
from .resolved_project import canonical_sha256
from .rig_bundle_validation import (
    RigBundleError,
    bundle_address_sha256,
    require_png,
    required_sha,
    validate_bundle_inputs,
)
from .rig_bundle_integrity import verify_rig_bundle_directory
from .rig_setup_artifact import (
    RigSetupArtifact,
    RigSetupArtifactError,
    SETUP_DOCUMENT_NAME,
    SETUP_IMAGE_NAME,
    build_setup_artifact,
)


_DOCUMENT_NAMES = {
    "rig.json", "run-manifest.json", "probes.json", SETUP_DOCUMENT_NAME,
}


class RigBundleStore:
    """Publish RigIR, compile provenance, probes, and pinned layer PNGs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self.root = self.state_root / "builds"

    def publish(
        self,
        project_id: str,
        rig: Mapping[str, Any],
        run_manifest: Mapping[str, Any],
        probe_report: Mapping[str, Any],
        layer_bundle_path: Path,
    ) -> tuple[Path, str]:
        rig_sha, run_sha, probe_sha, assets = validate_bundle_inputs(
            project_id, rig, run_manifest, probe_report, Path(layer_bundle_path)
        )
        _require_expected_layer_bundle(
            self.root,
            project_id,
            rig["source"]["layer_manifest_sha256"],
            Path(layer_bundle_path),
        )
        try:
            setup = build_setup_artifact(
                project_id, rig, rig_sha, Path(layer_bundle_path)
            )
        except RigSetupArtifactError as exc:
            raise RigBundleError("Could not render canonical RigIR setup") from exc
        bundle_sha = bundle_address_sha256(
            rig_sha, run_sha, probe_sha, setup.sha256
        )
        parent = self.root / project_id / "rig-ir"
        _prepare_parent(self.state_root, self.root, parent)
        rig_parent = _prepare_rig_parent(parent, rig_sha)
        destination = rig_parent / bundle_sha
        if destination.exists() or destination.is_symlink():
            self._verify(
                destination, rig, run_manifest, probe_report, setup,
                rig_sha=rig_sha, bundle_sha=bundle_sha,
            )
            return destination, rig_sha

        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{rig_sha[:12]}.{bundle_sha[:12]}.", dir=parent
            )
        )
        try:
            (staging / "layers").mkdir()
            for relative, (source, expected_sha) in assets.items():
                _copy_png(source, staging / relative, expected_sha)
            staged_setup = build_setup_artifact(project_id, rig, rig_sha, staging)
            if staged_setup != setup:
                raise RigBundleError("Copied layers changed the canonical setup render")
            _write_json(staging / "rig.json", rig)
            _write_json(staging / "run-manifest.json", run_manifest)
            _write_json(staging / "probes.json", probe_report)
            _write_json(staging / SETUP_DOCUMENT_NAME, setup.document)
            _write_bytes(staging / SETUP_IMAGE_NAME, setup.png)
            self._verify(
                staging,
                rig,
                run_manifest,
                probe_report,
                setup,
                rig_sha=rig_sha,
                bundle_sha=bundle_sha,
                require_content_address=False,
            )
            _fsync_directory(staging / "layers")
            _fsync_directory(staging)
            try:
                os.rename(staging, destination)
                staging = None
                _fsync_directory(rig_parent)
                _fsync_directory(parent)
            except OSError:
                if destination.is_symlink() or not destination.is_dir():
                    raise
                self._verify(
                    destination, rig, run_manifest, probe_report, setup,
                    rig_sha=rig_sha, bundle_sha=bundle_sha,
                )
        except RigBundleError:
            raise
        except (OSError, RigSetupArtifactError, TypeError, ValueError) as exc:
            raise RigBundleError("Could not publish RigIR bundle") from exc
        finally:
            if staging is not None and staging.is_dir():
                shutil.rmtree(staging)
        return destination, rig_sha

    @staticmethod
    def _verify(
        directory: Path,
        rig: Mapping[str, Any],
        run_manifest: Mapping[str, Any],
        probe_report: Mapping[str, Any],
        setup: RigSetupArtifact,
        *,
        rig_sha: str,
        bundle_sha: str,
        require_content_address: bool = True,
    ) -> None:
        expected_documents = {
            "rig.json": canonical_sha256(rig),
            "run-manifest.json": canonical_sha256(run_manifest),
            "probes.json": canonical_sha256(probe_report),
            SETUP_DOCUMENT_NAME: setup.sha256,
        }
        verified = verify_rig_bundle_directory(
            directory,
            require_content_address=require_content_address,
            expected_project_id=str(run_manifest.get("project_id") or ""),
        )
        actual_documents = {
            "rig.json": verified.rig_sha256,
            "run-manifest.json": verified.run_sha256,
            "probes.json": verified.probe_sha256,
            SETUP_DOCUMENT_NAME: verified.setup_sha256,
        }
        if actual_documents != expected_documents:
            raise RigBundleError("RigIR bundle documents differ from publication input")
        if verified.rig_sha256 != rig_sha or verified.bundle_sha256 != bundle_sha:
            raise RigBundleError("RigIR bundle has the wrong content address")


def _prepare_parent(state_root: Path, build_root: Path, parent: Path) -> None:
    if state_root.exists() and state_root.is_symlink():
        raise RigBundleError("State root cannot be a symlink")
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RigBundleError("Could not create RigIR bundle directory") from exc
    for path in (state_root, build_root, parent.parent, parent):
        if path.is_symlink() or not path.is_dir():
            raise RigBundleError("RigIR build path is unsafe")


def _prepare_rig_parent(parent: Path, rig_sha: str) -> Path:
    rig_parent = parent / required_sha(rig_sha, "RigIR")
    try:
        rig_parent.mkdir()
        _fsync_directory(parent)
    except FileExistsError:
        pass
    except OSError as exc:
        raise RigBundleError("Could not create RigIR content-address directory") from exc
    if rig_parent.is_symlink() or not rig_parent.is_dir():
        raise RigBundleError("RigIR content-address path is unsafe")
    try:
        children = list(rig_parent.iterdir())
    except OSError as exc:
        raise RigBundleError("Cannot inspect RigIR content-address directory") from exc
    for child in children:
        if child.is_symlink():
            raise RigBundleError("RigIR content-address directory contains a symlink")
        if child.is_file() or child.name in _DOCUMENT_NAMES | {"layers"}:
            raise RigBundleError("Legacy flat RigIR bundle cannot be reused")
        if not child.is_dir():
            raise RigBundleError("RigIR content-address directory has an unsafe entry")
        try:
            required_sha(child.name, "Rig bundle")
        except RigBundleError as exc:
            raise RigBundleError(
                "RigIR content-address directory has an unexpected entry"
            ) from exc
    return rig_parent


def _require_expected_layer_bundle(
    build_root: Path, project_id: str, digest: str, supplied: Path
) -> None:
    expected = build_root / project_id / "layer-manifests" / digest
    try:
        if expected.resolve(strict=True) != supplied.resolve(strict=True):
            raise RigBundleError("Layer Manifest bundle is outside the expected build path")
    except OSError as exc:
        raise RigBundleError("Layer Manifest bundle is outside the expected build path") from exc


def _copy_png(source: Path, target: Path, expected_sha: str) -> None:
    before = sha256_file(source)
    require_png(source)
    if before != expected_sha:
        raise RigBundleError(f"Layer changed before copying: {source.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    _fsync_file(target)
    _fsync_directory(target.parent)
    require_png(target)
    if sha256_file(target) != expected_sha or sha256_file(source) != before:
        raise RigBundleError(f"Layer changed while copying: {source.name}")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
    ) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _write_bytes(path: Path, value: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
