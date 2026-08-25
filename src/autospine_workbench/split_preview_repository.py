"""Read-only repository for immutable split previews and their child images."""

from __future__ import annotations

from pathlib import Path
import re
import stat
from typing import Any, Mapping

from .manifest_artifacts import LayerManifestError, resolve_layer_artifact
from .manifest_bundle import LayerManifestBundleError, LayerManifestBundleReader
from .split_derivation_contract import SplitDerivationError, normalize_derivation
from .split_preview_reader import SplitPreviewReader, SplitPreviewReaderError


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ITEMS = 256
_MAX_LIST_BYTES = 64 * 1024 * 1024


class SplitPreviewRepositoryError(RuntimeError):
    """Raised when repository state cannot be safely trusted."""


class SplitPreviewNotFound(SplitPreviewRepositoryError):
    """Raised when a requested content address is absent or malformed."""


class SplitPreviewRepository:
    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self.root = self.state_root / "analysis"
        self.reader = SplitPreviewReader(self.state_root)

    def list(self, project_id: str) -> dict[str, Any]:
        directory = self._directory(project_id, required=False)
        if directory is None:
            artifacts: list[tuple[str, Mapping[str, Any]]] = []
        else:
            paths = self._safe_entries(directory)
            artifacts = [
                (path.stem, self._load(project_id, path.stem)) for path in paths
            ]
        return {
            "format": "autospine-split-preview-index/v1",
            "project_id": project_id,
            "kind": "split-previews",
            "count": len(artifacts),
            "items": [
                {
                    "artifact_sha256": digest,
                    "layer_id": document["layer_id"],
                    "resolved_snapshot_sha256": document[
                        "resolved_snapshot_sha256"
                    ],
                    "layer_manifest_sha256": document["layer_manifest_sha256"],
                    "review_target_sha256": document["review_target_sha256"],
                }
                for digest, document in artifacts
            ],
        }

    def read(self, project_id: str, digest: str) -> dict[str, Any]:
        self._require_artifact(project_id, digest)
        return dict(self._load(project_id, digest))

    def child_image(self, project_id: str, digest: str, side: str) -> Path:
        if side not in {"left", "right"}:
            raise ValueError("Split preview side must be left or right")
        preview = self.read(project_id, digest)
        try:
            bundle = LayerManifestBundleReader(self.state_root).load(
                project_id, preview["layer_manifest_sha256"]
            )
            child = _bound_child(preview, bundle.manifest, side)
            raster = child["raster"]
            return resolve_layer_artifact(
                bundle.path, child["layer_id"], raster["artifact_path"]
            )
        except (
            KeyError,
            LayerManifestBundleError,
            LayerManifestError,
            SplitDerivationError,
            TypeError,
            ValueError,
        ) as exc:
            raise SplitPreviewRepositoryError(
                "Referenced Layer Manifest bundle is invalid"
            ) from exc

    def _load(self, project_id: str, digest: str) -> Mapping[str, Any]:
        try:
            return self.reader.load(project_id, digest).document
        except SplitPreviewReaderError as exc:
            raise SplitPreviewRepositoryError(
                "Split preview artifact is invalid"
            ) from exc

    def _require_artifact(self, project_id: str, digest: str) -> Path:
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise SplitPreviewNotFound("Split preview was not found")
        directory = self._directory(project_id, required=False)
        if directory is None:
            raise SplitPreviewNotFound("Split preview was not found")
        path = directory / f"{digest}.json"
        if _is_path_alias(path):
            raise SplitPreviewRepositoryError("Split preview path is unsafe")
        if not path.exists():
            raise SplitPreviewNotFound("Split preview was not found")
        if not path.is_file():
            raise SplitPreviewRepositoryError("Split preview path is unsafe")
        return path

    def _directory(self, project_id: str, *, required: bool) -> Path | None:
        if not isinstance(project_id, str) or not _SAFE_ID.fullmatch(project_id):
            raise SplitPreviewNotFound("Split preview project was not found")
        project = self.root / project_id
        lexical = project / "split-previews"
        chain = (self.state_root, self.root, project, lexical)
        if any(_is_path_alias(path) for path in chain):
            raise SplitPreviewRepositoryError("Split preview directory is unsafe")
        if (self.root.exists() and not self.root.is_dir()) or (
            project.exists() and not project.is_dir()
        ):
            raise SplitPreviewRepositoryError("Split preview directory is unsafe")
        if not lexical.exists():
            if required:
                raise SplitPreviewNotFound("Split preview was not found")
            return None
        try:
            root = self.root.resolve(strict=True)
            resolved = lexical.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SplitPreviewRepositoryError(
                "Split preview directory is unsafe"
            ) from exc
        if not resolved.is_dir():
            raise SplitPreviewRepositoryError("Split preview directory is unsafe")
        return resolved

    @staticmethod
    def _safe_entries(directory: Path) -> list[Path]:
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
            total = sum(path.lstat().st_size for path in entries)
        except OSError as exc:
            raise SplitPreviewRepositoryError(
                "Split preview index cannot be enumerated"
            ) from exc
        if len(entries) > _MAX_ITEMS:
            raise SplitPreviewRepositoryError("Split preview index exceeds 256 items")
        if total > _MAX_LIST_BYTES:
            raise SplitPreviewRepositoryError("Split preview index exceeds 64 MiB")
        if any(
            _is_path_alias(path)
            or not path.is_file()
            or path.name != f"{path.stem}.json"
            or not _SHA256.fullmatch(path.stem)
            for path in entries
        ):
            raise SplitPreviewRepositoryError(
                "Split preview index contains an unsafe entry"
            )
        return entries


def _is_path_alias(path: Path) -> bool:
    """Recognize symlinks plus Windows junction/reparse aliases."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SplitPreviewRepositoryError("Split preview path is unsafe") from exc
    if stat.S_ISLNK(info.st_mode):
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return True
        except OSError as exc:
            raise SplitPreviewRepositoryError(
                "Split preview path is unsafe"
            ) from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _bound_child(
    preview: Mapping[str, Any], manifest: Mapping[str, Any], side: str
) -> Mapping[str, Any]:
    target = preview["review_target"]
    source_target = target["source"]
    part_target = target["parts"][side]
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise ValueError("Layer Manifest layers are invalid")
    by_id = {
        layer.get("layer_id"): layer
        for layer in layers
        if isinstance(layer, Mapping) and isinstance(layer.get("layer_id"), str)
    }
    if len(by_id) != len(layers):
        raise ValueError("Layer Manifest layer ids are invalid")
    parent = by_id.get(source_target["layer_id"])
    child = by_id.get(part_target["layer_id"])
    if parent is None or child is None:
        raise ValueError("Preview layers are absent from the Layer Manifest")
    parent_raster = parent.get("raster") or {}
    parent_semantic = parent.get("semantic") or {}
    child_raster = child.get("raster") or {}
    child_semantic = child.get("semantic") or {}
    hint = child.get("rig_hint") or {}
    derivation = normalize_derivation(str(child["layer_id"]), child.get("derivation"))
    config = derivation.get("operation_config") or {}
    expected_parent = {
        "layer_id": source_target["layer_id"],
        "canonical_role": source_target["canonical_role"],
        "raster_sha256": source_target["raster_sha256"],
        "rgba_sha256": source_target["rgba_sha256"],
    }
    observed_parent = {
        "layer_id": parent.get("layer_id"),
        "canonical_role": parent_semantic.get("canonical_role"),
        "raster_sha256": parent_raster.get("sha256"),
        "rgba_sha256": config.get("source_rgba_sha256"),
    }
    observed_part = {
        "layer_id": child.get("layer_id"),
        "side": child_semantic.get("side"),
        "pivot_xy": (hint.get("pivot") or {}).get("xy"),
        "candidate_bone": hint.get("candidate_bone"),
        "setup_draw_order": hint.get("setup_draw_order"),
        "raster_sha256": child_raster.get("sha256"),
    }
    operation = target["operation"]
    if (
        observed_parent != expected_parent
        or observed_part != part_target
        or child_semantic.get("canonical_role") != source_target["canonical_role"]
        or derivation.get("operation_config_sha256")
        != preview["operation_config_sha256"]
        or config.get("output_rgba_sha256") != operation["output_rgba_sha256"]
    ):
        raise ValueError("Preview target differs from the Layer Manifest")
    return child
