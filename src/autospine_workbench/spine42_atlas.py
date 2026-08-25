"""Deterministic, lossless single-page atlas boundary for Spine 4.2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .png_rgba import RgbaImage, RgbaPngError, decode_rgba_png, encode_rgba_png


ATLAS_PADDING = 2
ATLAS_MAX_SIZE = 4096
ATLAS_MAX_REGIONS = 4096

_REGION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}\.png$")


class Spine42AtlasError(ValueError):
    """Raised when exact RGBA regions cannot form the pinned atlas profile."""


@dataclass(frozen=True, slots=True)
class AtlasPlacement:
    """One unrotated, untrimmed region in top-left atlas coordinates."""

    name: str
    x: int
    y: int
    width: int
    height: int
    source_sha256: str

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "xy": [self.x, self.y],
            "size": [self.width, self.height],
            "orig": [self.width, self.height],
            "offset": [0, 0],
            "rotate": False,
            "index": -1,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True, slots=True)
class Spine42Atlas:
    """Immutable output of one deterministic single-page atlas build."""

    page_name: str
    width: int
    height: int
    padding: int
    png_bytes: bytes
    atlas_text: str
    placements: tuple[AtlasPlacement, ...]

    @property
    def atlas_bytes(self) -> bytes:
        return self.atlas_text.encode("utf-8")

    def placement_metadata(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.metadata() for item in self.placements)


@dataclass(frozen=True, slots=True)
class _SourceRegion:
    name: str
    image: RgbaImage
    source_sha256: str


def build_spine42_atlas(
    sources: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
    *,
    page_name: str = "atlas.png",
) -> Spine42Atlas:
    """Pack exact RGBA PNG snapshots without trimming, rotation, or aliases."""

    _require_page_name(page_name)
    regions = _decode_sources(sources)
    coordinates, width, height = _choose_shelf_layout(regions)
    placements = tuple(
        AtlasPlacement(
            name=region.name,
            x=coordinates[region.name][0],
            y=coordinates[region.name][1],
            width=region.image.width,
            height=region.image.height,
            source_sha256=region.source_sha256,
        )
        for region in sorted(regions, key=lambda item: item.name)
    )
    pixels = _compose(regions, coordinates, width, height)
    png_bytes = encode_rgba_png(RgbaImage(width, height, pixels))
    atlas_text = _format_atlas(page_name, width, height, placements)
    return Spine42Atlas(
        page_name=page_name,
        width=width,
        height=height,
        padding=ATLAS_PADDING,
        png_bytes=png_bytes,
        atlas_text=atlas_text,
        placements=placements,
    )


def _decode_sources(
    sources: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
) -> tuple[_SourceRegion, ...]:
    if isinstance(sources, (str, bytes, bytearray)):
        raise Spine42AtlasError("Atlas sources must be named PNG byte snapshots")
    try:
        items = list(sources.items() if isinstance(sources, Mapping) else sources)
    except (AttributeError, TypeError) as exc:
        raise Spine42AtlasError("Atlas sources must be a mapping or pair iterable") from exc
    if not items:
        raise Spine42AtlasError("Atlas must contain at least one region")
    if len(items) > ATLAS_MAX_REGIONS:
        raise Spine42AtlasError(f"Atlas exceeds {ATLAS_MAX_REGIONS} regions")

    seen: set[str] = set()
    seen_folded: set[str] = set()
    regions: list[_SourceRegion] = []
    total_pixels = 0
    for item in items:
        if not isinstance(item, tuple) or len(item) != 2:
            raise Spine42AtlasError("Every atlas source must be a (name, PNG bytes) pair")
        name, data = item
        _require_region_name(name)
        folded = name.casefold()
        if name in seen or folded in seen_folded:
            raise Spine42AtlasError(f"Duplicate or case-aliasing region name: {name}")
        if not isinstance(data, bytes):
            raise Spine42AtlasError(f"Region {name} PNG must be immutable bytes")
        try:
            image = decode_rgba_png(data, source_name=name)
        except RgbaPngError as exc:
            raise Spine42AtlasError(f"Region {name} is not an exact RGBA PNG: {exc}") from exc
        if image.width + 2 * ATLAS_PADDING > ATLAS_MAX_SIZE \
                or image.height + 2 * ATLAS_PADDING > ATLAS_MAX_SIZE:
            raise Spine42AtlasError(f"Region {name} cannot fit the {ATLAS_MAX_SIZE}px page")
        total_pixels += image.width * image.height
        if total_pixels > ATLAS_MAX_SIZE * ATLAS_MAX_SIZE:
            raise Spine42AtlasError("Region pixels exceed one maximum atlas page")
        seen.add(name)
        seen_folded.add(folded)
        regions.append(_SourceRegion(name, image, hashlib.sha256(data).hexdigest()))
    return tuple(regions)


def _choose_shelf_layout(
    regions: tuple[_SourceRegion, ...],
) -> tuple[dict[str, tuple[int, int]], int, int]:
    ordered = sorted(
        regions,
        key=lambda item: (-item.image.height, -item.image.width, item.name),
    )
    minimum_width = max(item.image.width + 2 * ATLAS_PADDING for item in ordered)
    best: tuple[tuple[int, int, int, int], dict[str, tuple[int, int]], int, int] | None = None
    for candidate_width in range(minimum_width, ATLAS_MAX_SIZE + 1):
        packed = _pack_shelves(ordered, candidate_width)
        if packed is None:
            continue
        coordinates, used_width, used_height = packed
        score = (
            used_width * used_height,
            max(used_width, used_height),
            used_width,
            used_height,
        )
        if best is None or score < best[0]:
            best = (score, coordinates, used_width, used_height)
    if best is None:
        raise Spine42AtlasError(f"Regions overflow one {ATLAS_MAX_SIZE}x{ATLAS_MAX_SIZE} page")
    return best[1], best[2], best[3]


def _pack_shelves(
    regions: list[_SourceRegion], candidate_width: int
) -> tuple[dict[str, tuple[int, int]], int, int] | None:
    x = y = ATLAS_PADDING
    shelf_height = 0
    used_width = 0
    coordinates: dict[str, tuple[int, int]] = {}
    for region in regions:
        if x + region.image.width + ATLAS_PADDING > candidate_width:
            x = ATLAS_PADDING
            y += shelf_height + ATLAS_PADDING
            shelf_height = 0
        if y + region.image.height + ATLAS_PADDING > ATLAS_MAX_SIZE:
            return None
        coordinates[region.name] = (x, y)
        used_width = max(used_width, x + region.image.width + ATLAS_PADDING)
        shelf_height = max(shelf_height, region.image.height)
        x += region.image.width + ATLAS_PADDING
    return coordinates, used_width, y + shelf_height + ATLAS_PADDING


def _compose(
    regions: tuple[_SourceRegion, ...],
    coordinates: dict[str, tuple[int, int]],
    width: int,
    height: int,
) -> bytes:
    output = bytearray(width * height * 4)
    for region in regions:
        x, y = coordinates[region.name]
        source_stride = region.image.width * 4
        for row in range(region.image.height):
            source_start = row * source_stride
            target_start = ((y + row) * width + x) * 4
            output[target_start : target_start + source_stride] = region.image.pixels[
                source_start : source_start + source_stride
            ]
    return bytes(output)


def _format_atlas(
    page_name: str,
    width: int,
    height: int,
    placements: tuple[AtlasPlacement, ...],
) -> str:
    lines = [
        page_name,
        f"size: {width},{height}",
        "format: RGBA8888",
        "filter: Linear,Linear",
        "repeat: none",
    ]
    for item in placements:
        lines.extend((
            item.name,
            "  rotate: false",
            f"  xy: {item.x}, {item.y}",
            f"  size: {item.width}, {item.height}",
            f"  orig: {item.width}, {item.height}",
            "  offset: 0, 0",
            "  index: -1",
        ))
    return "\n".join(lines) + "\n"


def _require_region_name(value: object) -> str:
    if not isinstance(value, str) or not _REGION_NAME.fullmatch(value):
        raise Spine42AtlasError("Region names must be safe ASCII attachment identifiers")
    return value


def _require_page_name(value: object) -> str:
    if not isinstance(value, str) or not _PAGE_NAME.fullmatch(value):
        raise Spine42AtlasError("Atlas page name must be a safe lowercase .png filename")
    return value
