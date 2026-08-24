"""Representation-aware comparison for 8-bit RGBA PNG composites."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import struct
import zlib

try:  # Optional acceleration; the dependency-free decoder remains authoritative.
    import numpy as _np
except ImportError:  # pragma: no cover - exercised in minimal runtime environments
    _np = None

try:
    from PIL import Image as _PillowImage
except ImportError:  # pragma: no cover - exercised in minimal runtime environments
    _PillowImage = None


class CompositeQualityError(RuntimeError):
    """Raised when images cannot be compared without guessing a conversion."""


class CompositeQualityCache:
    """Cache immutable audit comparisons by audit content hash."""

    def __init__(self) -> None:
        self._metrics: dict[str, dict] = {}

    def measure(
        self,
        audit_sha256: str,
        raw_rgba_mae: float,
        composite_path: Path | None,
        embedded_path: Path | None,
    ) -> dict:
        cached = self._metrics.get(audit_sha256)
        if cached is not None:
            return cached
        try:
            if composite_path is None or embedded_path is None:
                raise CompositeQualityError("Composite assets are unavailable")
            metrics = compare_composite_pngs(composite_path, embedded_path).to_dict()
        except CompositeQualityError:
            metrics = {
                "status": "unavailable",
                "raw_rgba_mae": raw_rgba_mae,
                "alpha_representation": "unknown",
            }
        self._metrics[audit_sha256] = metrics
        return metrics


@dataclass(frozen=True, slots=True)
class CompositeQualityMetrics:
    width: int
    height: int
    raw_rgba_mae: float
    alpha_mae: float
    premultiplied_rgb_mae: float
    background_matched_rgb_mae: float
    background_matched_max_abs: int
    alpha_representation: str
    inferred_background_rgb: tuple[int, int, int]
    transparent_fraction_composite: float
    transparent_fraction_embedded: float
    status: str

    def to_dict(self) -> dict:
        result = asdict(self)
        result["inferred_background_rgb"] = list(self.inferred_background_rgb)
        return result


def compare_composite_pngs(
    composite_path: Path,
    embedded_path: Path,
    *,
    visual_mae_threshold: float = 5.0,
) -> CompositeQualityMetrics:
    width, height, composite = _decode_rgba_png(Path(composite_path))
    other_width, other_height, embedded = _decode_rgba_png(Path(embedded_path))
    if (width, height) != (other_width, other_height):
        raise CompositeQualityError("Composite dimensions differ")
    pixel_count = width * height
    if pixel_count < 1:
        raise CompositeQualityError("Composite is empty")

    if _np is not None:
        return _compare_numpy(
            width,
            height,
            composite,
            embedded,
            visual_mae_threshold,
        )

    raw_error = sum(abs(left - right) for left, right in zip(composite, embedded))
    alpha_error = 0
    premultiplied_error = 0
    transparent_composite = 0
    transparent_embedded = 0
    for offset in range(0, len(composite), 4):
        alpha_left = composite[offset + 3]
        alpha_right = embedded[offset + 3]
        alpha_error += abs(alpha_left - alpha_right)
        transparent_composite += alpha_left < 250
        transparent_embedded += alpha_right < 250
        for channel in range(3):
            left = (composite[offset + channel] * alpha_left + 127) // 255
            right = (embedded[offset + channel] * alpha_right + 127) // 255
            premultiplied_error += abs(left - right)

    background = _infer_background(composite, embedded)
    matched_error = 0
    matched_max = 0
    for offset in range(0, len(composite), 4):
        alpha_left = composite[offset + 3]
        alpha_right = embedded[offset + 3]
        for channel in range(3):
            left = _composite_channel(
                composite[offset + channel], alpha_left, background[channel]
            )
            right = _composite_channel(
                embedded[offset + channel], alpha_right, background[channel]
            )
            difference = abs(left - right)
            matched_error += difference
            matched_max = max(matched_max, difference)

    transparent_fraction_left = transparent_composite / pixel_count
    transparent_fraction_right = transparent_embedded / pixel_count
    alpha_mae = alpha_error / pixel_count
    representation = _alpha_representation(
        transparent_fraction_left,
        transparent_fraction_right,
        alpha_mae,
    )
    matched_mae = matched_error / (pixel_count * 3)
    return CompositeQualityMetrics(
        width=width,
        height=height,
        raw_rgba_mae=round(raw_error / (pixel_count * 4), 6),
        alpha_mae=round(alpha_mae, 6),
        premultiplied_rgb_mae=round(premultiplied_error / (pixel_count * 3), 6),
        background_matched_rgb_mae=round(matched_mae, 6),
        background_matched_max_abs=matched_max,
        alpha_representation=representation,
        inferred_background_rgb=background,
        transparent_fraction_composite=round(transparent_fraction_left, 8),
        transparent_fraction_embedded=round(transparent_fraction_right, 8),
        status="manual_required" if matched_mae > visual_mae_threshold else "passed",
    )


def _decode_rgba_png(path: Path) -> tuple[int, int, bytes]:
    if _PillowImage is not None:
        try:
            with _PillowImage.open(path) as image:
                if image.format != "PNG" or image.mode != "RGBA":
                    raise CompositeQualityError(
                        "Composite comparison requires 8-bit RGBA PNGs"
                    )
                image.load()
                return image.width, image.height, image.tobytes()
        except CompositeQualityError:
            raise
        except (OSError, ValueError) as exc:
            raise CompositeQualityError(f"Cannot decode PNG: {path.name}") from exc
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CompositeQualityError(f"Cannot read PNG: {path.name}") from exc
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise CompositeQualityError(f"Not a PNG: {path.name}")
    position = 8
    width = height = 0
    compressed = bytearray()
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        payload_start = position + 8
        payload_end = payload_start + length
        if payload_end + 4 > len(data):
            raise CompositeQualityError(f"Truncated PNG chunk: {path.name}")
        payload = data[payload_start:payload_end]
        if kind == b"IHDR":
            if len(payload) != 13:
                raise CompositeQualityError("Invalid PNG IHDR")
            width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if (depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise CompositeQualityError(
                    "Composite comparison requires non-interlaced 8-bit RGBA PNGs"
                )
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        position = payload_end + 4
    if width < 1 or height < 1 or not compressed:
        raise CompositeQualityError(f"PNG has no image data: {path.name}")
    try:
        filtered = zlib.decompress(compressed)
    except zlib.error as exc:
        raise CompositeQualityError(f"Cannot decompress PNG: {path.name}") from exc
    stride = width * 4
    if len(filtered) != height * (stride + 1):
        raise CompositeQualityError("PNG scanline size is inconsistent")

    output = bytearray(height * stride)
    source_offset = 0
    for row in range(height):
        filter_type = filtered[source_offset]
        source_offset += 1
        row_start = row * stride
        for column in range(stride):
            raw = filtered[source_offset + column]
            left = output[row_start + column - 4] if column >= 4 else 0
            above = output[row_start + column - stride] if row else 0
            upper_left = output[row_start + column - stride - 4] if row and column >= 4 else 0
            if filter_type == 0:
                value = raw
            elif filter_type == 1:
                value = raw + left
            elif filter_type == 2:
                value = raw + above
            elif filter_type == 3:
                value = raw + ((left + above) // 2)
            elif filter_type == 4:
                value = raw + _paeth(left, above, upper_left)
            else:
                raise CompositeQualityError(f"Unsupported PNG filter {filter_type}")
            output[row_start + column] = value & 0xFF
        source_offset += stride
    return width, height, bytes(output)


def _infer_background(composite: bytes, embedded: bytes) -> tuple[int, int, int]:
    histograms = [[0] * 256 for _ in range(3)]
    samples = 0
    for offset in range(0, len(composite), 4):
        if composite[offset + 3] <= 8 and embedded[offset + 3] >= 247:
            for channel in range(3):
                histograms[channel][embedded[offset + channel]] += 1
            samples += 1
    if not samples:
        for offset in range(0, len(composite), 4):
            if embedded[offset + 3] <= 8 and composite[offset + 3] >= 247:
                for channel in range(3):
                    histograms[channel][composite[offset + channel]] += 1
                samples += 1
    if not samples:
        return (0, 0, 0)
    return tuple(max(range(256), key=histogram.__getitem__) for histogram in histograms)


def _compare_numpy(
    width: int,
    height: int,
    composite: bytes,
    embedded: bytes,
    threshold: float,
) -> CompositeQualityMetrics:
    left_u8 = _np.frombuffer(composite, dtype=_np.uint8).reshape(-1, 4)
    right_u8 = _np.frombuffer(embedded, dtype=_np.uint8).reshape(-1, 4)
    left = left_u8.astype(_np.int32)
    right = right_u8.astype(_np.int32)
    alpha_left = left[:, 3:4]
    alpha_right = right[:, 3:4]
    premultiplied_left = (left[:, :3] * alpha_left + 127) // 255
    premultiplied_right = (right[:, :3] * alpha_right + 127) // 255

    background_mask = (left_u8[:, 3] <= 8) & (right_u8[:, 3] >= 247)
    background_source = right_u8
    if not bool(background_mask.any()):
        background_mask = (right_u8[:, 3] <= 8) & (left_u8[:, 3] >= 247)
        background_source = left_u8
    if bool(background_mask.any()):
        background = tuple(
            int(_np.bincount(background_source[background_mask, channel], minlength=256).argmax())
            for channel in range(3)
        )
    else:
        background = (0, 0, 0)
    background_array = _np.asarray(background, dtype=_np.int32).reshape(1, 3)
    matched_left = (
        left[:, :3] * alpha_left + background_array * (255 - alpha_left) + 127
    ) // 255
    matched_right = (
        right[:, :3] * alpha_right + background_array * (255 - alpha_right) + 127
    ) // 255
    matched_difference = _np.abs(matched_left - matched_right)
    transparent_left = float(_np.mean(left_u8[:, 3] < 250))
    transparent_right = float(_np.mean(right_u8[:, 3] < 250))
    alpha_mae = float(_np.mean(_np.abs(alpha_left - alpha_right)))
    matched_mae = float(_np.mean(matched_difference))
    return CompositeQualityMetrics(
        width=width,
        height=height,
        raw_rgba_mae=round(float(_np.mean(_np.abs(left - right))), 6),
        alpha_mae=round(alpha_mae, 6),
        premultiplied_rgb_mae=round(
            float(_np.mean(_np.abs(premultiplied_left - premultiplied_right))), 6
        ),
        background_matched_rgb_mae=round(matched_mae, 6),
        background_matched_max_abs=int(matched_difference.max(initial=0)),
        alpha_representation=_alpha_representation(
            transparent_left, transparent_right, alpha_mae
        ),
        inferred_background_rgb=background,
        transparent_fraction_composite=round(transparent_left, 8),
        transparent_fraction_embedded=round(transparent_right, 8),
        status="manual_required" if matched_mae > threshold else "passed",
    )


def _alpha_representation(left: float, right: float, alpha_mae: float) -> str:
    if alpha_mae <= 2 and abs(left - right) <= 0.01:
        return "comparable"
    if (left >= 0.01 and right <= 0.001) or (right >= 0.01 and left <= 0.001):
        return "flattened_reference"
    return "mixed"


def _composite_channel(color: int, alpha: int, background: int) -> int:
    return (color * alpha + background * (255 - alpha) + 127) // 255


def _paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    left_distance = abs(prediction - left)
    above_distance = abs(prediction - above)
    upper_left_distance = abs(prediction - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    return above if above_distance <= upper_left_distance else upper_left
