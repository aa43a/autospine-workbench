"""Dependency-free setup compositor for region-only RigIR probes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .png_rgba import RgbaPngError, read_rgba_png


class RigSetupRenderError(RuntimeError):
    """Raised when setup pixels cannot be reconstructed without guessing."""


@dataclass(frozen=True, slots=True)
class SetupPixelComparison:
    width: int
    height: int
    exact: bool
    differing_pixels: int
    differing_channels: int
    max_abs: int
    mae: float
    manifest_rgba_sha256: str
    rig_rgba_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_region_setup(
    manifest: Mapping[str, Any], rig: Mapping[str, Any], bundle_path: Path
) -> SetupPixelComparison:
    width, height = _manifest_canvas(manifest)
    rig_canvas = rig.get("canvas") or {}
    if (rig_canvas.get("width"), rig_canvas.get("height")) != (width, height):
        raise RigSetupRenderError("RigIR canvas does not match Layer Manifest")
    expected = render_manifest_setup(manifest, bundle_path)
    observed = render_rig_setup(rig, bundle_path)
    differences = [abs(left - right) for left, right in zip(expected, observed)]
    differing_channels = sum(value != 0 for value in differences)
    differing_pixels = sum(
        any(differences[index : index + 4])
        for index in range(0, len(differences), 4)
    )
    return SetupPixelComparison(
        width=width,
        height=height,
        exact=differing_channels == 0,
        differing_pixels=differing_pixels,
        differing_channels=differing_channels,
        max_abs=max(differences, default=0),
        mae=round(sum(differences) / max(1, len(differences)), 8),
        manifest_rgba_sha256=hashlib.sha256(expected).hexdigest(),
        rig_rgba_sha256=hashlib.sha256(observed).hexdigest(),
    )


def render_manifest_setup(manifest: Mapping[str, Any], bundle_path: Path) -> bytes:
    width, height = _manifest_canvas(manifest)
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise RigSetupRenderError("Layer Manifest has no layers")
    ordered = sorted(layers, key=_manifest_draw_order)
    canvas = bytearray(width * height * 4)
    for layer in ordered:
        if not isinstance(layer, Mapping):
            raise RigSetupRenderError("Layer Manifest contains an invalid layer")
        source = layer.get("source") or {}
        hint = layer.get("rig_hint") or {}
        if hint.get("attachment_kind") == "excluded" or not source.get("visible"):
            continue
        if hint.get("attachment_kind") != "region":
            raise RigSetupRenderError("Setup compositor only supports region layers")
        if source.get("blend_mode") != "normal":
            raise RigSetupRenderError("Setup compositor only supports normal blend")
        raster = layer.get("raster") or {}
        image = _load_image(bundle_path, raster.get("artifact_path"))
        opacity = _opacity_u8(source.get("opacity"))
        _draw(
            canvas,
            width,
            height,
            image.pixels,
            image.width,
            image.height,
            raster.get("canvas_offset_xy"),
            (255, 255, 255, opacity),
        )
    return bytes(canvas)


def render_rig_setup(rig: Mapping[str, Any], bundle_path: Path) -> bytes:
    canvas_spec = rig.get("canvas") or {}
    width, height = _positive_int(canvas_spec.get("width")), _positive_int(
        canvas_spec.get("height")
    )
    attachments = _unique_by_id(rig.get("attachments"), "attachment")
    slots = rig.get("slots")
    if not isinstance(slots, list):
        raise RigSetupRenderError("RigIR has no slots")
    canvas = bytearray(width * height * 4)
    for slot in sorted(slots, key=_rig_draw_order):
        if not isinstance(slot, Mapping):
            raise RigSetupRenderError("RigIR contains an invalid slot")
        attachment_id = slot.get("setup_attachment")
        if attachment_id is None:
            continue
        attachment = attachments.get(attachment_id)
        if attachment is None or attachment.get("slot") != slot.get("id"):
            raise RigSetupRenderError("RigIR setup attachment binding is invalid")
        if attachment.get("type") != "region":
            raise RigSetupRenderError("Setup compositor only supports region attachments")
        if slot.get("blend") != "normal":
            raise RigSetupRenderError("Setup compositor only supports normal blend")
        image = _load_image(bundle_path, attachment.get("image_path"))
        size = attachment.get("size")
        if list(size or []) != [image.width, image.height]:
            raise RigSetupRenderError("Region attachment size does not match its PNG")
        _draw(
            canvas,
            width,
            height,
            image.pixels,
            image.width,
            image.height,
            attachment.get("canvas_offset_xy"),
            _rgba(slot.get("color_rgba")),
        )
    return bytes(canvas)


def _draw(
    canvas: bytearray,
    canvas_width: int,
    canvas_height: int,
    pixels: bytes,
    image_width: int,
    image_height: int,
    offset: Any,
    tint: tuple[int, int, int, int],
) -> None:
    x0, y0 = _integer_point(offset)
    if x0 < 0 or y0 < 0 or x0 + image_width > canvas_width or y0 + image_height > canvas_height:
        raise RigSetupRenderError("Region image extends outside the setup canvas")
    for y in range(image_height):
        source_row = y * image_width * 4
        target_row = ((y0 + y) * canvas_width + x0) * 4
        for x in range(image_width):
            source = source_row + x * 4
            target = target_row + x * 4
            _source_over(canvas, target, pixels, source, tint)


def _source_over(
    canvas: bytearray,
    target: int,
    source: bytes,
    offset: int,
    tint: tuple[int, int, int, int],
) -> None:
    source_alpha = (source[offset + 3] * tint[3] + 127) // 255
    destination_alpha = canvas[target + 3]
    output_alpha = source_alpha + (destination_alpha * (255 - source_alpha) + 127) // 255
    for channel in range(3):
        color = (source[offset + channel] * tint[channel] + 127) // 255
        premultiplied = color * source_alpha + (
            canvas[target + channel] * destination_alpha * (255 - source_alpha) + 127
        ) // 255
        canvas[target + channel] = (
            (premultiplied + output_alpha // 2) // output_alpha if output_alpha else 0
        )
    canvas[target + 3] = output_alpha


def _load_image(bundle_path: Path, relative: Any):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise RigSetupRenderError("Region image path is unsafe")
    root = Path(bundle_path).resolve(strict=True)
    lexical = root / relative
    try:
        path = lexical.resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RigSetupRenderError("Region image is outside the manifest bundle") from exc
    if lexical.is_symlink() or not path.is_file():
        raise RigSetupRenderError("Region image path is unsafe")
    try:
        return read_rgba_png(path)
    except RgbaPngError as exc:
        raise RigSetupRenderError(str(exc)) from exc


def _manifest_canvas(manifest: Mapping[str, Any]) -> tuple[int, int]:
    canvas = (manifest.get("source") or {}).get("canvas")
    if not isinstance(canvas, Sequence) or isinstance(canvas, (str, bytes)) or len(canvas) != 2:
        raise RigSetupRenderError("Layer Manifest canvas is invalid")
    return _positive_int(canvas[0]), _positive_int(canvas[1])


def _manifest_draw_order(layer: Any) -> int:
    if not isinstance(layer, Mapping):
        raise RigSetupRenderError("Layer Manifest contains an invalid layer")
    value = (layer.get("rig_hint") or {}).get("setup_draw_order")
    return _integer(value, "Layer draw order")


def _rig_draw_order(slot: Any) -> int:
    if not isinstance(slot, Mapping):
        raise RigSetupRenderError("RigIR contains an invalid slot")
    return _integer(slot.get("setup_draw_order"), "Slot draw order")


def _unique_by_id(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise RigSetupRenderError(f"RigIR has no {label}s")
    result: dict[str, Mapping[str, Any]] = {}
    for item in value:
        item_id = item.get("id") if isinstance(item, Mapping) else None
        if not isinstance(item_id, str) or item_id in result:
            raise RigSetupRenderError(f"RigIR contains an invalid {label} id")
        result[item_id] = item
    return result


def _rgba(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, str) or len(value) != 8:
        raise RigSetupRenderError("Slot color is invalid")
    try:
        return tuple(int(value[index : index + 2], 16) for index in range(0, 8, 2))
    except ValueError as exc:
        raise RigSetupRenderError("Slot color is invalid") from exc


def _opacity_u8(value: Any) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise RigSetupRenderError("Layer opacity is invalid")
    if value < 0 or value > 1:
        raise RigSetupRenderError("Layer opacity is invalid")
    return int(float(value) * 255 + 0.5)


def _integer_point(value: Any) -> tuple[int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise RigSetupRenderError("Region canvas offset is invalid")
    return _integer(value[0], "Region x offset"), _integer(value[1], "Region y offset")


def _positive_int(value: Any) -> int:
    result = _integer(value, "Canvas dimension")
    if result < 1:
        raise RigSetupRenderError("Canvas dimension must be positive")
    return result


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RigSetupRenderError(f"{label} must be an integer")
    return value
