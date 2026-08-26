"""Cross-file validation for one minimum Spine 4.2 export."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import re
from typing import Any

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .png_rgba import RgbaPngError, decode_rgba_png
from .spine42_atlas import ATLAS_MAX_REGIONS, ATLAS_MAX_SIZE
from .spine42_contract import SPINE_JSON_VERSION, Spine42ContractError, canonical_spine42_json


MAX_SKELETON_JSON_BYTES = 32 * 1024 * 1024
MAX_ATLAS_BYTES = 4 * 1024 * 1024
MAX_ATLAS_PNG_BYTES = 72 * 1024 * 1024

_PAIR = re.compile(r"^(\d+), (\d+)$")
_SIZE = re.compile(r"^(\d+),(\d+)$")


class Spine42ExportValidationError(ValueError):
    """Raised when the JSON, atlas, PNG, or source identities disagree."""


@dataclass(frozen=True, slots=True)
class ValidatedSpine42Export:
    skeleton_json_bytes: bytes = field(repr=False)
    atlas_bytes: bytes = field(repr=False)
    png_bytes: bytes = field(repr=False)
    source_images: tuple[tuple[str, str], ...]
    attachment_paths: tuple[str, ...]
    atlas_width: int
    atlas_height: int
    bone_count: int
    slot_count: int
    attachment_count: int
    animation_count: int
    event_count: int


def validate_spine42_export(
    skeleton_json: Mapping[str, Any],
    atlas_bytes: bytes,
    png_bytes: bytes,
    source_image_sha256s: Mapping[str, str],
    *,
    expected_skeleton_hash: str,
    clip_id: str | None,
) -> ValidatedSpine42Export:
    """Validate all five cross-file relationships before evidence is built."""

    try:
        document_bytes = canonical_spine42_json(skeleton_json)
        if len(document_bytes) > MAX_SKELETON_JSON_BYTES:
            raise Spine42ExportValidationError("Spine JSON exceeds its byte limit")
        document = json.loads(document_bytes)
        skeleton = _object(document.get("skeleton"), "skeleton metadata")
        if skeleton.get("spine") != SPINE_JSON_VERSION:
            raise Spine42ExportValidationError("Skeleton is not pinned to Spine 4.2")
        if skeleton.get("hash") != expected_skeleton_hash:
            raise Spine42ExportValidationError("Skeleton source hash binding differs")
        bones = _array(document.get("bones"), "bones")
        slots = _array(document.get("slots"), "slots")
        animations = _object(document.get("animations"), "animations")
        events = _object(document.get("events"), "events")
        _bounded_count(bones, "bones", minimum=1, maximum=4096)
        _bounded_count(slots, "slots", minimum=1, maximum=4096)
        _bounded_count(events, "events", minimum=0, maximum=4096)
        _require_motion_mode(animations, clip_id)
        paths, region_sizes, attachment_count = _attachment_inventory(document)
        if attachment_count > 16_384:
            raise Spine42ExportValidationError("Skeleton has too many attachments")
        source_items = _source_inventory(source_image_sha256s, paths)
        atlas_width, atlas_height, atlas_regions = (
            require_spine42_atlas_inventory(atlas_bytes)
        )
        if set(atlas_regions) != set(paths):
            raise Spine42ExportValidationError(
                "Spine attachment paths differ from atlas regions"
            )
        for path, size in region_sizes.items():
            if atlas_regions[path][2:] != size:
                raise Spine42ExportValidationError(
                    f"Region attachment size differs from atlas: {path}"
                )
        _validate_png(png_bytes, atlas_width, atlas_height)
        return ValidatedSpine42Export(
            document_bytes, atlas_bytes, png_bytes, source_items, paths,
            atlas_width, atlas_height, len(bones), len(slots), attachment_count,
            len(animations), len(events),
        )
    except Spine42ExportValidationError:
        raise
    except (
        json.JSONDecodeError, LayerManifestError, RgbaPngError,
        Spine42ContractError, KeyError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42ExportValidationError(
            f"Spine 4.2 export validation failed: {exc}"
        ) from exc


def _require_motion_mode(animations: Mapping[str, Any], clip_id: str | None) -> None:
    expected = set() if clip_id is None else {require_safe_token(clip_id, "Clip id")}
    if set(animations) != expected:
        raise Spine42ExportValidationError(
            "Skeleton animations differ from the declared export mode"
        )


def _attachment_inventory(document: Mapping[str, Any]):
    skins = _array(document.get("skins"), "skins")
    paths: set[str] = set()
    folded: set[str] = set()
    region_sizes: dict[str, tuple[int, int]] = {}
    count = 0
    for skin in skins:
        attachments = _object(_object(skin, "skin").get("attachments"), "attachments")
        for slot_values in attachments.values():
            for name, raw in _object(slot_values, "slot attachments").items():
                attachment = _object(raw, "attachment")
                path = require_safe_token(attachment.get("path", name), "Attachment path")
                if path.casefold() in folded and path not in paths:
                    raise Spine42ExportValidationError("Attachment paths contain a case alias")
                paths.add(path)
                folded.add(path.casefold())
                count += 1
                if attachment.get("type", "region") == "region":
                    size = (_positive_int(attachment.get("width"), "region width"),
                            _positive_int(attachment.get("height"), "region height"))
                    prior = region_sizes.setdefault(path, size)
                    if prior != size:
                        raise Spine42ExportValidationError(
                            f"Shared region path has inconsistent dimensions: {path}"
                        )
    if not paths:
        raise Spine42ExportValidationError("Skeleton has no atlas attachments")
    return tuple(sorted(paths)), region_sizes, count


def _source_inventory(value: Mapping[str, str], paths: tuple[str, ...]):
    if not isinstance(value, Mapping):
        raise Spine42ExportValidationError("Source image hashes must be an object")
    items: list[tuple[str, str]] = []
    folded: set[str] = set()
    for raw_path, raw_sha in value.items():
        path = require_safe_token(raw_path, "Source image path")
        if path.casefold() in folded:
            raise Spine42ExportValidationError("Source image paths contain an alias")
        folded.add(path.casefold())
        items.append((path, require_sha256(raw_sha, f"Source image {path} SHA-256")))
    items.sort()
    if tuple(path for path, _sha in items) != paths:
        raise Spine42ExportValidationError(
            "Source image hash inventory differs from attachment paths"
        )
    return tuple(items)


def require_spine42_atlas_inventory(data: bytes):
    """Parse and strictly validate one canonical pinned atlas inventory."""

    if type(data) is not bytes or len(data) > MAX_ATLAS_BYTES:
        raise Spine42ExportValidationError("Atlas must be bounded immutable bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Spine42ExportValidationError("Atlas is not UTF-8 text") from exc
    if not text.endswith("\n") or "\r" in text or text.encode("utf-8") != data:
        raise Spine42ExportValidationError("Atlas text encoding is not canonical")
    lines = text[:-1].split("\n")
    if len(lines) < 12 or (len(lines) - 5) % 7:
        raise Spine42ExportValidationError("Atlas inventory shape is invalid")
    if (len(lines) - 5) // 7 > ATLAS_MAX_REGIONS:
        raise Spine42ExportValidationError("Atlas region count is invalid")
    size = _match_pair(_SIZE, lines[1].removeprefix("size: "), "atlas size")
    if lines[:1] != ["skeleton.png"] or lines[1] != f"size: {size[0]},{size[1]}" \
            or lines[2:5] != ["format: RGBA8888", "filter: Linear,Linear", "repeat: none"]:
        raise Spine42ExportValidationError("Atlas page header is not the pinned profile")
    if max(size) > ATLAS_MAX_SIZE or min(size) < 1:
        raise Spine42ExportValidationError("Atlas page dimensions are invalid")
    regions: dict[str, tuple[int, int, int, int]] = {}
    folded: set[str] = set()
    for start in range(5, len(lines), 7):
        block = lines[start:start + 7]
        name = require_safe_token(block[0], "Atlas region")
        folded_name = name.casefold()
        if folded_name in folded:
            raise Spine42ExportValidationError("Atlas region is duplicated or aliased")
        folded.add(folded_name)
        xy = _prefixed_pair(block[2], "  xy: ", "region position")
        wh = _prefixed_pair(block[3], "  size: ", "region size")
        if block[1] != "  rotate: false" or block[4] != f"  orig: {wh[0]}, {wh[1]}" \
                or block[5:] != ["  offset: 0, 0", "  index: -1"]:
            raise Spine42ExportValidationError(f"Atlas region metadata differs: {name}")
        if min(wh) < 1 or xy[0] + wh[0] > size[0] or xy[1] + wh[1] > size[1]:
            raise Spine42ExportValidationError(f"Atlas region is outside its page: {name}")
        regions[name] = (*xy, *wh)
    if list(regions) != sorted(regions):
        raise Spine42ExportValidationError("Atlas regions are not canonical and sorted")
    _require_nonoverlap(regions)
    return size[0], size[1], regions


def _validate_png(data: bytes, width: int, height: int) -> None:
    if type(data) is not bytes or len(data) > MAX_ATLAS_PNG_BYTES:
        raise Spine42ExportValidationError("Atlas PNG must be bounded immutable bytes")
    image = decode_rgba_png(data, source_name="skeleton.png")
    if (image.width, image.height) != (width, height):
        raise Spine42ExportValidationError("Atlas page and PNG dimensions differ")


def _require_nonoverlap(regions: Mapping[str, tuple[int, int, int, int]]) -> None:
    values = list(regions.items())
    for index, (left_name, (lx, ly, lw, lh)) in enumerate(values):
        for right_name, (rx, ry, rw, rh) in values[index + 1:]:
            if lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh:
                raise Spine42ExportValidationError(
                    f"Atlas regions overlap: {left_name}, {right_name}"
                )


def _prefixed_pair(value: str, prefix: str, label: str) -> tuple[int, int]:
    if not value.startswith(prefix):
        raise Spine42ExportValidationError(f"{label} is invalid")
    return _match_pair(_PAIR, value[len(prefix):], label)


def _match_pair(pattern: re.Pattern[str], value: str, label: str) -> tuple[int, int]:
    match = pattern.fullmatch(value)
    if match is None:
        raise Spine42ExportValidationError(f"{label} is invalid")
    return int(match.group(1)), int(match.group(2))


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise Spine42ExportValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise Spine42ExportValidationError(f"{label} must be an array")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not float(value).is_integer() or value < 1:
        raise Spine42ExportValidationError(f"{label} must be a positive integer")
    return int(value)


def _bounded_count(value: Any, label: str, *, minimum: int, maximum: int) -> None:
    count = len(value)
    if count < minimum or count > maximum:
        raise Spine42ExportValidationError(f"Skeleton {label} count is invalid")
