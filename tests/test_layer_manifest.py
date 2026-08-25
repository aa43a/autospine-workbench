"""Region-first Layer Manifest materialization tests."""

from __future__ import annotations

import binascii
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBuilder,
    LayerManifestBundleStore,
    LayerManifestError,
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
    layer = {
        "id": "layer-001-arm-l",
        "source_index": 1,
        "name": "arm-l",
        "canonical_role": "body.arm.lower",
        "side": "left",
        "disposition": "keep",
        "visible": True,
        "empty": False,
        "opacity": 1.0,
        "blend_mode": "BlendMode.NORMAL",
        "z_index": 3,
        "bbox": {"x": 10, "y": 20, "width": 30, "height": 40},
        "pivot_xy": [20, 25],
        "review_state": "manual_adjusted",
        "reviewed_fields": ["canonical_role", "side", "disposition", "pivot_xy"],
        "notes": "confirmed arm",
        "metrics": {"alpha_nonzero": 900, "component_count": 1},
    }
    return {
        "id": "sample-a",
        "source": {"sha256": "a" * 64, "audit_sha256": "b" * 64},
        "canvas": {"width": 100, "height": 200},
        "layers": [layer],
        "resolved": {
            "revision": 2,
            "canvas": {"width": 100, "height": 200},
            "layers": [layer],
        },
    }


class LayerManifestMaterializationTests(unittest.TestCase):
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
        self.assertEqual("passed", manifest["qa"]["status"])
        if Draft202012Validator is not None:
            schema = json.loads(
                (WORKBENCH_ROOT / "schemas" / "layer-manifest-v1.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            Draft202012Validator(schema).validate(manifest)

    def test_unrelated_override_does_not_claim_semantic_or_pivot_review(self) -> None:
        project = project_fixture()
        layer = project["resolved"]["layers"][0]
        layer["reviewed_fields"] = ["visible"]
        layer["metrics"]["component_count"] = 2
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
            with self.assertRaisesRegex(LayerManifestError, "Windows-reserved"):
                LayerManifestBuilder().build(reserved, {"CON": asset})

            outside = project_fixture()
            outside["resolved"]["layers"][0]["bbox"]["x"] = 80
            with self.assertRaisesRegex(LayerManifestError, "outside its canvas"):
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
