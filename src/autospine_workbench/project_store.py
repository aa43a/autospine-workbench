"""Discovery and persistence for local AutoSpine workbench projects."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from .composite_quality import CompositeQualityCache
from .contracts import (
    LAYER_SCHEMA_VERSION,
    PROJECT_SCHEMA_VERSION,
    SKELETON_SCHEMA_VERSION,
    contract_descriptor,
)
from .override_store import (
    OverrideHistoryStore,
    OverrideRevisionConflict,
    OverrideStateError,
    OverrideStoreError,
)
from .lazy_source_paths import project_override_context
from .resolved_project import ResolvedProjectBuilder
from .project_validation import validate_project_document


_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_MAX_AUDIT_BYTES = 64 * 1024 * 1024

class ProjectStoreError(RuntimeError):
    """Base error for project discovery and persistence."""


class ProjectNotFoundError(ProjectStoreError):
    def __init__(self, project_id: str):
        self.project_id = project_id
        super().__init__(f"Unknown project: {project_id}")


class AssetNotFoundError(ProjectStoreError):
    def __init__(self, project_id: str, asset: str):
        self.project_id = project_id
        self.asset = asset
        super().__init__(f"Asset not found for {project_id}: {asset}")


class RevisionConflictError(ProjectStoreError):
    def __init__(self, requested_revision: int, current_revision: int):
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        super().__init__(
            f"Revision conflict: requested {requested_revision}, current {current_revision}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "revision_conflict",
            "message": str(self),
            "requested_revision": self.requested_revision,
            "current_revision": self.current_revision,
        }


class ProjectStateError(ProjectStoreError):
    """Raised when a persisted override document is unreadable or invalid."""


@dataclass(frozen=True)
class _ProjectRecord:
    project_id: str
    audit_dir: Path
    audit_path: Path
    audit_sha256: str
    audit: Mapping[str, Any]


def _slug(value: str, fallback: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return normalized or fallback


def _safe_project_id(directory_name: str) -> str:
    if _PROJECT_ID_RE.fullmatch(directory_name) and directory_name not in {".", ".."}:
        return directory_name
    return _slug(directory_name, "project")[:96]


def _load_json(path: Path, max_bytes: int) -> Any:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ProjectStoreError(f"Cannot stat JSON file: {path.name}") from exc
    if size > max_bytes:
        raise ProjectStoreError(f"JSON file is too large: {path.name}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectStoreError(f"Cannot read JSON file: {path.name}") from exc


def _sha256_file(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as exc:
        raise ProjectStoreError(f"Cannot hash file: {path.name}") from exc


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)) and math.isfinite(value):
        return int(value)
    return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _bbox_dict(value: Any, canvas_width: int, canvas_height: int) -> dict[str, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return {"x": 0, "y": 0, "width": 0, "height": 0, "right": 0, "bottom": 0}
    left, top, right, bottom = (_as_int(item) for item in value)
    left = max(0, min(canvas_width, left))
    right = max(left, min(canvas_width, right))
    top = max(0, min(canvas_height, top))
    bottom = max(top, min(canvas_height, bottom))
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
        "right": right,
        "bottom": bottom,
    }


_ROLE_MAP = {
    "back-hair": "hair.back",
    "front-hair": "hair.front",
    "hair": "hair",
    "objects": "accessory.object",
    "object": "accessory.object",
    "head-obj": "accessory.head",
    "head-object": "accessory.head",
    "headwear": "accessory.headwear",
    "footwear": "body.foot",
    "foot": "body.foot",
    "handwear": "body.hand",
    "hand": "body.hand",
    "legwear": "body.leg",
    "leg": "body.leg",
    "bottomwear": "body.pelvis",
    "topwear": "body.torso",
    "torso": "body.torso",
    "neck": "body.neck",
    "face": "face.base",
    "nose": "face.nose",
    "mouth": "face.mouth",
    "ears": "face.ear",
    "ear": "face.ear",
    "eyebrow": "face.brow",
    "brow": "face.brow",
    "eyelash": "face.eyelash",
    "eyewhite": "face.eye.white",
    "irides": "face.eye.iris",
    "iris": "face.eye.iris",
}

_PAIRED_BASE_NAMES = frozenset(
    {"footwear", "foot", "handwear", "hand", "legwear", "leg", "ears", "ear", "eyebrow", "brow", "eyelash", "eyewhite", "irides", "iris"}
)


def _semantic_layer(name: str) -> tuple[str, str]:
    token = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    side: str | None = None
    base = token
    for suffix, candidate in (("-left", "left"), ("-right", "right"), ("-l", "left"), ("-r", "right")):
        if token.endswith(suffix):
            base = token[: -len(suffix)]
            side = candidate
            break
    role = _ROLE_MAP.get(base)
    if role is None:
        for known, known_role in _ROLE_MAP.items():
            if base == known or base.startswith(f"{known}-"):
                role = known_role
                break
    if role is None:
        role = f"unclassified.{_slug(base, 'layer')}"
    if side is None:
        if base in _PAIRED_BASE_NAMES:
            side = "bilateral"
        elif role.startswith("unclassified") or role.startswith("accessory.object"):
            side = "unknown"
        else:
            side = "center"
    return role, side


def _layer_id(layer: Mapping[str, Any], ordinal: int) -> str:
    index = _as_int(layer.get("traversal_index", layer.get("index", ordinal)), ordinal)
    return f"layer-{index:03d}-{_slug(str(layer.get('name', 'layer')), 'layer')}"


def _assigned_layers(raw_layers: Any) -> list[tuple[int, Mapping[str, Any], str]]:
    if not isinstance(raw_layers, list):
        return []
    assigned: list[tuple[int, Mapping[str, Any], str]] = []
    seen: set[str] = set()
    for ordinal, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, Mapping):
            continue
        layer_id = _layer_id(raw_layer, ordinal)
        if layer_id in seen:
            layer_id = f"{layer_id}-{ordinal}"
        seen.add(layer_id)
        assigned.append((ordinal, raw_layer, layer_id))
    return assigned


class ProjectStore:
    """Read audit projects and persist optimistic-concurrency overrides.

    ``workspace_root`` is the shared workspace containing
    ``tmp/psd_audit/results``.  ``state_root`` defaults to the workbench's own
    ``workspace`` directory and is the only location this class writes.
    """

    def __init__(self, workspace_root: Path, state_root: Path | None = None, *, measure_composite_quality: bool = True):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        default_state_root = Path(__file__).resolve().parents[2] / "workspace"
        self.state_root = Path(state_root).expanduser().resolve() if state_root else default_state_root
        self.audit_root = self.workspace_root / "tmp" / "psd_audit" / "results"
        self._override_store = OverrideHistoryStore(self.state_root)
        self._composite_quality = CompositeQualityCache(measure_composite_quality)

    def _discover(self) -> dict[str, _ProjectRecord]:
        records: dict[str, _ProjectRecord] = {}
        if not self.audit_root.is_dir():
            return records
        try:
            audit_paths = sorted(self.audit_root.glob("*/audit.json"), key=lambda item: item.parent.name)
        except OSError as exc:
            raise ProjectStoreError("Cannot enumerate the PSD audit result directory") from exc
        for audit_path in audit_paths:
            try:
                resolved_path = audit_path.resolve(strict=True)
                resolved_path.relative_to(self.audit_root.resolve(strict=True))
                audit = _load_json(resolved_path, _MAX_AUDIT_BYTES)
            except (OSError, ValueError, ProjectStoreError):
                continue
            if not isinstance(audit, Mapping):
                continue
            project_id = _safe_project_id(resolved_path.parent.name)
            if project_id in records:
                digest = str(audit.get("sha256", ""))[:8] or str(len(records))
                project_id = f"{project_id}-{digest}"
            records[project_id] = _ProjectRecord(
                project_id=project_id,
                audit_dir=resolved_path.parent,
                audit_path=resolved_path,
                audit_sha256=_sha256_file(resolved_path),
                audit=audit,
            )
        return records

    def _record(self, project_id: str) -> _ProjectRecord:
        if not isinstance(project_id, str) or not _PROJECT_ID_RE.fullmatch(project_id):
            raise ProjectNotFoundError(str(project_id))
        record = self._discover().get(project_id)
        if record is None:
            raise ProjectNotFoundError(project_id)
        return record

    def _canvas(self, audit: Mapping[str, Any]) -> tuple[int, int]:
        canvas = audit.get("canvas")
        if not isinstance(canvas, (list, tuple)) or len(canvas) != 2:
            return 0, 0
        return max(0, _as_int(canvas[0])), max(0, _as_int(canvas[1]))

    def _layers(self, record: _ProjectRecord) -> list[dict[str, Any]]:
        width, height = self._canvas(record.audit)
        raw_layers = record.audit.get("layers")
        if not isinstance(raw_layers, list):
            return []
        result: list[dict[str, Any]] = []
        for ordinal, raw_layer, layer_id in _assigned_layers(raw_layers):
            name = str(raw_layer.get("name", f"Layer {ordinal}"))
            role, side = _semantic_layer(name)
            bbox = _bbox_dict(raw_layer.get("bbox"), width, height)
            empty = bool(raw_layer.get("empty", False))
            visible = bool(raw_layer.get("visible", True))
            if empty:
                disposition = "exclude"
            elif role.startswith("unclassified") or side == "bilateral":
                disposition = "review"
            else:
                disposition = "keep"
            alpha_nonzero = max(0, _as_int(raw_layer.get("alpha_nonzero")))
            alpha_perceptible = max(0, _as_int(raw_layer.get("alpha_perceptible")))
            component_count = max(0, _as_int(raw_layer.get("component_count")))
            pivot = [bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2]
            result.append(
                {
                    "schema_version": LAYER_SCHEMA_VERSION,
                    "contract": contract_descriptor("layer"),
                    "id": layer_id,
                    "source_index": _as_int(
                        raw_layer.get("traversal_index", raw_layer.get("index", ordinal)), ordinal
                    ),
                    "name": name,
                    "canonical_role": role,
                    # Sides always mean the character's own left/right, never viewer left/right.
                    "side": side,
                    "disposition": disposition,
                    "visible": visible,
                    "empty": empty,
                    "opacity": _clamp(_as_int(raw_layer.get("opacity"), 255) / 255, 0, 1),
                    "blend_mode": str(raw_layer.get("blend_mode", "normal")),
                    "z_index": ordinal,
                    "bbox": bbox,
                    "pivot_xy": pivot,
                    "image_url": (
                        f"/api/projects/{quote(record.project_id, safe='')}/layers/"
                        f"{quote(layer_id, safe='')}/image"
                    ),
                    "metrics": {
                        "alpha_nonzero": alpha_nonzero,
                        "alpha_perceptible": alpha_perceptible,
                        "component_count": component_count,
                        "main_component_ratio": float(raw_layer.get("main_component_ratio", 0) or 0),
                        "fills_bbox_ratio": float(raw_layer.get("fills_bbox_ratio", 0) or 0),
                    },
                }
            )
        return result

    @staticmethod
    def _find_layer(
        layers: list[dict[str, Any]], role: str, side: str | None = None
    ) -> dict[str, Any] | None:
        candidates = [
            layer
            for layer in layers
            if layer["canonical_role"] == role
            and not layer["empty"]
            and (side is None or layer["side"] in {side, "bilateral"})
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item["metrics"]["alpha_perceptible"])

    @staticmethod
    def _center(layer: dict[str, Any] | None, fallback: tuple[float, float]) -> tuple[float, float]:
        if layer is None:
            return fallback
        bbox = layer["bbox"]
        return bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2

    def _skeleton(
        self, canvas_width: int, canvas_height: int, layers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        width = max(1, canvas_width)
        height = max(1, canvas_height)
        torso = self._find_layer(layers, "body.torso")
        pelvis_layer = self._find_layer(layers, "body.pelvis")
        neck_layer = self._find_layer(layers, "body.neck")
        face = self._find_layer(layers, "face.base")
        footwear = self._find_layer(layers, "body.foot")

        torso_box = torso["bbox"] if torso else {
            "x": width * 0.36,
            "y": height * 0.28,
            "width": width * 0.28,
            "height": height * 0.34,
            "bottom": height * 0.62,
        }
        pelvis_box = pelvis_layer["bbox"] if pelvis_layer else {
            "x": width * 0.38,
            "y": height * 0.54,
            "width": width * 0.24,
            "height": height * 0.18,
            "bottom": height * 0.72,
        }
        character_bottom = max(
            (layer["bbox"]["bottom"] for layer in layers if not layer["empty"]),
            default=height * 0.9,
        )

        pelvis = self._center(
            pelvis_layer,
            (width * 0.5, pelvis_box["y"] + pelvis_box["height"] * 0.42),
        )
        chest = (
            torso_box["x"] + torso_box["width"] * 0.5,
            torso_box["y"] + torso_box["height"] * 0.34,
        )
        spine = ((pelvis[0] + chest[0]) / 2, (pelvis[1] + chest[1]) / 2)
        neck = self._center(
            neck_layer,
            (torso_box["x"] + torso_box["width"] * 0.5, torso_box["y"]),
        )
        head = self._center(face, (neck[0], max(0, neck[1] - height * 0.1)))
        root = (pelvis[0], min(float(height), float(character_bottom)))

        points: dict[str, tuple[float, float, float, str]] = {
            "root": (*root, 0.7, "character-bounds"),
            "pelvis": (*pelvis, 0.7 if pelvis_layer else 0.3, "layer" if pelvis_layer else "fallback"),
            "spine": (*spine, 0.55, "derived"),
            "chest": (*chest, 0.7 if torso else 0.3, "layer" if torso else "fallback"),
            "neck": (*neck, 0.8 if neck_layer else 0.35, "layer" if neck_layer else "fallback"),
            "head": (*head, 0.8 if face else 0.35, "layer" if face else "fallback"),
        }

        def hand_point(side: str, shoulder: tuple[float, float]) -> tuple[float, float, float, str]:
            hand = self._find_layer(layers, "body.hand", side)
            if hand:
                bbox = hand["bbox"]
                center_x = bbox["x"] + bbox["width"] / 2
                far_x = bbox["x"] + bbox["width"] * (0.16 if center_x < shoulder[0] else 0.84)
                return far_x, bbox["y"] + bbox["height"] * 0.65, 0.68, "layer"
            direction = 1 if side == "left" else -1
            return shoulder[0] + direction * width * 0.18, shoulder[1] + height * 0.22, 0.2, "fallback"

        for side, default_direction in (("left", 1), ("right", -1)):
            hand_layer = self._find_layer(layers, "body.hand", side)
            default_shoulder_x = chest[0] + default_direction * torso_box["width"] * 0.42
            if hand_layer:
                hand_center_x = hand_layer["bbox"]["x"] + hand_layer["bbox"]["width"] / 2
                left_edge = torso_box["x"] + torso_box["width"] * 0.08
                right_edge = torso_box["x"] + torso_box["width"] * 0.92
                shoulder_x = left_edge if abs(hand_center_x - left_edge) < abs(hand_center_x - right_edge) else right_edge
            else:
                shoulder_x = default_shoulder_x
            shoulder = (shoulder_x, torso_box["y"] + torso_box["height"] * 0.22)
            wrist_x, wrist_y, wrist_conf, wrist_source = hand_point(side, shoulder)
            elbow = ((shoulder[0] + wrist_x) / 2, (shoulder[1] + wrist_y) / 2)
            points[f"shoulder.{side}"] = (*shoulder, 0.6 if torso else 0.25, "derived")
            points[f"elbow.{side}"] = (*elbow, min(0.55, wrist_conf), "derived")
            points[f"wrist.{side}"] = (wrist_x, wrist_y, wrist_conf, wrist_source)

        if footwear:
            foot_box = footwear["bbox"]
            ankle_y = foot_box["y"] + foot_box["height"] * 0.62
            ankle_x = {
                "right": foot_box["x"] + foot_box["width"] * 0.3,
                "left": foot_box["x"] + foot_box["width"] * 0.7,
            }
            ankle_confidence = 0.6
            ankle_source = "layer"
        else:
            ankle_y = character_bottom - height * 0.03
            ankle_x = {"right": pelvis[0] - width * 0.07, "left": pelvis[0] + width * 0.07}
            ankle_confidence = 0.2
            ankle_source = "fallback"

        hip_span = max(width * 0.04, min(width * 0.12, pelvis_box["width"] * 0.22))
        for side, direction in (("left", 1), ("right", -1)):
            hip = (pelvis[0] + direction * hip_span, pelvis[1] + pelvis_box["height"] * 0.08)
            ankle = (ankle_x[side], ankle_y)
            knee = ((hip[0] + ankle[0]) / 2, (hip[1] + ankle[1]) / 2)
            points[f"hip.{side}"] = (*hip, 0.5, "derived")
            points[f"knee.{side}"] = (*knee, min(0.5, ankle_confidence), "derived")
            points[f"ankle.{side}"] = (*ankle, ankle_confidence, ankle_source)

        # Eye joints are useful for blink/gaze authoring but are not part of the
        # deforming humanoid chain.
        eyes = self._find_layer(layers, "face.eye.white") or self._find_layer(layers, "face.eye.iris")
        if eyes:
            eye_box = eyes["bbox"]
            eye_y = eye_box["y"] + eye_box["height"] * 0.5
            points["eye.right"] = (
                eye_box["x"] + eye_box["width"] * 0.3,
                eye_y,
                0.7,
                "layer",
            )
            points["eye.left"] = (
                eye_box["x"] + eye_box["width"] * 0.7,
                eye_y,
                0.7,
                "layer",
            )

        joints: list[dict[str, Any]] = []
        for joint_id, (x, y, confidence, source) in points.items():
            side = "center"
            if joint_id.endswith(".left"):
                side = "left"
            elif joint_id.endswith(".right"):
                side = "right"
            joints.append(
                {
                    "id": joint_id,
                    "role": f"humanoid.{joint_id}",
                    "side": side,
                    "x": round(_clamp(x, 0, width), 3),
                    "y": round(_clamp(y, 0, height), 3),
                    "confidence": round(_clamp(confidence, 0, 1), 3),
                    "source": source,
                    "editable": True,
                }
            )

        bone_specs = [
            ("root-pelvis", "root", "pelvis", None, "humanoid.root"),
            ("pelvis-spine", "pelvis", "spine", "root-pelvis", "humanoid.spine.lower"),
            ("spine-chest", "spine", "chest", "pelvis-spine", "humanoid.spine.upper"),
            ("chest-neck", "chest", "neck", "spine-chest", "humanoid.neck"),
            ("neck-head", "neck", "head", "chest-neck", "humanoid.head"),
        ]
        for side in ("left", "right"):
            bone_specs.extend(
                [
                    (
                        f"chest-shoulder.{side}",
                        "chest",
                        f"shoulder.{side}",
                        "spine-chest",
                        f"humanoid.clavicle.{side}",
                    ),
                    (
                        f"upper-arm.{side}",
                        f"shoulder.{side}",
                        f"elbow.{side}",
                        f"chest-shoulder.{side}",
                        f"humanoid.arm.upper.{side}",
                    ),
                    (
                        f"forearm.{side}",
                        f"elbow.{side}",
                        f"wrist.{side}",
                        f"upper-arm.{side}",
                        f"humanoid.arm.lower.{side}",
                    ),
                    (
                        f"pelvis-hip.{side}",
                        "pelvis",
                        f"hip.{side}",
                        "root-pelvis",
                        f"humanoid.hip.{side}",
                    ),
                    (
                        f"thigh.{side}",
                        f"hip.{side}",
                        f"knee.{side}",
                        f"pelvis-hip.{side}",
                        f"humanoid.leg.upper.{side}",
                    ),
                    (
                        f"calf.{side}",
                        f"knee.{side}",
                        f"ankle.{side}",
                        f"thigh.{side}",
                        f"humanoid.leg.lower.{side}",
                    ),
                ]
            )
        bones = [
            {
                "id": bone_id,
                "role": role,
                "parent_id": parent_id,
                "start_joint_id": start,
                "end_joint_id": end,
            }
            for bone_id, start, end, parent_id, role in bone_specs
        ]
        return {
            "schema_version": SKELETON_SCHEMA_VERSION,
            "contract": contract_descriptor("skeleton"),
            "template": "humanoid-v1",
            "coordinate_system": {
                "origin": "canvas-top-left",
                "x_axis": "right",
                "y_axis": "down",
                "side_semantics": "character-own-left-right",
            },
            "generation": {
                "method": "audit-bbox-heuristic-v1",
                "requires_review": True,
            },
            "joints": joints,
            "bones": bones,
        }

    def _read_overrides(self, project: Mapping[str, Any]) -> dict[str, Any]:
        project_id = str(project["id"])
        try:
            return self._override_store.load(
                project_id,
                **project_override_context(project, self.resolve_asset, AssetNotFoundError),
            )
        except OverrideStateError as exc:
            raise ProjectStateError(str(exc)) from exc

    def _build_project(self, record: _ProjectRecord, include_overrides: bool = True) -> dict[str, Any]:
        canvas_width, canvas_height = self._canvas(record.audit)
        layers = self._layers(record)
        skeleton = self._skeleton(canvas_width, canvas_height, layers)
        source_name = Path(str(record.audit.get("source", record.project_id))).name
        raw_composite_mae = float(record.audit.get("composite_vs_embedded_mae_rgba", 0) or 0)
        try:
            composite_path = self.resolve_asset(record.project_id, "composite")
            embedded_path = self.resolve_asset(record.project_id, "embedded-composite")
        except AssetNotFoundError:
            composite_path = embedded_path = None
        composite_quality = self._composite_quality.measure(
            record.audit_sha256,
            raw_composite_mae,
            composite_path,
            embedded_path,
        )
        high_composite_error = composite_quality.get("status") == "manual_required"
        review_layers = sum(
            1 for layer in layers if layer["disposition"] == "review" or layer["empty"]
        )
        project: dict[str, Any] = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "contract": contract_descriptor("project"),
            "id": record.project_id,
            "name": Path(source_name).stem or record.project_id,
            "source": {
                "file_name": source_name,
                "sha256": str(record.audit.get("sha256", "")),
                "audit_sha256": record.audit_sha256,
                "audit_id": record.audit_dir.name,
            },
            "canvas": {
                "width": canvas_width,
                "height": canvas_height,
                "coordinate_system": "canvas-top-left-y-down",
            },
            "layers": layers,
            "skeleton": skeleton,
            "assets": {
                "composite_url": f"/api/projects/{quote(record.project_id, safe='')}/composite",
                "embedded_composite_url": (
                    f"/api/projects/{quote(record.project_id, safe='')}/embedded-composite"
                ),
                "contact_sheet_url": (
                    f"/api/projects/{quote(record.project_id, safe='')}/contact-sheet"
                ),
            },
            "capabilities": {
                "edit_joints": True,
                "edit_layers": True,
                "validate": True,
                "serve_source_assets": True,
                "export_spine": False,
                "supported_joint_override_fields": ["x", "y", "confidence", "reason"],
                "supported_layer_override_fields": [
                    "canonical_role",
                    "side",
                    "disposition",
                    "visible",
                    "pivot_xy", "candidate_bone",
                    "notes",
                ],
            },
            "workflow": {
                "status": "needs_review",
                "current_stage": "rig-review",
                "next_action": "Review semantic layers and heuristic joints.",
                "steps": [
                    {"id": "psd-audit", "status": "complete"},
                    {
                        "id": "layer-review",
                        "status": "needs_review" if review_layers else "ready",
                        "review_item_count": review_layers,
                    },
                    {"id": "skeleton-review", "status": "needs_review"},
                    {"id": "spine-export", "status": "not_implemented"},
                ],
                "audit_warnings": {
                    "high_composite_error": high_composite_error,
                    "raw_composite_difference": raw_composite_mae > 5,
                    "composite_quality": composite_quality,
                    "empty_layer_count": sum(1 for layer in layers if layer["empty"]),
                },
            },
        }
        if include_overrides:
            overrides = self._read_overrides(project)
            project["overrides"] = overrides
            resolved = ResolvedProjectBuilder().build(project, overrides)
            project["resolved"] = resolved
            project["workflow"]["status"] = resolved["qa"]["status"]
            project["workflow"]["steps"][1]["status"] = (
                "needs_review" if resolved["qa"]["review_layer_ids"] else "ready"
            )
            project["workflow"]["steps"][1]["review_item_count"] = len(
                resolved["qa"]["review_layer_ids"]
            )
            project["workflow"]["steps"][2]["status"] = (
                "needs_review" if resolved["qa"]["unresolved_joint_ids"] else "ready"
            )
        return project

    def list_projects(self) -> list[dict[str, Any]]:
        """Return stable project summaries sorted by project id."""

        summaries: list[dict[str, Any]] = []
        for record in self._discover().values():
            project = self._build_project(record)
            summaries.append(
                {
                    "schema_version": PROJECT_SCHEMA_VERSION,
                    "id": project["id"],
                    "name": project["name"],
                    "canvas": project["canvas"],
                    "layer_count": len(project["layers"]),
                    "visible_layer_count": sum(
                        1 for layer in project["layers"] if layer["visible"] and not layer["empty"]
                    ),
                    "workflow_status": project["workflow"]["status"],
                    "revision": project["overrides"]["revision"],
                    "composite_url": project["assets"]["composite_url"],
                }
            )
        return sorted(summaries, key=lambda item: item["id"])

    def discovered_project_count(self) -> int:
        """Count audit projects without resolving mutable authoring state."""

        return len(self._discover())

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Return a complete versioned project document."""

        return self._build_project(self._record(project_id))

    def save_overrides(self, project_id: str, payload: Any) -> dict[str, Any]:
        """Validate and append overrides using revision compare-and-swap."""

        project = self._build_project(self._record(project_id), include_overrides=False)
        try:
            return self._override_store.save(
                project_id,
                payload,
                **project_override_context(project, self.resolve_asset, AssetNotFoundError),
            )
        except OverrideRevisionConflict as exc:
            raise RevisionConflictError(
                exc.requested_revision, exc.current_revision
            ) from exc
        except OverrideStoreError as exc:
            raise ProjectStoreError(str(exc)) from exc

    def validate_project(self, project_id: str) -> dict[str, Any]:
        """Run deterministic structural and local-asset validation."""

        record = self._record(project_id)
        errors: list[dict[str, str]] = []
        checks: list[dict[str, Any]] = []
        project = self._build_project(record, include_overrides=False)
        revision = 0
        try:
            overrides = self._read_overrides(project)
            revision = overrides["revision"]
            resolved = ResolvedProjectBuilder().build(project, overrides)
            project["layers"] = resolved["layers"]
            project["skeleton"] = resolved["skeleton"]
            project["resolved_qa"] = resolved["qa"]
            checks.append({"id": "overrides", "status": "pass", "revision": revision})
        except ProjectStateError as exc:
            checks.append({"id": "overrides", "status": "fail"})
            errors.append({"path": "$.overrides", "code": "invalid_state", "message": str(exc)})
        return validate_project_document(
            project_id,
            project,
            revision=revision,
            resolve_asset=self.resolve_asset,
            asset_error_type=AssetNotFoundError,
            initial_errors=errors,
            initial_checks=checks,
        )

    def resolve_asset(
        self, project_id: str, asset: str, layer_id: str | None = None
    ) -> Path:
        """Resolve an allow-listed image asset without trusting audit paths.

        Supported ``asset`` values are ``composite``, ``embedded-composite``,
        ``contact-sheet`` and ``layer``.  Layer ids must come from the project
        document; arbitrary relative paths are never accepted.
        """

        record = self._record(project_id)
        if asset == "composite":
            filename = Path(str(record.audit.get("composite_path", "composite.png"))).name
            candidate = record.audit_dir / filename
        elif asset in {"embedded-composite", "embedded_composite"}:
            filename = Path(
                str(record.audit.get("embedded_composite_path", "embedded_composite.png"))
            ).name
            candidate = record.audit_dir / filename
        elif asset in {"contact-sheet", "contact_sheet"}:
            filename = Path(
                str(record.audit.get("layers_contact_sheet_path", "layers_contact_sheet.png"))
            ).name
            candidate = record.audit_dir / filename
        elif asset == "layer":
            if not layer_id:
                raise AssetNotFoundError(project_id, "layer")
            match: Mapping[str, Any] | None = None
            for _, raw_layer, assigned_id in _assigned_layers(record.audit.get("layers")):
                if assigned_id == layer_id:
                    match = raw_layer
                    break
            if match is None:
                raise AssetNotFoundError(project_id, f"layer:{layer_id}")
            filename = Path(str(match.get("crop_path", ""))).name
            candidate = record.audit_dir / "layers" / filename
        else:
            raise AssetNotFoundError(project_id, asset)

        try:
            resolved_root = record.audit_dir.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise AssetNotFoundError(project_id, asset) from exc
        if not resolved.is_file() or resolved.suffix.lower() not in _IMAGE_SUFFIXES:
            raise AssetNotFoundError(project_id, asset)
        return resolved
