"""Deterministic bilateral Layer Manifest materialization tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.layer_manifest import LayerManifestBuilder, sha256_file  # noqa: E402
from autospine_workbench.layer_split_materializer import (  # noqa: E402
    LayerSplitMaterializationError,
    materialize_bilateral_splits,
)
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    read_rgba_png,
    write_rgba_png,
)


LAYER_ID = "layer-001-legs"


def source_image(*, full_canvas: bool = False) -> RgbaImage:
    width, height = (8, 4) if full_canvas else (6, 4)
    pixels = bytearray(width * height * 4)
    left = 1 if full_canvas else 0
    right = 7 if full_canvas else 6
    for y in range(height):
        for x in range(left, right):
            offset = (y * width + x) * 4
            pixels[offset : offset + 4] = bytes((20 + x, 40 + y, 80, 64 + x * 20))
    pixels[(0 * width + left) * 4 : (0 * width + left) * 4 + 4] = bytes(
        (99, 88, 77, 0)
    )
    return RgbaImage(width, height, bytes(pixels))


def project_fixture() -> dict:
    layer = {
        "id": LAYER_ID,
        "source_index": 7,
        "name": "legwear",
        "canonical_role": "body.leg",
        "side": "bilateral",
        "disposition": "split_left_right",
        "visible": True,
        "empty": False,
        "opacity": 1.0,
        "blend_mode": "normal",
        "z_index": 9,
        "bbox": {"x": 1, "y": 0, "width": 6, "height": 4},
        "pivot_xy": [4, 1],
        "candidate_bone": "root-pelvis",
        "review_state": "manual_adjusted",
        "reviewed_fields": [
            "canonical_role",
            "side",
            "disposition",
            "pivot_xy",
            "candidate_bone",
        ],
        "metrics": {"alpha_nonzero": 23, "component_count": 1},
    }
    joints = []
    for side, x, review_state in (
        ("left", 2, "candidate_accepted"),
        ("right", 5, "manual_adjusted"),
    ):
        for name, y in (("hip", 0), ("knee", 2), ("ankle", 3)):
            joints.append(
                {
                    "id": f"{name}.{side}",
                    "x": x,
                    "y": y,
                    "review_state": review_state,
                }
            )
    return {
        "id": "sample-split",
        "source": {"sha256": "a" * 64, "audit_sha256": "b" * 64},
        "canvas": {"width": 8, "height": 4},
        "layers": [deepcopy(layer)],
        "resolved": {
            "revision": 3,
            "sha256": "c" * 64,
            "canvas": {"width": 8, "height": 4},
            "layers": [deepcopy(layer)],
            "skeleton": {"joints": joints, "bones": []},
            "qa": {"status": "ready"},
        },
    }


def authored_split_spec() -> dict:
    return {
        "parts": {
            "left": {
                "guide": [
                    {"kind": "joint", "joint_id": "hip.left"},
                    {
                        "kind": "manual_proxy",
                        "proxy_id": "garment-opening.left",
                        "xy": [3, 3],
                        "label": "garment opening",
                        "reason": "the ankle is hidden by the garment",
                        "proxy_for_joint_id": "ankle.left",
                    },
                ],
                "pivot": {
                    "kind": "manual_proxy",
                    "proxy_id": "garment-pivot.left",
                    "xy": [3, 3],
                    "label": "garment opening pivot",
                    "reason": "the anatomical ankle is hidden",
                    "proxy_for_joint_id": "ankle.left",
                },
                "candidate_bone": "calf.left",
            },
            "right": {
                "guide": [
                    {"kind": "joint", "joint_id": "hip.right"},
                    {"kind": "joint", "joint_id": "ankle.right"},
                ],
                "pivot": {"kind": "joint", "joint_id": "hip.right"},
                "candidate_bone": "calf.right",
            },
        }
    }


def visible_normalized(image: RgbaImage) -> bytes:
    output = bytearray(image.pixels)
    for offset in range(0, len(output), 4):
        if output[offset + 3] == 0:
            output[offset : offset + 4] = bytes(4)
    return bytes(output)


class BilateralLayerMaterializerTests(unittest.TestCase):
    def test_v3_split_spec_controls_guides_and_pivots_with_proxy_provenance(self) -> None:
        project = project_fixture()
        layer = project["resolved"]["layers"][0]
        layer["split_spec"] = authored_split_spec()
        project["resolved"]["skeleton"]["bones"] = [
            {"id": "calf.left"},
            {"id": "calf.right"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            write_rgba_png(source, source_image())
            materialized = materialize_bilateral_splits(
                project, {LAYER_ID: source}, root / "derived"
            )
            manifest = LayerManifestBuilder().build(
                project,
                materialized.assets,
                materialized_layers=materialized.layers,
            )

        left, right = materialized.layers[1:]
        config = left["derivation"]["operation_config"]
        proxy = config["guide_anchors"]["left"][1]
        self.assertEqual("manual_proxy", proxy["kind"])
        self.assertEqual("ankle.left", proxy["proxy_for_joint_id"])
        self.assertEqual([3.0, 3.0], left["pivot_xy"])
        self.assertEqual([5.0, 0.0], right["pivot_xy"])
        self.assertEqual(config, right["derivation"]["operation_config"])
        self.assertEqual("calf.left", left["proposed_candidate_bone"])
        self.assertEqual("calf.right", right["proposed_candidate_bone"])
        self.assertEqual([], left["reviewed_fields"])
        manifest_left, manifest_right = manifest["layers"][1:]
        self.assertEqual("calf.left", manifest_left["rig_hint"]["candidate_bone"])
        self.assertEqual("calf.right", manifest_right["rig_hint"]["candidate_bone"])
        for child in (manifest_left, manifest_right):
            self.assertEqual("alias", child["semantic"]["mapping_method"])
            self.assertEqual("unknown", child["rig_hint"]["pivot"]["method"])
            self.assertEqual("manual_required", child["qa"]["status"])
            self.assertIn("BONE_BINDING_REVIEW_REQUIRED", child["qa"]["flags"])

    def test_retains_parent_and_emits_lossless_unreviewed_children(self) -> None:
        project = project_fixture()
        before = deepcopy(project)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            write_rgba_png(source, source_image())
            input_assets = {LAYER_ID: source}
            materialized = materialize_bilateral_splits(
                project, input_assets, root / "derived"
            )
            layers, assets = materialized.layers, materialized.assets
            parent, left, right = layers

            self.assertEqual(before, project)
            self.assertEqual({LAYER_ID: source}, input_assets)
            self.assertEqual([LAYER_ID, f"{LAYER_ID}--left", f"{LAYER_ID}--right"], [
                item["id"] for item in layers
            ])
            self.assertEqual([0, 1, 2], [item["z_index"] for item in layers])
            self.assertEqual("exclude", parent["disposition"])
            self.assertNotIn("disposition", parent["reviewed_fields"])
            self.assertEqual(source, assets[LAYER_ID])
            self.assertEqual(("left", "right"), (left["side"], right["side"]))
            self.assertEqual(("keep", "keep"), (left["disposition"], right["disposition"]))
            self.assertEqual((7, 7), (left["source_index"], right["source_index"]))
            self.assertNotIn("candidate_bone", left)
            self.assertEqual([], left["reviewed_fields"])
            self.assertEqual([], right["reviewed_fields"])
            self.assertEqual(("unreviewed", "unreviewed"), (
                left["review_state"], right["review_state"]
            ))
            self.assertEqual([2.0, 0.0], left["pivot_xy"])
            self.assertEqual([5.0, 0.0], right["pivot_xy"])

            left_image = read_rgba_png(assets[left["id"]])
            right_image = read_rgba_png(assets[right["id"]])
            recomposed = bytes(
                left_byte | right_byte
                for left_byte, right_byte in zip(left_image.pixels, right_image.pixels)
            )
            self.assertEqual(visible_normalized(source_image()), recomposed)
            self.assertEqual(23, left["metrics"]["alpha_nonzero"] + right["metrics"]["alpha_nonzero"])
            config = left["derivation"]["operation_config"]
            self.assertEqual(config, right["derivation"]["operation_config"])
            self.assertEqual([1, 0], config["canvas_offset_xy"])
            self.assertEqual(sha256_file(source), config["source_raster_sha256"])
            self.assertEqual(
                {
                    "left": hashlib.sha256(left_image.pixels).hexdigest(),
                    "right": hashlib.sha256(right_image.pixels).hexdigest(),
                },
                config["output_rgba_sha256"],
            )
            self.assertEqual(
                ["hip.left", "knee.left", "ankle.left"],
                [
                    anchor["joint_id"]
                    for anchor in config["guide_anchors"]["left"]
                ],
            )
            self.assertEqual(
                ["candidate_accepted"] * 3,
                [
                    anchor["review_state"]
                    for anchor in config["guide_anchors"]["left"]
                ],
            )
            self.assertTrue(
                all(
                    anchor["kind"] == "resolved_joint"
                    for side in ("left", "right")
                    for anchor in config["guide_anchors"][side]
                )
            )
            self.assertEqual("left", config["tie_break"])

    def test_canonical_outputs_and_provenance_are_repeatable(self) -> None:
        project = project_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            write_rgba_png(source, source_image())
            first = materialize_bilateral_splits(
                project, {LAYER_ID: source}, root / "first"
            )
            second = materialize_bilateral_splits(
                project, {LAYER_ID: source}, root / "second"
            )
            self.assertEqual(first.layers, second.layers)
            for side in ("left", "right"):
                child_id = f"{LAYER_ID}--{side}"
                self.assertEqual(
                    first.assets[child_id].read_bytes(), second.assets[child_id].read_bytes()
                )
                self.assertEqual(
                    sha256_file(first.assets[child_id]), sha256_file(second.assets[child_id])
                )

    def test_authoritative_z_order_is_sorted_before_stable_expansion(self) -> None:
        project = project_fixture()
        split_layer = project["resolved"]["layers"][0]
        lower = {
            **deepcopy(split_layer),
            "id": "layer-000-lower",
            "name": "lower",
            "z_index": -3,
            "disposition": "keep",
        }
        upper = {
            **deepcopy(split_layer),
            "id": "layer-999-upper",
            "name": "upper",
            "z_index": 14,
            "disposition": "keep",
        }
        project["resolved"]["layers"] = [upper, split_layer, lower]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            write_rgba_png(source, source_image())
            materialized = materialize_bilateral_splits(
                project, {LAYER_ID: source}, root / "derived"
            )

        self.assertEqual(
            [
                "layer-000-lower",
                LAYER_ID,
                f"{LAYER_ID}--left",
                f"{LAYER_ID}--right",
                "layer-999-upper",
            ],
            [layer["id"] for layer in materialized.layers],
        )
        self.assertEqual(list(range(5)), [layer["z_index"] for layer in materialized.layers])

    def test_full_canvas_source_records_zero_offset_and_builds_manifest(self) -> None:
        project = project_fixture()
        for joint in project["resolved"]["skeleton"]["joints"]:
            joint["review_state"] = "manual_adjusted"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            write_rgba_png(source, source_image(full_canvas=True))
            materialized = materialize_bilateral_splits(
                project, {LAYER_ID: source}, root / "derived"
            )
            manifest = LayerManifestBuilder().build(
                project,
                materialized.assets,
                materialized_layers=materialized.layers,
            )
        parent, left, right = manifest["layers"]
        self.assertEqual("excluded", parent["rig_hint"]["attachment_kind"])
        self.assertEqual(([0, 0], [0, 0]), (
            left["raster"]["canvas_offset_xy"], right["raster"]["canvas_offset_xy"]
        ))
        self.assertEqual("manual_required", manifest["qa"]["status"])
        self.assertIn("SEMANTIC_REVIEW_REQUIRED", manifest["qa"]["flags"])
        self.assertIn("PIVOT_REVIEW_REQUIRED", manifest["qa"]["flags"])
        self.assertEqual(("thigh.left", "thigh.right"), (
            left["rig_hint"]["candidate_bone"], right["rig_hint"]["candidate_bone"]
        ))

    def test_unreviewed_source_layer_never_gains_manual_child_claims(self) -> None:
        project = project_fixture()
        project["resolved"]["layers"][0]["reviewed_fields"] = []
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            write_rgba_png(source, source_image())
            materialized = materialize_bilateral_splits(
                project, {LAYER_ID: source}, Path(directory) / "derived"
            )
        for child in materialized.layers[1:]:
            self.assertEqual([], child["reviewed_fields"])
            self.assertNotIn("candidate_bone", child)

    def test_invalid_requests_fail_closed(self) -> None:
        mutations = {
            "non-bilateral": lambda project: project["resolved"]["layers"][0].update(side="left"),
            "unsupported role": lambda project: project["resolved"]["layers"][0].update(canonical_role="body.torso"),
            "missing joint": lambda project: project["resolved"]["skeleton"]["joints"].pop(),
            "unobservable guide": lambda project: project["resolved"]["skeleton"]["joints"][0].update(
                review_state="unobservable"
            ),
            "colliding child": lambda project: project["resolved"]["layers"].append({
                **deepcopy(project["resolved"]["layers"][0]),
                "id": f"{LAYER_ID}--left",
                "z_index": 10,
                "disposition": "keep",
            }),
            "invalid z_index": lambda project: project["resolved"]["layers"][0].update(
                z_index="9"
            ),
            "duplicate z_index": lambda project: project["resolved"]["layers"].append({
                **deepcopy(project["resolved"]["layers"][0]),
                "id": "layer-duplicate-z",
                "disposition": "keep",
            }),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                project = project_fixture()
                mutate(project)
                source = Path(directory) / "source.png"
                write_rgba_png(source, source_image())
                with self.assertRaises(LayerSplitMaterializationError):
                    materialize_bilateral_splits(
                        project, {LAYER_ID: source}, Path(directory) / "derived"
                    )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(LayerSplitMaterializationError, "missing"):
                materialize_bilateral_splits(
                    project_fixture(), {}, Path(directory) / "derived"
                )
            wrong_size = Path(directory) / "wrong.png"
            write_rgba_png(wrong_size, RgbaImage(2, 2, bytes(16)))
            with self.assertRaisesRegex(LayerSplitMaterializationError, "dimensions"):
                materialize_bilateral_splits(
                    project_fixture(), {LAYER_ID: wrong_size}, Path(directory) / "other"
                )


if __name__ == "__main__":
    unittest.main()
