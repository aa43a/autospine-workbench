"""Reproducible P3 weight and deformation evidence images."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

from .mesh_eligibility import HingeTarget
from .mesh_pose_render import MeshPoseRenderError, render_mesh_pose
from .mesh_probe_report import MeshProbeReportError, require_mesh_probe_report
from .mesh_weight_heatmap import (
    ALPHA_COVERAGE_THRESHOLD,
    BALANCED_RGB,
    DISTAL_RGB,
    PROXIMAL_RGB,
    MeshWeightHeatmapError,
    render_mesh_weight_heatmap,
)
from .png_rgba import RgbaImage, RgbaPngError, encode_rgba_png
from .resolved_project import canonical_sha256
from .rig_setup_artifact import encoder_identity

FORMAT = "autospine-mesh-visual-artifacts"
FORMAT_VERSION = 1
HEATMAP_RENDERER_ID = "autospine-mesh-weight-heatmap"
POSE_RENDERER_ID = "autospine-mesh-pose"
RENDERER_VERSION = "1.0.0"

class MeshVisualArtifactsError(ValueError):
    """Raised when visual evidence cannot be generated or independently trusted."""

@dataclass(frozen=True, slots=True)
class MeshVisualArtifacts:
    """Frozen canonical JSON plus an immutable path-to-PNG byte snapshot."""

    _json: str
    _png_items: tuple[tuple[str, bytes], ...]

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._json)

    @property
    def png_by_path(self) -> Mapping[str, bytes]:
        return MappingProxyType(dict(self._png_items))

    def to_json(self) -> str:
        return self._json


def build_mesh_visual_artifacts(
    rig: Mapping[str, Any],
    run: Mapping[str, Any],
    probes: Mapping[str, Any],
    targets: Sequence[HingeTarget],
    target_images: Mapping[str, RgbaImage],
) -> MeshVisualArtifacts:
    """Render canonical weight, setup, and widest-safe evidence for every target."""

    try:
        require_mesh_probe_report(probes, rig=rig, run=run, targets=targets)
        if probes.get("status") != "passed":
            raise MeshVisualArtifactsError("rejected mesh probes have no visual pass set")
        ordered_targets = _ordered_targets(targets)
        images = _target_images(target_images, ordered_targets)
        entries = _probe_entries(probes, ordered_targets)
        attachments = _attachments(rig, ordered_targets)
        pngs: dict[str, bytes] = {}
        artifacts: list[dict[str, Any]] = []
        for target in ordered_targets:
            rendered = _render_target(
                rig, target, images[target.attachment_id],
                attachments[target.attachment_id], entries[target.attachment_id],
            )
            for path, kind, pose, bone, angle, image in rendered:
                png = encode_rgba_png(image)
                pngs[path] = png
                artifacts.append({
                    "kind": kind,
                    "id": target.attachment_id,
                    "pose": pose,
                    "bone": bone,
                    "angle_deg": angle,
                    "width": image.width,
                    "height": image.height,
                    "rgba_sha256": hashlib.sha256(image.pixels).hexdigest(),
                    "png_sha256": hashlib.sha256(png).hexdigest(),
                    "path": path,
                })
        artifacts.sort(key=lambda item: item["path"])
        _safe_unique_paths(tuple(item["path"] for item in artifacts))
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": probes["project_id"],
            "source": {
                "rig_sha256": canonical_sha256(rig),
                "run_manifest_sha256": canonical_sha256(run),
                "probes_sha256": canonical_sha256(probes),
            },
            "renderers": renderer_identities(),
            "status": "passed",
            "summary": (
                f"converted={len(ordered_targets)}"
                if ordered_targets else "reviewed-noop"
            ),
            "images": [_image_entry(item.attachment_id, images[item.attachment_id])
                       for item in ordered_targets],
            "targets": [_target_entry(item) for item in ordered_targets],
            "artifacts": artifacts,
        }
        encoded = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return MeshVisualArtifacts(encoded, tuple(sorted(pngs.items())))
    except MeshVisualArtifactsError:
        raise
    except (
        MeshPoseRenderError, MeshProbeReportError, MeshWeightHeatmapError,
        RgbaPngError, KeyError, TypeError, ValueError,
    ) as exc:
        raise MeshVisualArtifactsError(f"mesh visual artifacts failed: {exc}") from exc

def require_mesh_visual_artifacts(
    document: Mapping[str, Any],
    png_by_path: Mapping[str, bytes],
    *,
    rig: Mapping[str, Any],
    run: Mapping[str, Any],
    probes: Mapping[str, Any],
    targets: Sequence[HingeTarget],
    target_images: Mapping[str, RgbaImage],
) -> None:
    """Re-render all evidence and require exact JSON and exact PNG bytes."""

    if not isinstance(document, Mapping):
        raise MeshVisualArtifactsError("mesh visual artifact document must be an object")
    supplied = _png_mapping(png_by_path)
    expected = build_mesh_visual_artifacts(
        rig, run, probes, targets, target_images
    )
    try:
        document_matches = canonical_sha256(document) == canonical_sha256(expected.document)
    except (TypeError, ValueError) as exc:
        raise MeshVisualArtifactsError("visual artifact document is not canonical JSON") from exc
    if not document_matches:
        raise MeshVisualArtifactsError("visual artifact document differs from recomputed evidence")
    claimed_paths = tuple(item.get("path") for item in document.get("artifacts", ()))
    _safe_unique_paths(claimed_paths)
    if set(claimed_paths) != set(supplied):
        raise MeshVisualArtifactsError("visual artifact PNG path set differs from document")
    if supplied != dict(expected.png_by_path):
        raise MeshVisualArtifactsError("visual artifact PNG bytes differ from recomputed evidence")


def renderer_identities() -> dict[str, Any]:
    return {
        "weight_heatmap": {
            "id": HEATMAP_RENDERER_ID,
            "version": RENDERER_VERSION,
            "palette": {
                "proximal": _hex(PROXIMAL_RGB),
                "balanced": _hex(BALANCED_RGB),
                "distal": _hex(DISTAL_RGB),
            },
            "alpha_threshold": ALPHA_COVERAGE_THRESHOLD,
        },
        "pose": {"id": POSE_RENDERER_ID, "version": RENDERER_VERSION,
                 "sampling": "nearest", "canvas": "full"},
        "png_encoder": encoder_identity(),
    }

def _render_target(rig, target, source, attachment, entry):
    canvas = rig.get("canvas")
    if not isinstance(canvas, Mapping):
        raise MeshVisualArtifactsError("mesh RigIR canvas must be an object")
    heatmap = render_mesh_weight_heatmap(
        source, attachment,
        proximal_bone_id=target.proximal_bone_id,
        distal_bone_id=target.distal_bone_id,
    )
    setup = render_mesh_pose(
        source, rig.get("bones"), attachment, {},
        canvas_width=canvas.get("width"), canvas_height=canvas.get("height"),
    )
    widest = entry["widest_safe_bend"]
    magnitude = widest["magnitude_deg"]
    signed = -magnitude if widest["direction"] == "negative" else magnitude
    posed = render_mesh_pose(
        source, rig.get("bones"), attachment,
        {target.distal_bone_id: signed},
        canvas_width=canvas.get("width"), canvas_height=canvas.get("height"),
    )
    identifier = target.attachment_id
    return (
        (f"weights/{identifier}.png", "weight_heatmap", "weights",
         target.distal_bone_id, None, heatmap),
        (f"poses/{identifier}.setup.png", "pose", "setup", None, 0, setup),
        (f"poses/{identifier}.widest-safe-{_angle_tag(signed)}.png", "pose", "widest-safe",
         target.distal_bone_id, signed, posed),
    )

def _ordered_targets(targets) -> tuple[HingeTarget, ...]:
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes, bytearray)):
        raise MeshVisualArtifactsError("mesh targets must be an array")
    if any(not isinstance(item, HingeTarget) for item in targets):
        raise MeshVisualArtifactsError("mesh targets must be HingeTarget values")
    return tuple(sorted(targets, key=lambda item: item.attachment_id))

def _target_images(value, targets) -> dict[str, RgbaImage]:
    if not isinstance(value, Mapping):
        raise MeshVisualArtifactsError("target images must be an object")
    expected = {item.attachment_id for item in targets}
    if set(value) != expected:
        raise MeshVisualArtifactsError("target image keys differ from mesh targets")
    if any(not isinstance(image, RgbaImage) for image in value.values()):
        raise MeshVisualArtifactsError("target images must be RGBA images")
    return dict(value)

def _probe_entries(probes, targets):
    items = probes.get("attachments")
    if not isinstance(items, list):
        raise MeshVisualArtifactsError("probe attachments must be an array")
    indexed = {item.get("attachment_id"): item for item in items}
    if set(indexed) != {item.attachment_id for item in targets}:
        raise MeshVisualArtifactsError("probe attachment set differs from targets")
    return indexed

def _attachments(rig, targets):
    items = rig.get("attachments")
    if not isinstance(items, list):
        raise MeshVisualArtifactsError("mesh RigIR attachments must be an array")
    indexed = {item.get("id"): item for item in items if item.get("type") == "mesh"}
    if set(indexed) != {item.attachment_id for item in targets}:
        raise MeshVisualArtifactsError("mesh attachment set differs from targets")
    return indexed

def _image_entry(identifier: str, image: RgbaImage) -> dict[str, Any]:
    return {"id": identifier, "width": image.width, "height": image.height,
            "rgba_sha256": hashlib.sha256(image.pixels).hexdigest()}

def _target_entry(target: HingeTarget) -> dict[str, str]:
    return {name: getattr(target, name) for name in (
        "attachment_id", "source_layer_id", "side",
        "proximal_bone_id", "distal_bone_id",
    )}

def _png_mapping(value) -> dict[str, bytes]:
    if not isinstance(value, Mapping):
        raise MeshVisualArtifactsError("visual artifact PNGs must be an object")
    _safe_unique_paths(tuple(value))
    if any(not isinstance(item, bytes) for item in value.values()):
        raise MeshVisualArtifactsError("visual artifact PNG values must be bytes")
    return dict(value)

def _safe_unique_paths(paths) -> None:
    folded: set[str] = set()
    for path in paths:
        if (
            not isinstance(path, str) or not path or path == "." or "\\" in path
            or PurePosixPath(path).is_absolute()
            or str(PurePosixPath(path)) != path
            or ".." in PurePosixPath(path).parts
        ):
            raise MeshVisualArtifactsError("visual artifact path is unsafe")
        lowered = path.casefold()
        if lowered in folded:
            raise MeshVisualArtifactsError("visual artifact paths are not case-unique")
        folded.add(lowered)

def _hex(rgb) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in rgb)

def _angle_tag(angle: int) -> str:
    return f"{'m' if angle < 0 else 'p'}{abs(angle):03d}"
