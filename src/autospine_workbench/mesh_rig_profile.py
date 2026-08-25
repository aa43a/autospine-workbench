"""Semantic proof for the pinned P3 two-bone mesh RigIR profile."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import math
from typing import Any

from .mesh_contract import require_mesh_compile_run
from .mesh_eligibility import HingeTarget, resolve_hinge_targets
from .mesh_topology import validate_mesh_topology
from .resolved_project import canonical_sha256
from .rig_validation import RigSemanticValidator


RIG_VERTEX_LIMIT = 32768
RIG_TRIANGLE_LIMIT = 65536
WEIGHT_QUANTIZATION = 65535
WEIGHT_TOLERANCE = 1e-12
MESH_ELIGIBILITY_CHECK_ID = "attachments.mesh-eligibility"


class MeshRigProfileError(ValueError):
    """Raised when a compiled rig is not an exact P3 profile result."""


def mesh_eligibility_status(target_count: int) -> str:
    """Return stable human-readable evidence for the reviewed target set."""

    if not isinstance(target_count, int) or isinstance(target_count, bool) or target_count < 0:
        raise MeshRigProfileError("mesh target count must be a non-negative integer")
    return f"converted={target_count}" if target_count else "reviewed-noop"


def mesh_eligibility_check(target_count: int) -> dict[str, str]:
    return {
        "id": MESH_ELIGIBILITY_CHECK_ID,
        "status": "passed",
        "message": mesh_eligibility_status(target_count),
    }


def require_mesh_rig_profile(
    rig: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    *,
    base_rig: Mapping[str, Any],
    base_run: Mapping[str, Any],
    manifest: Mapping[str, Any],
    base_bundle_sha256: str,
    targets: Sequence[HingeTarget] | None = None,
) -> tuple[HingeTarget, ...]:
    """Prove run binding, exact P2 preservation, and bounded mesh semantics."""

    try:
        require_mesh_compile_run(
            run_manifest,
            base_rig=base_rig,
            base_run=base_run,
            base_bundle_sha256=base_bundle_sha256,
        )
        if canonical_sha256(manifest) != run_manifest["inputs"]["layer_manifest_sha256"]:
            raise MeshRigProfileError(
                "Layer Manifest content address differs from the mesh compile run"
            )
        RigSemanticValidator(max_influences=2).raise_for_errors(rig)
        expected_targets = resolve_hinge_targets(manifest, base_rig)
        if targets is not None and tuple(targets) != expected_targets:
            raise MeshRigProfileError("compiled mesh targets differ from reviewed eligibility")
        _require_run_source(rig, run_manifest, base_rig)
        _require_preserved_rig(rig, base_rig, expected_targets)
        _require_meshes(rig, base_rig, expected_targets)
        _require_qa(rig, base_rig, len(expected_targets))
        return expected_targets
    except MeshRigProfileError:
        raise
    except (TypeError, ValueError, RuntimeError) as exc:
        raise MeshRigProfileError(f"mesh RigIR profile is invalid: {exc}") from exc


def _require_run_source(rig, run_manifest, base_rig) -> None:
    source = _object(rig.get("source"), "mesh RigIR source")
    base_source = _object(base_rig.get("source"), "base RigIR source")
    expected = deepcopy(dict(base_source))
    expected["run_manifest_sha256"] = canonical_sha256(run_manifest)
    _same(source, expected, "mesh RigIR source changed outside its run binding")


def _require_preserved_rig(rig, base_rig, targets) -> None:
    if set(rig) != set(base_rig):
        raise MeshRigProfileError("mesh RigIR top-level fields differ from its base")
    for field in (
        "format", "format_version", "canvas", "unsupported_feature_policy",
        "bones", "slots", "skins", "animations",
    ):
        _same(rig.get(field), base_rig.get(field), f"mesh RigIR {field} subtree changed")
    expected_capabilities = (
        ["region_attachment", "mesh_attachment", "setup_draw_order"]
        if targets else base_rig.get("capabilities")
    )
    _same(rig.get("capabilities"), expected_capabilities, "mesh capabilities are invalid")
    if rig.get("animations") != [] or "bone_rotate" in (rig.get("capabilities") or []):
        raise MeshRigProfileError("P3 mesh profile cannot declare animation or rotation")


def _require_meshes(rig, base_rig, targets) -> None:
    actual = _attachments(rig.get("attachments"), "mesh RigIR attachments")
    base = _attachments(base_rig.get("attachments"), "base RigIR attachments")
    target_by_id = {target.attachment_id: target for target in targets}
    if set(actual) != set(base):
        raise MeshRigProfileError("mesh attachment ids differ from the base RigIR")
    mesh_ids = {item_id for item_id, item in actual.items() if item.get("type") == "mesh"}
    if mesh_ids != set(target_by_id):
        raise MeshRigProfileError("mesh attachment set differs from reviewed targets")

    total_vertices = total_triangles = 0
    for attachment_id, base_attachment in base.items():
        attachment = actual[attachment_id]
        target = target_by_id.get(attachment_id)
        if target is None:
            _same(attachment, base_attachment, f"non-target attachment {attachment_id} changed")
            continue
        _require_preserved_attachment(attachment, base_attachment, attachment_id)
        vertices = _array(attachment.get("vertices"), f"mesh {attachment_id} vertices")
        uvs = _array(attachment.get("uvs"), f"mesh {attachment_id} uvs")
        weights = _array(attachment.get("weights"), f"mesh {attachment_id} weights")
        triangles = _array(attachment.get("triangles"), f"mesh {attachment_id} triangles")
        if len(vertices) != len(uvs) or len(vertices) != len(weights) or len(triangles) % 3:
            raise MeshRigProfileError(f"mesh {attachment_id} cardinality is invalid")
        size = _size(base_attachment.get("size"), attachment_id)
        triangle_rows = [triangles[index:index + 3] for index in range(0, len(triangles), 3)]
        validate_mesh_topology(
            vertices_xy=vertices, uvs=uvs, triangles=triangle_rows,
            width_px=size[0], height_px=size[1],
        )
        _require_target_weights(weights, target)
        total_vertices += len(vertices)
        total_triangles += len(triangle_rows)
    if total_vertices > RIG_VERTEX_LIMIT or total_triangles > RIG_TRIANGLE_LIMIT:
        raise MeshRigProfileError(
            f"mesh RigIR exceeds total resources ({RIG_VERTEX_LIMIT} vertices, "
            f"{RIG_TRIANGLE_LIMIT} triangles)"
        )


def _require_preserved_attachment(attachment, base, attachment_id) -> None:
    expected_keys = (set(base) - {"size"}) | {"vertices", "uvs", "triangles", "weights"}
    if set(attachment) != expected_keys or attachment.get("type") != "mesh":
        raise MeshRigProfileError(f"target attachment {attachment_id} fields are invalid")
    for field in set(base) - {"type", "size"}:
        _same(
            attachment.get(field), base.get(field),
            f"target attachment {attachment_id} changed base field {field}",
        )


def _require_target_weights(weights, target: HingeTarget) -> None:
    allowed = {target.proximal_bone_id, target.distal_bone_id}
    used: set[str] = set()
    classes: set[str] = set()
    for vertex_index, raw in enumerate(weights):
        influences = _array(raw, f"mesh {target.attachment_id} weight {vertex_index}")
        if len(influences) not in (1, 2):
            raise MeshRigProfileError("mesh vertices must have one or two influences")
        vertex_bones: set[str] = set()
        total = 0.0
        for influence in influences:
            item = _object(influence, "mesh influence")
            if set(item) != {"bone", "weight"} or item.get("bone") not in allowed:
                raise MeshRigProfileError(
                    f"mesh {target.attachment_id} uses a non-designated bone"
                )
            bone, weight = item["bone"], item.get("weight")
            if bone in vertex_bones or not _quantized_weight(weight):
                raise MeshRigProfileError(
                    f"mesh {target.attachment_id} weights are not unique uint16 lattice values"
                )
            vertex_bones.add(bone)
            used.add(bone)
            total += float(weight)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=WEIGHT_TOLERANCE):
            raise MeshRigProfileError(f"mesh {target.attachment_id} weights do not sum to one")
        if len(influences) == 2 and vertex_bones == allowed:
            classes.add("blend")
        elif len(influences) == 1 and target.proximal_bone_id in vertex_bones:
            classes.add("proximal-only")
        elif len(influences) == 1 and target.distal_bone_id in vertex_bones:
            classes.add("distal-only")
    if used != allowed:
        raise MeshRigProfileError(f"mesh {target.attachment_id} does not use both hinge bones")
    required_classes = {"proximal-only", "distal-only", "blend"}
    if classes != required_classes:
        raise MeshRigProfileError(
            f"mesh {target.attachment_id} lacks a required two-bone weight class"
        )


def _quantized_weight(value) -> bool:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 < float(value) <= 1.0
    ):
        return False
    quantized = round(float(value) * WEIGHT_QUANTIZATION)
    return math.isclose(
        float(value), quantized / WEIGHT_QUANTIZATION,
        rel_tol=0.0, abs_tol=WEIGHT_TOLERANCE,
    )


def _require_qa(rig, base_rig, target_count) -> None:
    base_qa = deepcopy(dict(_object(base_rig.get("qa"), "base RigIR QA")))
    checks = _array(base_qa.get("checks"), "base RigIR QA checks")
    if any(isinstance(item, Mapping) and item.get("id") == MESH_ELIGIBILITY_CHECK_ID for item in checks):
        raise MeshRigProfileError("base RigIR already contains the P3 eligibility check")
    base_qa["status"] = "passed"
    base_qa["checks"] = [*checks, mesh_eligibility_check(target_count)]
    _same(rig.get("qa"), base_qa, "mesh RigIR QA evidence is invalid")


def _attachments(value, label) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in _array(value, label):
        item = _object(item, label)
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in result:
            raise MeshRigProfileError(f"{label} ids must be non-empty and unique")
        result[item_id] = item
    return result


def _size(value, attachment_id) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(
        not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in value
    ):
        raise MeshRigProfileError(f"base attachment {attachment_id} size is invalid")
    return value[0], value[1]


def _same(actual, expected, message) -> None:
    if canonical_sha256(actual) != canonical_sha256(expected):
        raise MeshRigProfileError(message)


def _object(value, label) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MeshRigProfileError(f"{label} must be an object")
    return value


def _array(value, label) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise MeshRigProfileError(f"{label} must be an array")
    return list(value)
