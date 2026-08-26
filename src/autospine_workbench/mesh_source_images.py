"""Fail-closed P6 boundary for exact P3 rigs and original RGBA images."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    canonical_layer_artifact_path,
    require_safe_token,
    require_sha256,
)
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .png_rgba import RgbaPngError, decode_rgba_png


class VerifiedMeshSourceReaderError(RuntimeError):
    """The exact P3 bundle cannot supply a complete trusted image inventory."""


@dataclass(frozen=True, slots=True)
class VerifiedAttachmentImage:
    """One immutable attachment-to-original-PNG binding."""

    attachment_id: str
    image_path: str
    image_sha256: str
    width: int
    height: int
    _png_bytes: bytes = field(repr=False)

    @property
    def png_bytes(self) -> bytes:
        return self._png_bytes


@dataclass(frozen=True, slots=True)
class VerifiedMeshSource:
    """Copy-isolated rig plus exact, path-bound source images for an adapter."""

    path: Path
    project_id: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    base_rig_sha256: str
    base_bundle_sha256: str
    _rig_json: str = field(repr=False)
    _images: tuple[VerifiedAttachmentImage, ...] = field(repr=False)

    @property
    def p3_address(self) -> tuple[str, str, str]:
        return self.project_id, self.p3_rig_sha256, self.p3_bundle_sha256

    @property
    def rig(self) -> dict[str, Any]:
        return json.loads(self._rig_json)

    @property
    def images(self) -> tuple[VerifiedAttachmentImage, ...]:
        return self._images

    @property
    def image_by_attachment(self) -> dict[str, VerifiedAttachmentImage]:
        return {item.attachment_id: item for item in self._images}

    @property
    def png_by_attachment(self) -> dict[str, bytes]:
        return {item.attachment_id: item.png_bytes for item in self._images}


@dataclass(frozen=True, slots=True)
class VerifiedMeshSourceReader:
    """Load one explicit P3 address; never scan for aliases or latest builds."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        p3_rig_sha256: str,
        p3_bundle_sha256: str,
    ) -> VerifiedMeshSource:
        try:
            verified = VerifiedMeshBundleReader(self.state_root).load(
                project_id, p3_rig_sha256, p3_bundle_sha256
            )
            rig = verified.rig
            images = verified_attachment_images(rig, verified.source_pngs)
            return VerifiedMeshSource(
                path=verified.path,
                project_id=verified.project_id,
                p3_rig_sha256=verified.rig_sha256,
                p3_bundle_sha256=verified.bundle_sha256,
                base_rig_sha256=verified.base_rig_sha256,
                base_bundle_sha256=verified.base_bundle_sha256,
                _rig_json=_canonical_json(rig),
                _images=images,
            )
        except VerifiedMeshSourceReaderError:
            raise
        except (
            VerifiedMeshBundleReaderError, LayerManifestError, RgbaPngError,
            UnicodeError, RuntimeError, TypeError, ValueError, KeyError, OverflowError,
        ) as exc:
            raise VerifiedMeshSourceReaderError(
                f"Verified mesh source load failed: {exc}"
            ) from exc


def verified_attachment_images(
    rig: Mapping[str, Any], png_by_path: Mapping[str, bytes]
) -> tuple[VerifiedAttachmentImage, ...]:
    """Validate one detached rig and its exact original PNG snapshots."""

    attachments = _objects(rig.get("attachments"), "RigIR attachments")
    canvas = _canvas(rig.get("canvas"))
    if not isinstance(png_by_path, Mapping):
        raise VerifiedMeshSourceReaderError("Source PNG snapshots must be an object")
    snapshots: dict[str, bytes] = {}
    folded_paths: set[str] = set()
    for path, raw in png_by_path.items():
        if not isinstance(path, str) or not isinstance(raw, bytes):
            raise VerifiedMeshSourceReaderError("Source PNG snapshot is invalid")
        if path.casefold() in folded_paths:
            raise VerifiedMeshSourceReaderError("Source PNG paths are case aliases")
        folded_paths.add(path.casefold())
        snapshots[path] = raw

    result: list[VerifiedAttachmentImage] = []
    ids: set[str] = set()
    expected_paths: set[str] = set()
    expected_folded: set[str] = set()
    for attachment in attachments:
        identifier = require_safe_token(attachment.get("id"), "Attachment id")
        if identifier.casefold() in ids:
            raise VerifiedMeshSourceReaderError("Attachment ids are case aliases")
        ids.add(identifier.casefold())
        image_path = _canonical_image_path(attachment)
        if image_path.casefold() in expected_folded:
            raise VerifiedMeshSourceReaderError("Attachment image paths are duplicated")
        expected_paths.add(image_path)
        expected_folded.add(image_path.casefold())
        digest = require_sha256(
            attachment.get("image_sha256"), f"Attachment {identifier} image"
        )
        raw = snapshots.get(image_path)
        if raw is None or hashlib.sha256(raw).hexdigest() != digest:
            raise VerifiedMeshSourceReaderError(
                f"Attachment image hash differs: {identifier}"
            )
        decoded = decode_rgba_png(raw, source_name=image_path)
        _require_raster_bounds(attachment, decoded.width, decoded.height, canvas)
        result.append(VerifiedAttachmentImage(
            attachment_id=identifier,
            image_path=image_path,
            image_sha256=digest,
            width=decoded.width,
            height=decoded.height,
            _png_bytes=raw,
        ))
    if set(snapshots) != expected_paths:
        raise VerifiedMeshSourceReaderError(
            "Source PNG inventory differs from P3 attachments"
        )
    return tuple(sorted(result, key=lambda item: item.attachment_id))


def _canonical_image_path(attachment: Mapping[str, Any]) -> str:
    source_ids = attachment.get("source_layer_ids")
    if (
        not isinstance(source_ids, list)
        or len(source_ids) != 1
        or not isinstance(source_ids[0], str)
    ):
        raise VerifiedMeshSourceReaderError("Attachment source identity is invalid")
    source_id = require_safe_token(source_ids[0], "Attachment source layer")
    expected = canonical_layer_artifact_path(source_id)
    if attachment.get("image_path") != expected:
        raise VerifiedMeshSourceReaderError("Attachment image path is not canonical")
    return expected


def _require_raster_bounds(
    attachment: Mapping[str, Any],
    width: int,
    height: int,
    canvas: tuple[int, int],
) -> None:
    offset = _integer_pair(attachment.get("canvas_offset_xy"), "canvas offset")
    if (
        offset[0] < 0
        or offset[1] < 0
        or offset[0] + width > canvas[0]
        or offset[1] + height > canvas[1]
    ):
        raise VerifiedMeshSourceReaderError("Attachment raster escapes the canvas")
    kind = attachment.get("type")
    if kind == "region":
        if _integer_pair(attachment.get("size"), "region size") != (width, height):
            raise VerifiedMeshSourceReaderError("Region size differs from its PNG")
        return
    if kind != "mesh":
        raise VerifiedMeshSourceReaderError("Attachment type is unsupported")
    vertices = _pairs(attachment.get("vertices"), "mesh vertices")
    uvs = _pairs(attachment.get("uvs"), "mesh UVs")
    if not vertices or len(vertices) != len(uvs):
        raise VerifiedMeshSourceReaderError("Mesh raster coordinates are incomplete")
    if any(not 0 <= point[0] <= width or not 0 <= point[1] <= height for point in vertices):
        raise VerifiedMeshSourceReaderError("Mesh vertex escapes its source PNG")
    if any(not 0 <= point[0] <= 1 or not 0 <= point[1] <= 1 for point in uvs):
        raise VerifiedMeshSourceReaderError("Mesh UV escapes its source PNG")


def _canvas(value: Any) -> tuple[int, int]:
    if not isinstance(value, Mapping):
        raise VerifiedMeshSourceReaderError("RigIR canvas is invalid")
    return _positive_pair([value.get("width"), value.get("height")], "canvas")


def _integer_pair(value: Any, label: str) -> tuple[int, int]:
    pair = _sequence_pair(value, label)
    if any(type(item) is not int for item in pair):
        raise VerifiedMeshSourceReaderError(f"Attachment {label} is invalid")
    return int(pair[0]), int(pair[1])


def _positive_pair(value: Any, label: str) -> tuple[int, int]:
    pair = _integer_pair(value, label)
    if any(item < 1 for item in pair):
        raise VerifiedMeshSourceReaderError(f"Attachment {label} is invalid")
    return pair


def _pairs(value: Any, label: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list):
        raise VerifiedMeshSourceReaderError(f"Attachment {label} is invalid")
    result = []
    for item in value:
        pair = _sequence_pair(item, label)
        if any(isinstance(number, bool) or not isinstance(number, (int, float))
               or not math.isfinite(float(number)) for number in pair):
            raise VerifiedMeshSourceReaderError(f"Attachment {label} is invalid")
        result.append((float(pair[0]), float(pair[1])))
    return tuple(result)


def _sequence_pair(value: Any, label: str) -> tuple[Any, Any]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 2
    ):
        raise VerifiedMeshSourceReaderError(f"Attachment {label} is invalid")
    return value[0], value[1]


def _objects(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise VerifiedMeshSourceReaderError(f"{label} must be an object array")
    return tuple(value)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))
