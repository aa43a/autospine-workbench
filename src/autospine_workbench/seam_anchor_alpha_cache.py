"""Bounded alpha-geometry cache for exact seam attachment images."""

from __future__ import annotations

from .alpha_geometry import (
    AlphaGeometry,
    AlphaGeometryLimitError,
    analyze_alpha_image,
)
from .png_rgba import decode_rgba_png
from .seam_anchor_candidate_profile import (
    ALPHA_THRESHOLD,
    MAX_TOTAL_ALPHA_RUNS,
)
from .seam_anchor_sampling import MAX_RUNS_PER_MASK


class SeamAnchorAlphaCacheError(ValueError):
    """Raised when admitted attachment images no longer match their rig."""


def build_seam_alpha_index(
    inputs, attachments, referenced_ids
) -> dict[str, AlphaGeometry | None]:
    """Decode exact PNGs and stop each analysis at the seam run ceiling."""

    metadata = {
        row["attachment_id"]: row for row in inputs.attachment_images
    }
    pngs = inputs.png_by_attachment
    identifiers = tuple(sorted(set(referenced_ids)))
    if any(identifier not in attachments for identifier in identifiers):
        raise SeamAnchorAlphaCacheError(
            "Referenced seam attachment is absent"
        )
    result: dict[str, AlphaGeometry | None] = {}
    total_runs = 0
    for identifier in identifiers:
        attachment = attachments[identifier]
        row = metadata[identifier]
        image = decode_rgba_png(
            pngs[identifier], source_name=row["image_path"]
        )
        if (image.width, image.height) != (row["width"], row["height"]):
            raise SeamAnchorAlphaCacheError(
                "Attachment PNG dimensions changed after admission"
            )
        offset = attachment.get("canvas_offset_xy")
        if not isinstance(offset, list) or len(offset) != 2 \
                or any(type(item) is not int for item in offset):
            raise SeamAnchorAlphaCacheError(
                "Attachment canvas offset is invalid"
            )
        try:
            geometry = analyze_alpha_image(
                image, canvas_offset_xy=tuple(offset),
                threshold=ALPHA_THRESHOLD, max_runs=MAX_RUNS_PER_MASK,
            )
            total_runs += geometry.run_count
            if total_runs > MAX_TOTAL_ALPHA_RUNS:
                return {item: None for item in identifiers}
            result[identifier] = geometry
        except AlphaGeometryLimitError:
            result[identifier] = None
    return result
