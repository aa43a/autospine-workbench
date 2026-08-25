"""Immutable publication of a validated RigIR setup bundle."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Mapping

from .layer_manifest import sha256_file
from .resolved_project import canonical_sha256
from .rig_bundle_validation import (
    RigBundleError,
    read_json,
    require_png,
    safe_existing_file,
    validate_bundle_inputs,
)


_DOCUMENT_NAMES = {"rig.json", "run-manifest.json", "probes.json"}


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
        rig_sha, assets = validate_bundle_inputs(
            project_id, rig, run_manifest, probe_report, Path(layer_bundle_path)
        )
        _require_expected_layer_bundle(
            self.root,
            project_id,
            rig["source"]["layer_manifest_sha256"],
            Path(layer_bundle_path),
        )
        parent = self.root / project_id / "rig-ir"
        _prepare_parent(self.state_root, self.root, parent)
        destination = parent / rig_sha
        if destination.exists() or destination.is_symlink():
            self._verify(destination, rig, run_manifest, probe_report, assets)
            return destination, rig_sha

        staging = Path(tempfile.mkdtemp(prefix=f".{rig_sha[:12]}.", dir=parent))
        try:
            (staging / "layers").mkdir()
            for relative, (source, expected_sha) in assets.items():
                _copy_png(source, staging / relative, expected_sha)
            _write_json(staging / "rig.json", rig)
            _write_json(staging / "run-manifest.json", run_manifest)
            _write_json(staging / "probes.json", probe_report)
            _fsync_directory(staging / "layers")
            _fsync_directory(staging)
            try:
                os.rename(staging, destination)
                staging = None
                _fsync_directory(parent)
            except OSError:
                if destination.is_symlink() or not destination.is_dir():
                    raise
                self._verify(destination, rig, run_manifest, probe_report, assets)
        except RigBundleError:
            raise
        except (OSError, TypeError, ValueError) as exc:
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
        assets: Mapping[str, tuple[Path, str]],
    ) -> None:
        if directory.is_symlink() or not directory.is_dir():
            raise RigBundleError("Existing RigIR bundle is not a real directory")
        expected_documents = {
            "rig.json": canonical_sha256(rig),
            "run-manifest.json": canonical_sha256(run_manifest),
            "probes.json": canonical_sha256(probe_report),
        }
        for name, digest in expected_documents.items():
            if canonical_sha256(read_json(directory / name)) != digest:
                raise RigBundleError(f"Existing {name} does not match publication input")
        if expected_documents["rig.json"] != directory.name:
            raise RigBundleError("Existing RigIR directory has the wrong content address")

        expected_files = _DOCUMENT_NAMES | set(assets)
        expected_directories = {"layers"}
        for relative in assets:
            parent = PurePosixPath(relative).parent
            while parent.as_posix() != ".":
                expected_directories.add(parent.as_posix())
                parent = parent.parent
        observed_files: set[str] = set()
        observed_directories: set[str] = set()
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise RigBundleError("Existing RigIR bundle contains a symlink")
            if path.is_file():
                observed_files.add(path.relative_to(directory).as_posix())
            elif path.is_dir():
                observed_directories.add(path.relative_to(directory).as_posix())
        if observed_files != expected_files or observed_directories != expected_directories:
            raise RigBundleError("Existing RigIR bundle has missing or unexpected files")
        for relative, (_, digest) in assets.items():
            target = safe_existing_file(directory, relative)
            require_png(target)
            if sha256_file(target) != digest:
                raise RigBundleError(f"Existing layer hash mismatch: {relative}")


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
