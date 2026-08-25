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


def project_fixture() -> dict:
    layer = {
        "id": "layer-arm-left",
        "source_index": 1,
        "name": "arm-left",
        "canonical_role": "body.hand",
        "side": "left",
        "disposition": "keep",
        "visible": True,
        "empty": False,
        "opacity": 1.0,
        "blend_mode": "normal",
        "z_index": 3,
        "bbox": {"x": 10, "y": 20, "width": 2, "height": 2},
        "pivot_xy": [10.5, 20.5],
        "review_state": "manual_adjusted",
        "metrics": {"alpha_nonzero": 4, "component_count": 1},
    }
    return {
        "id": "sample-a",
        "source": {"sha256": "a" * 64, "audit_sha256": "b" * 64},
        "canvas": {"width": 20, "height": 30},
        "layers": [layer],
        "resolved": {
            "revision": 2,
            "canvas": {"width": 20, "height": 30},
            "layers": [layer],
        },
    }


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


if __name__ == "__main__":
    unittest.main()
