"""Region-first Layer Manifest materialization tests."""

from __future__ import annotations

import binascii
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBuilder,
    LayerManifestBundleStore,
    LayerManifestError,
    _deform_class,
)
from autospine_workbench.current_project_chain import (  # noqa: E402
    rebuild_current_project_chains,
)
from autospine_workbench.mesh_eligibility import (  # noqa: E402
    resolve_hinge_targets,
)
from tests.resolved_snapshot_helpers import (  # noqa: E402
    refresh_resolved_snapshot,
    resolved_bone,
    resolved_joint,
    resolved_layer,
    resolved_project_envelope,
    resolved_snapshot_from_parts,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, *, color_type: int = 6) -> None:
    channels = 4 if color_type == 6 else 3
    pixel = bytes([80, 120, 160, 255][:channels])
    raw = b"".join(b"\x00" + pixel * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def project_fixture() -> dict:
    revision = 2
    layer = resolved_layer(
        "layer-001-arm-l",
        project_id="sample-a",
        revision=revision,
        source_index=1,
        z_index=0,
        name="arm-l",
        canonical_role="body.arm.upper",
        side="left",
        bbox_xywh=(10, 20, 30, 40),
        pivot_xy=(20, 25),
        notes="confirmed arm",
        alpha_nonzero=900,
    )
    joints = [
        resolved_joint(
            "root", side="center", x=50, y=180, revision=revision
        ),
        resolved_joint(
            "tip", side="center", x=50, y=100, revision=revision
        ),
    ]
    bones = [
        resolved_bone(
            "root-tip", start_joint_id="root", end_joint_id="tip"
        )
    ]
    resolved = resolved_snapshot_from_parts(
        project_id="sample-a",
        revision=revision,
        width=100,
        height=200,
        layers=[layer],
        joints=joints,
        bones=bones,
    )
    return resolved_project_envelope(resolved)


class LayerManifestMaterializationTests(unittest.TestCase):
    def test_current_chain_detects_manifest_algorithm_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            project = project_fixture()

            class Store:
                def get_project(self, project_id):
                    if project_id != project["id"]:
                        raise AssertionError("unexpected project")
                    return project

                def resolve_asset(self, project_id, kind, layer_id):
                    if (project_id, kind, layer_id) != (
                        project["id"], "layer", "layer-001-arm-l",
                    ):
                        raise AssertionError("unexpected asset")
                    return asset

            first = rebuild_current_project_chains(Store(), [project["id"]])[
                project["id"]
            ]
            with patch(
                "autospine_workbench.layer_manifest._deform_class",
                return_value="hinge",
            ):
                second = rebuild_current_project_chains(
                    Store(), [project["id"]],
                )[project["id"]]
        self.assertEqual(
            first.resolved_project_sha256,
            second.resolved_project_sha256,
        )
        self.assertNotEqual(
            first.layer_manifest_sha256,
            second.layer_manifest_sha256,
        )

    def test_profile_v1_only_emits_supported_generic_leg_hinges(self) -> None:
        expected = {
            "body.leg": "hinge",
            "body.arm.upper": "rigid",
            "body.arm.lower": "rigid",
            "body.leg.upper": "rigid",
            "body.leg.lower": "rigid",
        }
        for role, deform_class in expected.items():
            with self.subTest(role=role):
                self.assertEqual(deform_class, _deform_class(role))

    def test_reviewed_layer_builds_a_schema_valid_region_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            manifest = LayerManifestBuilder().build(
                project_fixture(), {"layer-001-arm-l": asset}
            )
        layer = manifest["layers"][0]
        self.assertEqual("region", layer["rig_hint"]["attachment_kind"])
        self.assertEqual("manual", layer["semantic"]["mapping_method"])
        self.assertEqual([10, 20], layer["raster"]["canvas_offset_xy"])
        self.assertEqual("left", layer["semantic"]["side"])
        self.assertEqual("rigid", layer["rig_hint"]["deform_class"])
        self.assertEqual((), resolve_hinge_targets(manifest, {}))
        self.assertEqual("passed", manifest["qa"]["status"])
        if Draft202012Validator is not None:
            schema = json.loads(
                (WORKBENCH_ROOT / "schemas" / "layer-manifest-v1.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            Draft202012Validator(schema).validate(manifest)

    def test_builder_rejects_resealed_unknown_resolved_authority(self) -> None:
        project = project_fixture()
        project["resolved"]["layers"][0]["release_approved"] = True
        project["resolved"] = refresh_resolved_snapshot(project["resolved"])
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            with self.assertRaisesRegex(LayerManifestError, "authority field"):
                LayerManifestBuilder().build(
                    project, {"layer-001-arm-l": asset}
                )

    def test_builder_requires_exact_trusted_override_context(self) -> None:
        project = project_fixture()
        project.pop("overrides")
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            with self.assertRaisesRegex(LayerManifestError, "override state"):
                LayerManifestBuilder().build(
                    project, {"layer-001-arm-l": asset}
                )

    def test_unrelated_override_does_not_claim_semantic_or_pivot_review(self) -> None:
        project = project_fixture()
        layer = project["resolved"]["layers"][0]
        layer["reviewed_fields"] = ["visible", "notes"]
        layer["metrics"]["component_count"] = 2
        project["resolved"] = refresh_resolved_snapshot(project["resolved"])
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            manifest = LayerManifestBuilder().build(
                project, {"layer-001-arm-l": asset}
            )
        built = manifest["layers"][0]
        self.assertEqual("alias", built["semantic"]["mapping_method"])
        self.assertEqual("unknown", built["rig_hint"]["pivot"]["method"])
        self.assertEqual("manual_required", manifest["qa"]["status"])
        self.assertIn("SEMANTIC_REVIEW_REQUIRED", built["qa"]["flags"])
        self.assertIn("PIVOT_REVIEW_REQUIRED", built["qa"]["flags"])
        self.assertIn("MULTIPLE_ALPHA_COMPONENTS", built["qa"]["flags"])

    def test_explicit_keep_accepts_multiple_components(self) -> None:
        project = project_fixture()
        layer = project["resolved"]["layers"][0]
        layer["metrics"]["component_count"] = 2
        project["resolved"] = refresh_resolved_snapshot(project["resolved"])
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            manifest = LayerManifestBuilder().build(
                project, {"layer-001-arm-l": asset}
            )
        self.assertNotIn("MULTIPLE_ALPHA_COMPONENTS", manifest["qa"]["flags"])

    def test_bundle_is_content_addressed_idempotent_and_verifies_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "arm.png"
            write_png(asset, 30, 40)
            assets = {"layer-001-arm-l": asset}
            manifest = LayerManifestBuilder().build(project_fixture(), assets)
            store = LayerManifestBundleStore(root / "state")
            first_path, first_sha = store.publish("sample-a", manifest, assets)
            second_path, second_sha = store.publish("sample-a", manifest, assets)
            self.assertEqual((first_path, first_sha), (second_path, second_sha))
            self.assertTrue((first_path / "manifest.json").is_file())
            self.assertEqual(first_sha, first_path.name)

            write_png(first_path / "layers" / "layer-001-arm-l.png", 30, 40, color_type=2)
            with self.assertRaises(LayerManifestError):
                store.publish("sample-a", manifest, assets)

    def test_non_rgba_or_misaligned_png_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40, color_type=2)
            with self.assertRaisesRegex(LayerManifestError, "8-bit RGBA"):
                LayerManifestBuilder().build(
                    project_fixture(), {"layer-001-arm-l": asset}
                )
            write_png(asset, 31, 40)
            with self.assertRaisesRegex(LayerManifestError, "dimensions"):
                LayerManifestBuilder().build(
                    project_fixture(), {"layer-001-arm-l": asset}
                )

    def test_builder_rejects_reserved_aliases_and_out_of_canvas_crops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            reserved = project_fixture()
            reserved["resolved"]["layers"][0]["id"] = "CON"
            reserved["resolved"]["layers"][0]["image_url"] = (
                "/api/projects/sample-a/layers/CON/image"
            )
            reserved["resolved"] = refresh_resolved_snapshot(reserved["resolved"])
            with self.assertRaisesRegex(LayerManifestError, "Windows-reserved"):
                LayerManifestBuilder().build(reserved, {"CON": asset})

            outside = project_fixture()
            outside["resolved"]["layers"][0]["bbox"]["x"] = 80
            outside["resolved"]["layers"][0]["bbox"]["right"] = 110
            outside["resolved"] = refresh_resolved_snapshot(outside["resolved"])
            with self.assertRaisesRegex(LayerManifestError, "outside (?:the|its) canvas"):
                LayerManifestBuilder().build(
                    outside, {"layer-001-arm-l": asset}
                )

    def test_publish_rejects_noncanonical_path_before_creating_a_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "arm.png"
            write_png(asset, 30, 40)
            assets = {"layer-001-arm-l": asset}
            manifest = LayerManifestBuilder().build(project_fixture(), assets)
            manifest["layers"][0]["raster"]["artifact_path"] = "../escape.png"
            store = LayerManifestBundleStore(root / "state")
            with self.assertRaisesRegex(LayerManifestError, "not canonical"):
                store.publish("sample-a", manifest, assets)
            self.assertFalse((root / "state" / "builds").exists())
            self.assertFalse((root / "escape.png").exists())

    def test_materialized_overlay_does_not_mutate_or_rehash_resolved_snapshot(self) -> None:
        project = project_fixture()
        resolved_before = json.dumps(project["resolved"], sort_keys=True)
        derived = dict(project["resolved"]["layers"][0])
        derived["id"] = "layer-001-arm-l--left"
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            manifest = LayerManifestBuilder().build(
                project,
                {derived["id"]: asset},
                materialized_layers=[derived],
            )
        self.assertEqual([derived["id"]], [item["layer_id"] for item in manifest["layers"]])
        self.assertEqual(resolved_before, json.dumps(project["resolved"], sort_keys=True))

    def test_duplicate_materialized_layer_ids_fail_loudly(self) -> None:
        project = project_fixture()
        layer = project["resolved"]["layers"][0]
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            with self.assertRaisesRegex(LayerManifestError, "duplicated"):
                LayerManifestBuilder().build(
                    project,
                    {layer["id"]: asset},
                    materialized_layers=[layer, layer],
                )

            alias = dict(layer)
            alias["id"] = layer["id"].upper()
            with self.assertRaisesRegex(LayerManifestError, "duplicated"):
                LayerManifestBuilder().build(
                    project,
                    {layer["id"]: asset, alias["id"]: asset},
                    materialized_layers=[layer, alias],
                )

            with self.assertRaisesRegex(LayerManifestError, "must be objects"):
                LayerManifestBuilder().build(
                    project,
                    {layer["id"]: asset},
                    materialized_layers=[layer, None],
                )


if __name__ == "__main__":
    unittest.main()
