"""Strict loading tests for immutable Layer Manifest bundles."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBuilder,
    LayerManifestBundleStore,
)
from autospine_workbench.manifest_bundle import (  # noqa: E402
    LayerManifestBundleError,
    LayerManifestBundleReader,
)
from tests.png_helpers import write_rgba  # noqa: E402
from tests.resolved_snapshot_helpers import (  # noqa: E402
    resolved_bone,
    resolved_joint,
    resolved_layer,
    resolved_project_envelope,
    resolved_snapshot_from_parts,
)


def project_fixture() -> dict:
    revision = 2
    layer = resolved_layer(
        "layer-arm-left",
        project_id="sample-a",
        revision=revision,
        source_index=1,
        z_index=0,
        name="arm-left",
        canonical_role="body.hand",
        side="left",
        bbox_xywh=(10, 20, 2, 2),
        pivot_xy=(10.5, 20.5),
        alpha_nonzero=4,
    )
    joints = [
        resolved_joint(
            "root", side="center", x=10, y=28, revision=revision
        ),
        resolved_joint(
            "tip", side="center", x=10, y=10, revision=revision
        ),
    ]
    resolved = resolved_snapshot_from_parts(
        project_id="sample-a",
        revision=revision,
        width=20,
        height=30,
        layers=[layer],
        joints=joints,
        bones=[resolved_bone(
            "root-tip", start_joint_id="root", end_joint_id="tip"
        )],
    )
    return resolved_project_envelope(resolved)


class LayerManifestBundleReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.asset = self.root / "arm.png"
        write_rgba(
            self.asset,
            [[(255, 0, 0, 255), (0, 255, 0, 255)]] * 2,
        )
        manifest = LayerManifestBuilder().build(
            project_fixture(), {"layer-arm-left": self.asset}
        )
        self.bundle, self.digest = LayerManifestBundleStore(self.root).publish(
            "sample-a", manifest, {"layer-arm-left": self.asset}
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_load_verifies_content_address_assets_and_image_sizes(self) -> None:
        loaded = LayerManifestBundleReader(self.root).load("sample-a", self.digest)
        self.assertEqual(self.bundle.resolve(), loaded.path)
        self.assertEqual(self.digest, loaded.sha256)
        self.assertEqual((2, 2), loaded.image_sizes["layer-arm-left"])

    def test_wrong_identity_or_tampered_manifest_fails_closed(self) -> None:
        reader = LayerManifestBundleReader(self.root)
        with self.assertRaises(LayerManifestBundleError):
            reader.load("../sample-a", self.digest)
        with self.assertRaises(LayerManifestBundleError):
            reader.load("sample-a", "not-a-sha")
        manifest_path = self.bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["revision"] += 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(LayerManifestBundleError, "content address"):
            reader.load("sample-a", self.digest)

    def test_tampered_or_escaping_layer_image_fails_closed(self) -> None:
        image = self.bundle / "layers" / "layer-arm-left.png"
        image.write_bytes(image.read_bytes() + b"tamper")
        with self.assertRaisesRegex(LayerManifestBundleError, "image hash"):
            LayerManifestBundleReader(self.root).load("sample-a", self.digest)

    def test_duplicate_layer_identity_fails_before_path_aliasing(self) -> None:
        manifest = json.loads(
            (self.bundle / "manifest.json").read_text(encoding="utf-8")
        )
        manifest["layers"].append(dict(manifest["layers"][0]))
        with self.assertRaisesRegex(LayerManifestBundleError, "duplicated"):
            LayerManifestBundleReader._verify_layers(self.bundle.resolve(), manifest)

    def test_noncanonical_traversal_and_reserved_paths_fail_closed(self) -> None:
        original = json.loads(
            (self.bundle / "manifest.json").read_text(encoding="utf-8")
        )
        for relative in (
            "../outside.png",
            "layers/./layer-arm-left.png",
            "layers\\layer-arm-left.png",
        ):
            with self.subTest(relative=relative):
                manifest = json.loads(json.dumps(original))
                manifest["layers"][0]["raster"]["artifact_path"] = relative
                with self.assertRaisesRegex(LayerManifestBundleError, "not canonical"):
                    LayerManifestBundleReader._verify_layers(
                        self.bundle.resolve(), manifest
                    )

        reserved = json.loads(json.dumps(original))
        reserved["layers"][0]["layer_id"] = "NUL"
        reserved["layers"][0]["raster"]["artifact_path"] = "layers/NUL.png"
        with self.assertRaisesRegex(LayerManifestBundleError, "Windows-reserved"):
            LayerManifestBundleReader._verify_layers(self.bundle.resolve(), reserved)

    def test_case_normalized_layer_aliases_are_duplicates(self) -> None:
        manifest = json.loads(
            (self.bundle / "manifest.json").read_text(encoding="utf-8")
        )
        alias = json.loads(json.dumps(manifest["layers"][0]))
        alias["layer_id"] = "LAYER-ARM-LEFT"
        alias["raster"]["artifact_path"] = "layers/LAYER-ARM-LEFT.png"
        manifest["layers"].append(alias)
        with self.assertRaisesRegex(LayerManifestBundleError, "duplicated"):
            LayerManifestBundleReader._verify_layers(self.bundle.resolve(), manifest)

    def test_cropped_raster_geometry_must_match_png_and_canvas(self) -> None:
        original = json.loads(
            (self.bundle / "manifest.json").read_text(encoding="utf-8")
        )
        mutations = (
            ("crop_bbox_xywh", [19, 29, 2, 2], "outside its canvas"),
            ("canvas_offset_xy", [11, 20], "does not match its bbox"),
            ("canvas_size", [21, 30], "differs from manifest"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(original))
                manifest["layers"][0]["raster"][field] = value
                with self.assertRaisesRegex(LayerManifestBundleError, message):
                    LayerManifestBundleReader._verify_layers(
                        self.bundle.resolve(), manifest
                    )

    def test_full_canvas_raster_requires_zero_offset(self) -> None:
        full_asset = self.root / "full.png"
        write_rgba(full_asset, [[(0, 0, 0, 0)] * 20 for _ in range(30)])
        manifest = LayerManifestBuilder().build(
            project_fixture(), {"layer-arm-left": full_asset}
        )
        bundle, _digest = LayerManifestBundleStore(self.root / "full-state").publish(
            "sample-a", manifest, {"layer-arm-left": full_asset}
        )
        manifest["layers"][0]["raster"]["canvas_offset_xy"] = [10, 20]
        with self.assertRaisesRegex(LayerManifestBundleError, "nonzero offset"):
            LayerManifestBundleReader._verify_layers(bundle.resolve(), manifest)


if __name__ == "__main__":
    unittest.main()
