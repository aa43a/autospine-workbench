"""Cross-reference and numeric validation for version-neutral RigIR documents.

JSON Schema validates shape. This module validates relationships that Draft 2020-12
cannot express, and deliberately reports unsupported or inconsistent data instead of
silently repairing it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class RigValidationIssue:
    code: str
    path: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class RigSemanticValidationError(ValueError):
    """Raised when RigIR contains one or more semantic errors."""

    def __init__(self, issues: Sequence[RigValidationIssue]) -> None:
        self.issues = tuple(issue for issue in issues if issue.severity == "error")
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(summary or "RigIR semantic validation failed")


class RigSemanticValidator:
    """Validate RigIR v1 identifiers, references, topology, and mesh weights."""

    def __init__(self, *, weight_tolerance: float = 1e-5, max_influences: int = 4) -> None:
        if weight_tolerance <= 0 or max_influences < 1:
            raise ValueError("Validator tolerances must be positive")
        self.weight_tolerance = weight_tolerance
        self.max_influences = max_influences

    def validate(self, rig: Mapping[str, Any]) -> list[RigValidationIssue]:
        issues: list[RigValidationIssue] = []
        bones = _objects(rig.get("bones"))
        slots = _objects(rig.get("slots"))
        attachments = _objects(rig.get("attachments"))
        animations = _objects(rig.get("animations"))

        bone_ids = self._unique_ids(bones, "bones", issues)
        slot_ids = self._unique_ids(slots, "slots", issues)
        attachment_ids = self._unique_ids(attachments, "attachments", issues)
        self._unique_ids(animations, "animations", issues)

        self._validate_bones(bones, bone_ids, issues)
        attachment_slots = self._validate_slots(
            slots, slot_ids, bone_ids, attachment_ids, attachments, issues
        )
        self._validate_attachments(attachments, attachment_slots, slot_ids, bone_ids, issues)
        self._validate_skins(rig.get("skins"), slot_ids, attachment_slots, issues)
        self._validate_animations(animations, bone_ids, issues)
        self._validate_retarget(rig.get("retarget"), bone_ids, issues)
        self._validate_capabilities(rig, attachments, animations, issues)
        return issues

    def raise_for_errors(self, rig: Mapping[str, Any]) -> list[RigValidationIssue]:
        issues = self.validate(rig)
        if any(issue.severity == "error" for issue in issues):
            raise RigSemanticValidationError(issues)
        return issues

    @staticmethod
    def _unique_ids(
        objects: Sequence[Mapping[str, Any]],
        collection: str,
        issues: list[RigValidationIssue],
    ) -> set[str]:
        result: set[str] = set()
        for index, item in enumerate(objects):
            item_id = item.get("id")
            if not isinstance(item_id, str):
                continue
            if item_id in result:
                _error(issues, "duplicate_id", f"/{collection}/{index}/id", f"duplicate id '{item_id}'")
            result.add(item_id)
        return result

    def _validate_bones(
        self,
        bones: Sequence[Mapping[str, Any]],
        bone_ids: set[str],
        issues: list[RigValidationIssue],
    ) -> None:
        parents: dict[str, str | None] = {}
        for index, bone in enumerate(bones):
            bone_id = bone.get("id")
            parent = bone.get("parent")
            if not isinstance(bone_id, str):
                continue
            parents[bone_id] = parent if isinstance(parent, str) else None
            if parent == bone_id:
                _error(issues, "bone_self_parent", f"/bones/{index}/parent", "bone cannot parent itself")
            elif isinstance(parent, str) and parent not in bone_ids:
                _error(issues, "missing_bone_parent", f"/bones/{index}/parent", f"unknown parent '{parent}'")
            self._finite_mapping(bone.get("setup"), f"/bones/{index}/setup", issues)

        states: dict[str, int] = {}

        def visit(bone_id: str, chain: tuple[str, ...]) -> None:
            if states.get(bone_id) == 2:
                return
            if states.get(bone_id) == 1:
                cycle = " -> ".join((*chain, bone_id))
                _error(issues, "bone_cycle", "/bones", f"bone hierarchy contains a cycle: {cycle}")
                return
            states[bone_id] = 1
            parent = parents.get(bone_id)
            if parent in parents:
                visit(parent, (*chain, bone_id))
            states[bone_id] = 2

        for bone_id in parents:
            visit(bone_id, ())

    def _validate_slots(
        self,
        slots: Sequence[Mapping[str, Any]],
        slot_ids: set[str],
        bone_ids: set[str],
        attachment_ids: set[str],
        attachments: Sequence[Mapping[str, Any]],
        issues: list[RigValidationIssue],
    ) -> dict[str, str]:
        attachment_slots = {
            item["id"]: item["slot"]
            for item in attachments
            if isinstance(item.get("id"), str) and isinstance(item.get("slot"), str)
        }
        draw_orders: dict[int, int] = {}
        for index, slot in enumerate(slots):
            bone = slot.get("bone")
            if isinstance(bone, str) and bone not in bone_ids:
                _error(issues, "missing_slot_bone", f"/slots/{index}/bone", f"unknown bone '{bone}'")
            setup_attachment = slot.get("setup_attachment")
            if isinstance(setup_attachment, str):
                if setup_attachment not in attachment_ids:
                    _error(issues, "missing_setup_attachment", f"/slots/{index}/setup_attachment", f"unknown attachment '{setup_attachment}'")
                elif attachment_slots.get(setup_attachment) != slot.get("id"):
                    _error(issues, "setup_attachment_slot_mismatch", f"/slots/{index}/setup_attachment", "setup attachment belongs to another slot")
            draw_order = slot.get("setup_draw_order")
            if isinstance(draw_order, int) and not isinstance(draw_order, bool):
                if draw_order in draw_orders:
                    _error(issues, "duplicate_draw_order", f"/slots/{index}/setup_draw_order", f"also used by slot index {draw_orders[draw_order]}")
                draw_orders[draw_order] = index
        return attachment_slots

    def _validate_attachments(
        self,
        attachments: Sequence[Mapping[str, Any]],
        attachment_slots: Mapping[str, str],
        slot_ids: set[str],
        bone_ids: set[str],
        issues: list[RigValidationIssue],
    ) -> None:
        for index, attachment in enumerate(attachments):
            path = f"/attachments/{index}"
            slot = attachment.get("slot")
            if isinstance(slot, str) and slot not in slot_ids:
                _error(issues, "missing_attachment_slot", f"{path}/slot", f"unknown slot '{slot}'")
            for field in ("canvas_offset_xy", "pivot_xy"):
                self._finite_sequence(attachment.get(field), f"{path}/{field}", issues)
            kind = attachment.get("type")
            if kind == "region":
                size = attachment.get("size")
                self._finite_sequence(size, f"{path}/size", issues)
                if _numeric_pair(size) and any(value <= 0 for value in size):
                    _error(issues, "invalid_region_size", f"{path}/size", "region width and height must be positive")
            elif kind == "mesh":
                self._validate_mesh(attachment, path, bone_ids, issues)

    def _validate_mesh(
        self,
        mesh: Mapping[str, Any],
        path: str,
        bone_ids: set[str],
        issues: list[RigValidationIssue],
    ) -> None:
        vertices = _sequences(mesh.get("vertices"))
        uvs = _sequences(mesh.get("uvs"))
        weights = _sequences(mesh.get("weights"))
        triangles = mesh.get("triangles") if isinstance(mesh.get("triangles"), list) else []
        for index, point in enumerate(vertices):
            self._finite_sequence(point, f"{path}/vertices/{index}", issues)
        for index, point in enumerate(uvs):
            self._finite_sequence(point, f"{path}/uvs/{index}", issues)
        if len(vertices) != len(uvs) or len(vertices) != len(weights):
            _error(issues, "mesh_cardinality", path, "vertices, uvs, and weights must have equal lengths")
        if len(triangles) % 3:
            _error(issues, "triangle_arity", f"{path}/triangles", "triangle index count must be divisible by three")
        for index, vertex_index in enumerate(triangles):
            if isinstance(vertex_index, int) and not isinstance(vertex_index, bool):
                if vertex_index < 0 or vertex_index >= len(vertices):
                    _error(issues, "triangle_index_out_of_range", f"{path}/triangles/{index}", f"index {vertex_index} is outside 0..{max(0, len(vertices) - 1)}")
        for vertex_index, influences in enumerate(weights):
            influence_path = f"{path}/weights/{vertex_index}"
            if len(influences) > self.max_influences:
                _error(issues, "too_many_influences", influence_path, f"maximum is {self.max_influences}")
            total = 0.0
            seen: set[str] = set()
            valid_total = True
            for influence_index, influence in enumerate(_objects(influences)):
                bone = influence.get("bone")
                weight = influence.get("weight")
                item_path = f"{influence_path}/{influence_index}"
                if isinstance(bone, str):
                    if bone not in bone_ids:
                        _error(issues, "missing_weight_bone", f"{item_path}/bone", f"unknown bone '{bone}'")
                    if bone in seen:
                        _error(issues, "duplicate_weight_bone", f"{item_path}/bone", f"bone '{bone}' occurs twice")
                    seen.add(bone)
                if not _finite_number(weight) or weight <= 0:
                    valid_total = False
                    _error(issues, "invalid_weight", f"{item_path}/weight", "weight must be finite and positive")
                else:
                    total += float(weight)
            if valid_total and not math.isclose(total, 1.0, abs_tol=self.weight_tolerance):
                _error(issues, "weight_sum", influence_path, f"weights sum to {total:.8g}, expected 1")

    def _validate_skins(
        self,
        skins: Any,
        slot_ids: set[str],
        attachment_slots: Mapping[str, str],
        issues: list[RigValidationIssue],
    ) -> None:
        if not isinstance(skins, Mapping):
            return
        for skin_id, mapping in skins.items():
            if not isinstance(mapping, Mapping):
                continue
            for slot_id, attachment_ids in mapping.items():
                path = f"/skins/{skin_id}/{slot_id}"
                if slot_id not in slot_ids:
                    _error(issues, "missing_skin_slot", path, f"unknown slot '{slot_id}'")
                if not isinstance(attachment_ids, list):
                    continue
                for index, attachment_id in enumerate(attachment_ids):
                    if attachment_id not in attachment_slots:
                        _error(issues, "missing_skin_attachment", f"{path}/{index}", f"unknown attachment '{attachment_id}'")
                    elif attachment_slots[attachment_id] != slot_id:
                        _error(issues, "skin_attachment_slot_mismatch", f"{path}/{index}", "attachment belongs to another slot")

    def _validate_animations(
        self,
        animations: Sequence[Mapping[str, Any]],
        bone_ids: set[str],
        issues: list[RigValidationIssue],
    ) -> None:
        for animation_index, animation in enumerate(animations):
            duration = animation.get("duration")
            for timeline_index, timeline in enumerate(_objects(animation.get("timelines"))):
                path = f"/animations/{animation_index}/timelines/{timeline_index}"
                bone = timeline.get("bone")
                if isinstance(bone, str) and bone not in bone_ids:
                    _error(issues, "missing_timeline_bone", f"{path}/bone", f"unknown bone '{bone}'")
                previous = -math.inf
                for key_index, key in enumerate(_objects(timeline.get("keys"))):
                    key_path = f"{path}/keys/{key_index}"
                    time = key.get("time")
                    if not _finite_number(time):
                        _error(issues, "non_finite_number", f"{key_path}/time", "time must be finite")
                    else:
                        numeric_time = float(time)
                        if numeric_time < previous:
                            _error(issues, "key_time_order", f"{key_path}/time", "key times must be nondecreasing")
                        if _finite_number(duration) and numeric_time > float(duration) + 1e-9:
                            _error(issues, "key_after_duration", f"{key_path}/time", "key occurs after animation duration")
                        previous = numeric_time
                    value = key.get("value")
                    if timeline.get("property") == "rotate":
                        if not _finite_number(value):
                            _error(issues, "invalid_rotate_value", f"{key_path}/value", "rotate value must be finite scalar")
                    else:
                        self._finite_sequence(value, f"{key_path}/value", issues)

    @staticmethod
    def _validate_retarget(retarget: Any, bone_ids: set[str], issues: list[RigValidationIssue]) -> None:
        if not isinstance(retarget, Mapping) or not isinstance(retarget.get("bone_map"), Mapping):
            return
        for role, bone in retarget["bone_map"].items():
            if isinstance(bone, str) and bone not in bone_ids:
                _error(issues, "missing_retarget_bone", f"/retarget/bone_map/{role}", f"unknown bone '{bone}'")

    @staticmethod
    def _validate_capabilities(
        rig: Mapping[str, Any],
        attachments: Sequence[Mapping[str, Any]],
        animations: Sequence[Mapping[str, Any]],
        issues: list[RigValidationIssue],
    ) -> None:
        capabilities = set(rig.get("capabilities", []))
        required = {f"{item.get('type')}_attachment" for item in attachments if item.get("type") in {"region", "mesh"}}
        required.update(
            f"bone_{timeline.get('property')}"
            for animation in animations
            for timeline in _objects(animation.get("timelines"))
            if timeline.get("property") in {"translate", "rotate", "scale"}
        )
        for capability in sorted(required - capabilities):
            _error(issues, "undeclared_capability", "/capabilities", f"data requires '{capability}'")

    @staticmethod
    def _finite_mapping(value: Any, path: str, issues: list[RigValidationIssue]) -> None:
        if not isinstance(value, Mapping):
            return
        for name, item in value.items():
            if isinstance(item, (int, float)) and not _finite_number(item):
                _error(issues, "non_finite_number", f"{path}/{name}", "value must be finite")

    @staticmethod
    def _finite_sequence(value: Any, path: str, issues: list[RigValidationIssue]) -> None:
        if not isinstance(value, (list, tuple)):
            return
        for index, item in enumerate(value):
            if not _finite_number(item):
                _error(issues, "non_finite_number", f"{path}/{index}", "value must be finite")


def _objects(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _sequences(value: Any) -> list[Sequence[Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, (list, tuple))]


def _numeric_pair(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(_finite_number(item) for item in value)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _error(issues: list[RigValidationIssue], code: str, path: str, message: str) -> None:
    issues.append(RigValidationIssue(code=code, path=path, message=message))
