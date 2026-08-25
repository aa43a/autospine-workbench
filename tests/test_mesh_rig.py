"""Atomic in-memory P3 mesh RigIR compiler tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_rig import (  # noqa: E402
    MeshRigError,
    compile_mesh_rig,
)
from autospine_workbench.mesh_rig_profile import (  # noqa: E402
    MeshRigProfileError,
    require_mesh_rig_profile,
)
from autospine_workbench.png_rgba import RgbaImage  # noqa: E402
from autospine_workbench.region_rig import compile_region_rig  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_validation import RigSemanticValidator  # noqa: E402
from tests.test_region_rig import (  # noqa: E402
    compile_fixture,
    manifest_fixture,
)


BASE_BUNDLE_SHA = "d" * 64


def solid(width: int, height: int, alpha: int = 255) -> RgbaImage:
    return RgbaImage(width, height, bytes((20, 40, 60, alpha)) * width * height)


def _layer(layer_id, *, role, side, bone, offset, size, order, deform):
    width, height = size
    return {
        "layer_id": layer_id,
        "source": {
            "name": layer_id, "index": order, "group_path": [], "visible": True,
            "opacity": 1.0, "blend_mode": "normal",
        },
        "raster": {
            "artifact_path": f"layers/{layer_id}.png",
            "sha256": f"{order + 1:x}" * 64,
            "canvas_size": [160, 100],
            "crop_bbox_xywh": [offset[0], offset[1], width, height],
            "canvas_offset_xy": list(offset), "channels": "RGBA",
            "alpha_mode": "straight", "color_space": "srgb",
            "alpha_nonzero": width * height,
        },
        "semantic": {
            "source_tag": layer_id, "canonical_role": role, "side": side,
            "stratum": "body", "instance": 0, "mapping_method": "manual",
            "confidence": 1.0,
        },
        "derivation": {"operation": "source", "parent_layer_ids": []},
        "rig_hint": {
            "attachment_kind": "region", "deform_class": deform,
            "candidate_bone": bone,
            "pivot": {"xy": [width // 2, height // 2], "method": "manual", "confidence": 1.0},
            "setup_draw_order": order,
        },
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def manifest_a() -> dict:
    layers = [
        _layer(
            "torso", role="body.torso", side="center", bone="spine",
            offset=(72, 10), size=(16, 64), order=0, deform="rigid",
        ),
        _layer(
            "leg-right", role="body.leg", side="right", bone="thigh.right",
            offset=(104, 0), size=(32, 80), order=2, deform="hinge",
        ),
        _layer(
            "leg-left", role="body.leg", side="left", bone="thigh.left",
            offset=(24, 0), size=(32, 80), order=1, deform="hinge",
        ),
    ]
    return {
        "format": "autospine-layer-manifest", "format_version": 1,
        "project_id": "mesh-a", "revision": 1,
        "source": {
            "psd_sha256": "a" * 64, "audit_sha256": "b" * 64,
            "canvas": [160, 100],
            "coordinate_system": {
                "origin": "top_left", "x_axis": "right", "y_axis": "down",
                "units": "pixel", "side_naming": "character_side",
                "view_orientation": "front", "mirror_state": "not_mirrored",
            },
        },
        "layers": layers,
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def _seal(document: dict) -> dict:
    document.pop("sha256", None)
    document["sha256"] = canonical_sha256(document)
    return document


def resolved_a() -> dict:
    joints = [
        {"id": "spine-start", "x": 80, "y": 90, "confidence": 1.0, "decision_kind": "manual_absolute"},
        {"id": "spine-end", "x": 80, "y": 10, "confidence": 1.0, "decision_kind": "manual_absolute"},
    ]
    bones = [{
        "id": "spine", "parent_id": None,
        "start_joint_id": "spine-start", "end_joint_id": "spine-end",
    }]
    for side, x in (("left", 40), ("right", 120)):
        joints.extend([
            {"id": f"hip.{side}", "x": x, "y": 0, "confidence": 1.0, "decision_kind": "manual_absolute"},
            {"id": f"knee.{side}", "x": x, "y": 40, "confidence": 1.0, "decision_kind": "manual_absolute"},
            {"id": f"ankle.{side}", "x": x, "y": 80, "confidence": 1.0, "decision_kind": "manual_absolute"},
        ])
        bones.extend([
            {"id": f"thigh.{side}", "parent_id": None, "start_joint_id": f"hip.{side}", "end_joint_id": f"knee.{side}"},
            {"id": f"calf.{side}", "parent_id": f"thigh.{side}", "start_joint_id": f"knee.{side}", "end_joint_id": f"ankle.{side}"},
        ])
    return _seal({
        "schema_version": "autospine.resolved-project/v1",
        "project_id": "mesh-a", "revision": 1,
        "inputs": {"base_project_sha256": "c" * 64, "override_sha256": "2" * 64},
        "canvas": {"width": 160, "height": 100},
        "layers": [], "skeleton": {"joints": joints, "bones": bones},
        "qa": {"status": "ready", "review_layer_ids": [], "unresolved_joint_ids": []},
    })


def base_a() -> tuple[dict, dict, dict]:
    manifest = manifest_a()
    result = compile_region_rig(
        manifest, resolved_a(), layer_manifest_sha256=canonical_sha256(manifest),
        image_sizes={"torso": (16, 64), "leg-left": (32, 80), "leg-right": (32, 80)},
    )
    return result.rig, result.run_manifest, manifest


def images_a() -> dict[str, RgbaImage]:
    return {"leg-right": solid(32, 80), "leg-left": solid(32, 80)}


def compile_a():
    rig, run, manifest = base_a()
    return compile_mesh_rig(
        rig, run, manifest, images_a(), base_bundle_sha256=BASE_BUNDLE_SHA
    )


def _reverse_keys(value):
    if isinstance(value, dict):
        return {key: _reverse_keys(item) for key, item in reversed(list(value.items()))}
    if isinstance(value, list):
        return [_reverse_keys(item) for item in value]
    return value


class MeshRigCompilerTests(unittest.TestCase):
    def test_synthetic_a_converts_two_hinges_and_preserves_non_target(self) -> None:
        base_rig, base_run, manifest = base_a()
        result = compile_mesh_rig(
            base_rig, base_run, manifest, images_a(),
            base_bundle_sha256=BASE_BUNDLE_SHA,
        )
        rig = result.rig

        self.assertEqual("converted=2", result.status)
        self.assertEqual(["leg-left", "leg-right"], [item.attachment_id for item in result.targets])
        self.assertEqual(
            ["region_attachment", "mesh_attachment", "setup_draw_order"],
            rig["capabilities"],
        )
        by_id = {item["id"]: item for item in rig["attachments"]}
        base_by_id = {item["id"]: item for item in base_rig["attachments"]}
        self.assertEqual(base_by_id["torso"], by_id["torso"])
        for attachment_id in ("leg-left", "leg-right"):
            mesh = by_id[attachment_id]
            self.assertEqual("mesh", mesh["type"])
            self.assertNotIn("size", mesh)
            self.assertEqual([0, 0], mesh["vertices"][0])
            self.assertEqual([32, 80], mesh["vertices"][-1])
            self.assertEqual(len(mesh["vertices"]), len(mesh["uvs"]))
            self.assertEqual(len(mesh["vertices"]), len(mesh["weights"]))
            self.assertEqual(0, len(mesh["triangles"]) % 3)
            for field in set(base_by_id[attachment_id]) - {"type", "size"}:
                self.assertEqual(base_by_id[attachment_id][field], mesh[field])
        self.assertEqual([], RigSemanticValidator().validate(rig))
        require_mesh_rig_profile(
            rig, result.run_manifest, base_rig=base_rig, base_run=base_run,
            manifest=manifest, base_bundle_sha256=BASE_BUNDLE_SHA,
            targets=result.targets,
        )
        self.assertEqual("converted=2", rig["qa"]["checks"][-1]["message"])

    def test_synthetic_b_is_reviewed_noop_with_p2_subtrees_intact(self) -> None:
        base = compile_fixture()
        result = compile_mesh_rig(
            base.rig, base.run_manifest, manifest_fixture(), {},
            base_bundle_sha256=BASE_BUNDLE_SHA,
        )
        self.assertEqual((), result.targets)
        self.assertEqual("reviewed-noop", result.status)
        for field in (
            "canvas", "capabilities", "bones", "slots", "attachments", "skins", "animations",
        ):
            self.assertEqual(base.rig[field], result.rig[field])
        self.assertEqual("reviewed-noop", result.rig["qa"]["checks"][-1]["message"])

    def test_result_is_immutable_and_accessors_are_isolated(self) -> None:
        result = compile_a()
        changed = result.rig
        changed["attachments"][0]["type"] = "tampered"
        self.assertNotEqual("tampered", result.rig["attachments"][0]["type"])
        with self.assertRaises(FrozenInstanceError):
            result.status = "changed"  # type: ignore[misc]

    def test_deterministic_under_mapping_key_and_image_order(self) -> None:
        rig, run, manifest = base_a()
        before = deepcopy((rig, run, manifest))
        first = compile_mesh_rig(
            rig, run, manifest, images_a(), base_bundle_sha256=BASE_BUNDLE_SHA
        )
        reversed_images = dict(reversed(list(images_a().items())))
        second = compile_mesh_rig(
            _reverse_keys(rig), _reverse_keys(run), _reverse_keys(manifest),
            reversed_images, base_bundle_sha256=BASE_BUNDLE_SHA,
        )
        self.assertEqual(first, second)
        self.assertEqual(before, (rig, run, manifest))

    def test_images_are_an_exact_typed_and_sized_target_map(self) -> None:
        rig, run, manifest = base_a()
        cases = (
            ({"leg-left": solid(32, 80)}, "missing"),
            ({**images_a(), "torso": solid(16, 64)}, "extra"),
            ({"leg-left": solid(32, 80), "leg-right": object()}, "RgbaImage"),
            ({"leg-left": solid(32, 79), "leg-right": solid(32, 80)}, "size"),
        )
        for images, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(MeshRigError, message):
                compile_mesh_rig(
                    rig, run, manifest, images, base_bundle_sha256=BASE_BUNDLE_SHA
                )
        base = compile_fixture()
        with self.assertRaisesRegex(MeshRigError, "extra"):
            compile_mesh_rig(
                base.rig, base.run_manifest, manifest_fixture(), {"torso": solid(30, 40)},
                base_bundle_sha256=BASE_BUNDLE_SHA,
            )

    def test_one_bad_side_fails_the_whole_pure_compilation(self) -> None:
        rig, run, manifest = base_a()
        before = deepcopy((rig, run, manifest))
        images = images_a()
        images["leg-right"] = solid(32, 80, alpha=0)
        with self.assertRaisesRegex(MeshRigError, "no foreground"):
            compile_mesh_rig(
                rig, run, manifest, images, base_bundle_sha256=BASE_BUNDLE_SHA
            )
        self.assertEqual(before, (rig, run, manifest))

    def test_unknown_hinge_fails_before_any_result(self) -> None:
        _rig, _run, manifest = base_a()
        manifest["layers"][1]["semantic"]["canonical_role"] = "body.arm"
        compiled = compile_region_rig(
            manifest, resolved_a(),
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes={
                "torso": (16, 64), "leg-left": (32, 80), "leg-right": (32, 80)
            },
        )
        with self.assertRaisesRegex(MeshRigError, "unsupported profile-v1 role"):
            compile_mesh_rig(
                compiled.rig, compiled.run_manifest, manifest, images_a(),
                base_bundle_sha256=BASE_BUNDLE_SHA,
            )

    def test_manifest_must_be_the_base_content_address_even_if_targets_match(self) -> None:
        rig, run, manifest = base_a()
        manifest["qa"]["notes"].append("same targets, different reviewed input")
        with self.assertRaisesRegex(MeshRigError, "content address"):
            compile_mesh_rig(
                rig, run, manifest, images_a(), base_bundle_sha256=BASE_BUNDLE_SHA
            )


class MeshRigProfileTamperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_rig, self.base_run, self.manifest = base_a()
        result = compile_mesh_rig(
            self.base_rig, self.base_run, self.manifest, images_a(),
            base_bundle_sha256=BASE_BUNDLE_SHA,
        )
        self.rig, self.run, self.targets = result.rig, result.run_manifest, result.targets

    def require(self, rig=None, run=None):
        return require_mesh_rig_profile(
            rig or self.rig, run or self.run,
            base_rig=self.base_rig, base_run=self.base_run, manifest=self.manifest,
            base_bundle_sha256=BASE_BUNDLE_SHA, targets=self.targets,
        )

    def test_non_target_cardinality_and_total_limits_are_enforced(self) -> None:
        changed = deepcopy(self.rig)
        next(item for item in changed["attachments"] if item["id"] == "torso")["pivot_xy"][0] += 1
        with self.assertRaisesRegex(MeshRigProfileError, "non-target"):
            self.require(changed)

        changed = deepcopy(self.rig)
        next(item for item in changed["attachments"] if item["type"] == "mesh")["uvs"].pop()
        with self.assertRaisesRegex(MeshRigProfileError, "invalid"):
            self.require(changed)

        with patch("autospine_workbench.mesh_rig_profile.RIG_VERTEX_LIMIT", 1):
            with self.assertRaisesRegex(MeshRigProfileError, "total resources"):
                self.require()

    def test_weight_bones_classes_sums_and_uint16_lattice_are_enforced(self) -> None:
        def first_mesh(rig):
            return next(item for item in rig["attachments"] if item["type"] == "mesh")

        changed = deepcopy(self.rig)
        mixed = next(items for items in first_mesh(changed)["weights"] if len(items) == 2)
        mixed[0]["bone"] = "spine"
        with self.assertRaisesRegex(MeshRigProfileError, "non-designated"):
            self.require(changed)

        changed = deepcopy(self.rig)
        mesh = first_mesh(changed)
        for index, items in enumerate(mesh["weights"]):
            if len(items) == 2:
                mesh["weights"][index] = [{"bone": items[0]["bone"], "weight": 1.0}]
        with self.assertRaisesRegex(MeshRigProfileError, "weight class"):
            self.require(changed)

        changed = deepcopy(self.rig)
        mesh = first_mesh(changed)
        proximal = next(items[0]["bone"] for items in mesh["weights"] if len(items) == 1)
        distal = next(
            target.distal_bone_id for target in self.targets
            if target.attachment_id == mesh["id"]
        )
        for index, items in enumerate(mesh["weights"]):
            if len(items) == 1 and items[0]["bone"] == proximal:
                mesh["weights"][index] = [{"bone": distal, "weight": 1.0}]
        with self.assertRaisesRegex(MeshRigProfileError, "weight class"):
            self.require(changed)

        changed = deepcopy(self.rig)
        mixed = next(items for items in first_mesh(changed)["weights"] if len(items) == 2)
        mixed[1]["bone"] = mixed[0]["bone"]
        with self.assertRaisesRegex(MeshRigProfileError, "occurs twice"):
            self.require(changed)

        changed = deepcopy(self.rig)
        mixed = next(items for items in first_mesh(changed)["weights"] if len(items) == 2)
        mixed[0]["weight"] += 1e-6
        mixed[1]["weight"] -= 1e-6
        with self.assertRaisesRegex(MeshRigProfileError, "uint16 lattice"):
            self.require(changed)

        changed = deepcopy(self.rig)
        mixed = next(items for items in first_mesh(changed)["weights"] if len(items) == 2)
        mixed[0]["weight"] -= 1 / 65535
        with self.assertRaisesRegex(MeshRigProfileError, "weights sum"):
            self.require(changed)


if __name__ == "__main__":
    unittest.main()
