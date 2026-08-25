"""Compile a reviewed P2 region RigIR into the pinned in-memory P3 mesh RigIR."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any

from .alpha_grid_mesh import build_alpha_grid_mesh
from .mesh_contract import (
    build_mesh_compile_run,
    require_base_region_rig,
    require_mesh_compile_run,
)
from .mesh_eligibility import HingeTarget, resolve_hinge_targets
from .mesh_rig_profile import (
    MeshRigProfileError,
    mesh_eligibility_check,
    mesh_eligibility_status,
    require_mesh_rig_profile,
)
from .png_rgba import RgbaImage
from .resolved_project import canonical_sha256
from .rig_fk import evaluate_world_setup
from .two_bone_weights import build_two_bone_weights, to_rigir_weights


class MeshRigError(ValueError):
    """Raised when P3 compilation cannot produce the exact pinned profile."""


@dataclass(frozen=True, slots=True)
class MeshRigCompilation:
    """Immutable result; JSON accessors always return isolated values."""

    _rig_json: str
    _run_manifest_json: str
    targets: tuple[HingeTarget, ...]
    status: str

    @property
    def rig(self) -> dict[str, Any]:
        return json.loads(self._rig_json)

    @property
    def run_manifest(self) -> dict[str, Any]:
        return json.loads(self._run_manifest_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rig": self.rig,
            "run_manifest": self.run_manifest,
            "targets": [
                {
                    "attachment_id": item.attachment_id,
                    "source_layer_id": item.source_layer_id,
                    "side": item.side,
                    "proximal_bone_id": item.proximal_bone_id,
                    "distal_bone_id": item.distal_bone_id,
                }
                for item in self.targets
            ],
            "status": self.status,
        }


def compile_mesh_rig(
    base_rig: Mapping[str, Any],
    base_run: Mapping[str, Any],
    manifest: Mapping[str, Any],
    images_by_attachment: Mapping[str, RgbaImage],
    *,
    base_bundle_sha256: str,
) -> MeshRigCompilation:
    """Convert every reviewed profile-v1 hinge atomically, or fail closed."""

    try:
        base_identity = require_base_region_rig(base_rig, base_run)
        if canonical_sha256(manifest) != base_identity["layer_manifest_sha256"]:
            raise MeshRigError(
                "Layer Manifest content address differs from the base RigIR"
            )
        run_manifest = build_mesh_compile_run(
            base_rig, base_run, base_bundle_sha256=base_bundle_sha256
        )
        require_mesh_compile_run(
            run_manifest,
            base_rig=base_rig,
            base_run=base_run,
            base_bundle_sha256=base_bundle_sha256,
        )
        targets = resolve_hinge_targets(manifest, base_rig)
        images = _require_images(images_by_attachment, targets)
        world_setup = evaluate_world_setup(base_rig.get("bones"))
        config = run_manifest["compiler"]["config"]
        converted_by_id = {
            target.attachment_id: _compile_attachment(
                _attachment(base_rig, target.attachment_id),
                target,
                images[target.attachment_id],
                world_setup,
                config,
            )
            for target in targets
        }
        rig = _assemble_rig(base_rig, run_manifest, converted_by_id, len(targets))
        require_mesh_rig_profile(
            rig,
            run_manifest,
            base_rig=base_rig,
            base_run=base_run,
            manifest=manifest,
            base_bundle_sha256=base_bundle_sha256,
            targets=targets,
        )
        encode = lambda value: json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return MeshRigCompilation(
            encode(rig),
            encode(run_manifest),
            targets,
            mesh_eligibility_status(len(targets)),
        )
    except MeshRigError:
        raise
    except (TypeError, ValueError, RuntimeError) as exc:
        raise MeshRigError(f"Could not compile mesh RigIR: {exc}") from exc


def _require_images(value, targets) -> dict[str, RgbaImage]:
    if not isinstance(value, Mapping):
        raise MeshRigError("images_by_attachment must be an object")
    expected = {target.attachment_id for target in targets}
    if set(value) != expected:
        missing, extra = sorted(expected - set(value)), sorted(set(value) - expected)
        raise MeshRigError(
            f"mesh image keys must exactly match targets; missing={missing}, extra={extra}"
        )
    result = dict(value)
    if any(not isinstance(image, RgbaImage) for image in result.values()):
        raise MeshRigError("every mesh target image must be an RgbaImage")
    return result


def _attachment(base_rig, attachment_id) -> Mapping[str, Any]:
    matches = [
        item for item in base_rig.get("attachments", [])
        if isinstance(item, Mapping) and item.get("id") == attachment_id
    ]
    if len(matches) != 1:
        raise MeshRigError(f"target attachment {attachment_id} is not unique")
    return matches[0]


def _compile_attachment(base, target, image, world_setup, config) -> dict[str, Any]:
    size = base.get("size")
    if size != [image.width, image.height]:
        raise MeshRigError(
            f"target image {target.attachment_id} size does not match its base region"
        )
    mesh = build_alpha_grid_mesh(
        image,
        grid_step_px=config["grid_step_px"],
        alpha_threshold=config["alpha_threshold"],
    )
    proximal = world_setup[target.proximal_bone_id]
    distal = world_setup[target.distal_bone_id]
    offset = base.get("canvas_offset_xy")
    if not isinstance(offset, list) or len(offset) != 2:
        raise MeshRigError(f"target attachment {target.attachment_id} offset is invalid")
    canvas_vertices = tuple(
        (offset[0] + point[0], offset[1] + point[1]) for point in mesh.vertices_xy
    )
    weight_result = build_two_bone_weights(
        canvas_vertices,
        proximal_bone_id=target.proximal_bone_id,
        distal_bone_id=target.distal_bone_id,
        proximal_origin_xy=proximal["origin_xy"],
        proximal_endpoint_xy=proximal["endpoint_xy"],
        distal_origin_xy=distal["origin_xy"],
        distal_endpoint_xy=distal["endpoint_xy"],
        grid_step_px=config["grid_step_px"],
        blend_fraction=config["blend_fraction"],
    )
    result = deepcopy(dict(base))
    result.pop("size", None)
    result.update(
        type="mesh",
        vertices=[list(point) for point in mesh.vertices_xy],
        uvs=[list(point) for point in mesh.uvs],
        triangles=[index for triangle in mesh.triangles for index in triangle],
        weights=to_rigir_weights(weight_result),
    )
    return result


def _assemble_rig(base_rig, run_manifest, converted_by_id, target_count):
    result = deepcopy(dict(base_rig))
    result["source"]["run_manifest_sha256"] = canonical_sha256(run_manifest)
    result["attachments"] = [
        deepcopy(converted_by_id.get(item["id"], item))
        for item in base_rig["attachments"]
    ]
    if target_count:
        result["capabilities"] = [
            "region_attachment", "mesh_attachment", "setup_draw_order"
        ]
    result["qa"]["status"] = "passed"
    result["qa"]["checks"] = [
        *deepcopy(base_rig["qa"]["checks"]),
        mesh_eligibility_check(target_count),
    ]
    return result
