"""Optional Pillow analysis of alpha geometry, never human or pose annotation."""
import hashlib
from io import BytesIO
import math

SCHEMA = "autospine.benchmark-input-quality/v1"
PROFILE = "alpha-input-quality-v1"
LIMITATIONS = ["human_body_cropping_not_assessed", "character_count_not_assessed", "perspective_not_assessed"]
_REASONS = {
    "empty_alpha_image": "blocked", "alpha_channel_missing": "warning",
    "low_alpha_only": "warning", "faint_alpha_content": "warning",
    "alpha_content_touches_canvas": "warning", "low_alpha_content_touches_canvas": "warning",
    "landscape_canvas": "warning", "small_alpha_bbox": "warning", "large_alpha_bbox": "warning",
}
_THRESHOLDS = (8, 32)
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 32 * 1024 * 1024


class InputQualityError(ValueError):
    def __init__(self, reason_code="input_quality_invalid"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def analyze_input_image(raw_png):
    """Observe alpha >= 8/32; bbox edges use right/bottom exclusive coordinates.

    RGB without transparency has unknown alpha observations, not a fabricated
    full-canvas silhouette. Nonzero alpha below the thresholds remains nonempty.
    """
    if type(raw_png) is not bytes or not 0 < len(raw_png) <= MAX_PNG_BYTES:
        raise InputQualityError("input_quality_png_invalid")
    try:
        from PIL import Image
    except ImportError as exc:
        raise InputQualityError("input_quality_dependency_unavailable") from exc
    try:
        with Image.open(BytesIO(raw_png)) as image:
            width, height = image.size
            if image.format != "PNG" or not 1 <= width * height <= MAX_PIXELS or getattr(image, "n_frames", 1) != 1:
                raise InputQualityError("input_quality_png_invalid")
            image.load()
            present = "A" in image.getbands() or "transparency" in image.info
            alpha = {"present": present, "min": None, "max": None,
                     "transparent_pixel_ratio": None, "nonzero_pixel_ratio": None,
                     "bbox_threshold_8": None, "bbox_threshold_32": None}
            if present:
                channel = image.convert("RGBA").getchannel("A")
                histogram = channel.histogram()
                occupied = [value for value, count in enumerate(histogram) if count]
                alpha.update(min=min(occupied), max=max(occupied),
                             transparent_pixel_ratio=histogram[0] / (width * height),
                             nonzero_pixel_ratio=1 - histogram[0] / (width * height))
                for threshold in _THRESHOLDS:
                    mask = channel.point([255 if value >= threshold else 0 for value in range(256)])
                    bbox = mask.getbbox()
                    alpha[f"bbox_threshold_{threshold}"] = list(bbox) if bbox is not None else None
    except InputQualityError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise InputQualityError("input_quality_png_invalid") from exc
    edges, ratios = _geometry(alpha, width, height)
    issues = _issues(alpha, edges, ratios, width / height)
    result = {
        "schema": SCHEMA, "analysis_profile": PROFILE,
        "source_sha256": hashlib.sha256(raw_png).hexdigest(), "canvas": [width, height],
        "alpha": alpha, "edge_contacts": edges, "canvas_aspect_ratio": width / height,
        "bbox_area_ratio": ratios, "quality": _quality(issues), "issues": issues,
        "authority": "none", "observability": "limited_to_alpha_geometry",
        "limitations": list(LIMITATIONS),
    }
    return validate_input_quality(result)


def _geometry(alpha, width, height):
    edges, ratios = {}, {}
    for threshold in _THRESHOLDS:
        key = f"threshold_{threshold}"
        bbox = alpha[f"bbox_{key}"]
        edges[key] = []
        ratios[key] = None
        if bbox is not None:
            left, top, right, bottom = bbox
            edges[key] = [name for name, contact in (
                ("left", left == 0), ("top", top == 0),
                ("right", right == width), ("bottom", bottom == height),
            ) if contact]
            ratios[key] = ((right - left) * (bottom - top)) / (width * height)
    return edges, ratios


def _issues(alpha, edges, ratios, aspect):
    reasons = []
    if not alpha["present"]:
        reasons.append("alpha_channel_missing")
    elif alpha["max"] == 0:
        reasons.append("empty_alpha_image")
    elif alpha["bbox_threshold_8"] is None:
        reasons.append("low_alpha_only")
    elif alpha["bbox_threshold_32"] is None:
        reasons.append("faint_alpha_content")
    if edges["threshold_32"]:
        reasons.append("alpha_content_touches_canvas")
    elif edges["threshold_8"]:
        reasons.append("low_alpha_content_touches_canvas")
    if aspect >= 1.2:
        reasons.append("landscape_canvas")
    ratio = ratios["threshold_32"]
    if ratio is not None and ratio < 0.1:
        reasons.append("small_alpha_bbox")
    elif ratio is not None and ratio >= 0.95:
        reasons.append("large_alpha_bbox")
    return [{"reason_code": reason, "severity": _REASONS[reason]} for reason in sorted(reasons)]


def _quality(issues):
    return "blocked" if any(row["severity"] == "blocked" for row in issues) else "warning" if issues else "ok"


def validate_input_quality(document):
    """Validate finite scalars, nested bbox thresholds and derived issue rules."""
    from copy import deepcopy
    from .validation import require_digest

    try:
        if type(document) is not dict or set(document) != {
            "schema", "analysis_profile", "source_sha256", "canvas", "alpha", "edge_contacts",
            "canvas_aspect_ratio", "bbox_area_ratio", "quality", "issues", "authority", "observability", "limitations",
        } or document["schema"] != SCHEMA or document["analysis_profile"] != PROFILE \
                or document["authority"] != "none" or document["observability"] != "limited_to_alpha_geometry" \
                or document["limitations"] != LIMITATIONS:
            raise InputQualityError()
        require_digest(document["source_sha256"])
        canvas = document["canvas"]
        if type(canvas) is not list or len(canvas) != 2 or any(type(v) is not int or v < 1 for v in canvas):
            raise InputQualityError()
        width, height = canvas
        if width * height > MAX_PIXELS:
            raise InputQualityError()
        alpha = document["alpha"]
        if type(alpha) is not dict or set(alpha) != {
            "present", "min", "max", "transparent_pixel_ratio", "nonzero_pixel_ratio", "bbox_threshold_8", "bbox_threshold_32",
        } or type(alpha["present"]) is not bool:
            raise InputQualityError()
        if not alpha["present"]:
            if any(value is not None for key, value in alpha.items() if key != "present"):
                raise InputQualityError()
        else:
            if any(type(alpha[key]) is not int or not 0 <= alpha[key] <= 255 for key in ("min", "max")) \
                    or alpha["min"] > alpha["max"]:
                raise InputQualityError()
            for key in ("transparent_pixel_ratio", "nonzero_pixel_ratio"):
                _ratio(alpha[key])
            if not math.isclose(alpha["transparent_pixel_ratio"] + alpha["nonzero_pixel_ratio"], 1, abs_tol=1e-12):
                raise InputQualityError()
            if (alpha["max"] == 0) != (alpha["nonzero_pixel_ratio"] == 0) \
                    or (alpha["min"] > 0) != (alpha["transparent_pixel_ratio"] == 0):
                raise InputQualityError()
            for threshold in _THRESHOLDS:
                bbox = alpha[f"bbox_threshold_{threshold}"]
                if (bbox is None) != (alpha["max"] < threshold):
                    raise InputQualityError()
                if bbox is not None and (type(bbox) is not list or len(bbox) != 4 or any(type(v) is not int for v in bbox)
                                        or not 0 <= bbox[0] < bbox[2] <= width or not 0 <= bbox[1] < bbox[3] <= height):
                    raise InputQualityError()
                if alpha["min"] >= threshold and bbox != [0, 0, width, height]:
                    raise InputQualityError()
            low, high = alpha["bbox_threshold_8"], alpha["bbox_threshold_32"]
            if high is not None and not (low[0] <= high[0] < high[2] <= low[2] and low[1] <= high[1] < high[3] <= low[3]):
                raise InputQualityError()
        edges, ratios = _geometry(alpha, width, height)
        if document["edge_contacts"] != edges or document["bbox_area_ratio"] != ratios:
            raise InputQualityError()
        _ratio(document["canvas_aspect_ratio"], positive=True, upper=None)
        if document["canvas_aspect_ratio"] != width / height:
            raise InputQualityError()
        for value in document["bbox_area_ratio"].values():
            if value is not None:
                _ratio(value)
        issues = _issues(alpha, edges, ratios, width / height)
        if document["issues"] != issues or document["quality"] != _quality(issues):
            raise InputQualityError()
    except InputQualityError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
        raise InputQualityError() from exc
    return deepcopy(document)


def _ratio(value, *, positive=False, upper=1):
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0 \
            or (positive and value <= 0) or (upper is not None and value > upper):
        raise InputQualityError()
