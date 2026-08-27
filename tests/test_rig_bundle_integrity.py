"""Regression tests for full on-disk RigIR bundle verification."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import main as cli_main  # noqa: E402
from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBuilder,
    LayerManifestBundleStore,
)
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    encode_rgba_png,
    read_rgba_png,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_bundle import RigBundleError  # noqa: E402
from autospine_workbench.rig_setup_artifact import (  # noqa: E402
    RigSetupArtifactError,
    encoder_identity,
    renderer_identity,
    verify_setup_artifact,
)
from autospine_workbench.rig_setup_render import render_rig_setup  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402
from tests.resolved_snapshot_helpers import (  # noqa: E402
    resolved_project_envelope,
)
from tests.test_layer_manifest import project_fixture, write_png  # noqa: E402
from tests.test_rig_bundle import BundleFixture  # noqa: E402


SMALL_SETUP_GOLDEN = {
    "png": "7b757d1046586dcc45076e3111a2a8c51768bc878c8394d59b0ade1121a55891",
    "rgba": "d1cb491ab2cd678d7934a871a2edd94c674c03994c6d2f55ab891061c70f2938",
}


class RigBundleIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _fixture(self, name: str, **kwargs) -> BundleFixture:
        root = self.root / name
        root.mkdir()
        return BundleFixture(root, **kwargs)

    def _approve(self, bundle: Path, rig_sha: str) -> Path:
        golden = self.root / f"golden-{len(list(self.root.glob('golden-*')))}"
        golden.mkdir()
        setup = json.loads(
            (bundle / "setup-render.json").read_text(encoding="utf-8")
        )
        png = (bundle / "setup.png").read_bytes()
        image = read_rgba_png(bundle / "setup.png")
        image_path = golden / "approved.png"
        image_path.write_bytes(png)
        contract = {
            "format": "autospine-setup-golden",
            "format_version": 1,
            "project_id": setup["project_id"],
            "source": {
                "rig_sha256": rig_sha,
                "bundle_sha256": bundle.name,
                "setup_render_sha256": canonical_sha256(setup),
            },
            "renderer": renderer_identity(),
            "encoder": encoder_identity(),
            "image": {
                "path": image_path.name,
                "width": image.width,
                "height": image.height,
                "rgba_sha256": hashlib.sha256(image.pixels).hexdigest(),
                "png_sha256": hashlib.sha256(png).hexdigest(),
            },
        }
        contract_path = golden / "approved.json"
        contract_path.write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return contract_path

    def _assert_invalid_bundle(self, bundle: Path, contract: Path) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli_main(["verify-setup-golden", str(bundle), str(contract)])
        report = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(("error", "invalid_bundle"), (report["status"], report["code"]))

    def test_same_pixels_with_different_png_bytes_are_rejected(self) -> None:
        fixture = self._fixture("same-pixels")
        bundle, rig_sha = fixture.publish()
        contract = self._approve(bundle, rig_sha)
        region = bundle / "layers" / "layer-001-arm-l.png"
        before = region.read_bytes()
        image = read_rgba_png(region)
        replacement = encode_rgba_png(RgbaImage(image.width, image.height, image.pixels))
        self.assertNotEqual(before, replacement)
        region.write_bytes(replacement)
        self.assertEqual(image.pixels, read_rgba_png(region).pixels)
        self._assert_invalid_bundle(bundle, contract)

    def test_small_setup_has_a_checked_in_golden_identity(self) -> None:
        fixture = self._fixture("checked-in-golden")
        bundle, _rig_sha = fixture.publish()
        setup = json.loads(
            (bundle / "setup-render.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            SMALL_SETUP_GOLDEN,
            {
                "png": setup["image"]["png_sha256"],
                "rgba": setup["image"]["rgba_sha256"],
            },
        )

    def test_alpha_zero_rgb_tampering_is_rejected_even_when_setup_is_unchanged(self) -> None:
        def transparent_corner(path: Path) -> None:
            rows = [
                [
                    (11, 22, 33, 0) if (x, y) == (0, 0) else (80, 120, 160, 255)
                    for x in range(30)
                ]
                for y in range(40)
            ]
            write_rgba(path, rows)

        fixture = self._fixture("alpha-zero", asset_writer=transparent_corner)
        bundle, rig_sha = fixture.publish()
        contract = self._approve(bundle, rig_sha)
        rig = json.loads((bundle / "rig.json").read_text(encoding="utf-8"))
        before = render_rig_setup(rig, bundle)
        region = bundle / "layers" / "layer-001-arm-l.png"
        image = read_rgba_png(region)
        pixels = bytearray(image.pixels)
        self.assertEqual(0, pixels[3])
        pixels[:3] = b"\xfe\xfd\xfc"
        region.write_bytes(encode_rgba_png(RgbaImage(image.width, image.height, bytes(pixels))))
        self.assertEqual(before, render_rig_setup(rig, bundle))
        self._assert_invalid_bundle(bundle, contract)

    def test_fully_occluded_region_tampering_is_rejected(self) -> None:
        fixture = self._fixture("occluded")
        bundle, rig_sha = self._publish_two_layer_bundle(fixture)
        contract = self._approve(bundle, rig_sha)
        rig = json.loads((bundle / "rig.json").read_text(encoding="utf-8"))
        before = render_rig_setup(rig, bundle)
        back = bundle / "layers" / "layer-001-arm-l.png"
        image = read_rgba_png(back)
        pixels = bytearray(image.pixels)
        pixels[0] ^= 0x7F
        back.write_bytes(encode_rgba_png(RgbaImage(image.width, image.height, bytes(pixels))))
        self.assertEqual(before, render_rig_setup(rig, bundle))
        self._assert_invalid_bundle(bundle, contract)

    def test_staging_is_fully_verified_before_rename(self) -> None:
        fixture = self._fixture("staging")
        from autospine_workbench import rig_bundle as module

        original = module._copy_png

        def recode_after_copy(source: Path, target: Path, digest: str) -> None:
            original(source, target, digest)
            image = read_rgba_png(target)
            target.write_bytes(
                encode_rgba_png(RgbaImage(image.width, image.height, image.pixels))
            )

        with patch.object(module, "_copy_png", side_effect=recode_after_copy):
            with self.assertRaisesRegex(RigBundleError, "hash mismatch"):
                fixture.publish()
        rig_parent = (
            fixture.state
            / "builds"
            / "sample-a"
            / "rig-ir"
            / canonical_sha256(fixture.rig)
        )
        self.assertEqual([], list(rig_parent.iterdir()))

    def test_unknown_setup_renderer_version_fails_closed(self) -> None:
        fixture = self._fixture("renderer-version")
        bundle, rig_sha = fixture.publish()
        setup = json.loads(
            (bundle / "setup-render.json").read_text(encoding="utf-8")
        )
        setup["renderer"]["version"] = "9.0.0"
        rig = json.loads((bundle / "rig.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(RigSetupArtifactError, "unsupported"):
            verify_setup_artifact(
                setup,
                (bundle / "setup.png").read_bytes(),
                project_id="sample-a",
                rig=rig,
                rig_sha256=rig_sha,
                bundle_path=bundle,
            )

    def test_bundle_json_and_setup_png_reads_are_bounded(self) -> None:
        fixture = self._fixture("bounded-reads")
        bundle, rig_sha = fixture.publish()
        contract = self._approve(bundle, rig_sha)
        with patch(
            "autospine_workbench.rig_bundle_integrity.MAX_RIG_JSON_BYTES", 32
        ):
            self._assert_invalid_bundle(bundle, contract)
        setup_size = (bundle / "setup.png").stat().st_size
        with patch(
            "autospine_workbench.rig_bundle_integrity.MAX_RIG_PNG_BYTES",
            setup_size - 1,
        ):
            self._assert_invalid_bundle(bundle, contract)

    def _publish_two_layer_bundle(self, fixture: BundleFixture) -> tuple[Path, str]:
        project = project_fixture()
        cover_layer = deepcopy(project["resolved"]["layers"][0])
        cover_layer.update(
            {
                "id": "layer-002-cover",
                "source_index": 2,
                "name": "cover",
                "z_index": 1,
                "image_url": (
                    "/api/projects/sample-a/layers/layer-002-cover/image"
                ),
            }
        )
        project["resolved"]["layers"].append(cover_layer)
        project = resolved_project_envelope(project["resolved"])
        back, cover = fixture.root / "back.png", fixture.root / "cover.png"
        write_png(back, 30, 40)
        write_png(cover, 30, 40)
        assets = {"layer-001-arm-l": back, "layer-002-cover": cover}
        manifest = LayerManifestBuilder().build(project, assets)
        layer_bundle, layer_sha = LayerManifestBundleStore(fixture.state).publish(
            "sample-a", manifest, assets
        )
        run = deepcopy(fixture.run)
        run["inputs"]["layer_manifest_sha256"] = layer_sha
        rig = deepcopy(fixture.rig)
        rig["source"]["layer_manifest_sha256"] = layer_sha
        rig["source"]["run_manifest_sha256"] = canonical_sha256(run)
        first, second = manifest["layers"]
        rig["attachments"][0].update(
            image_path=first["raster"]["artifact_path"],
            image_sha256=first["raster"]["sha256"],
            source_layer_ids=[first["layer_id"]],
        )
        rig["slots"].append(
            {"id": "cover-slot", "bone": "root", "setup_attachment": "cover-region",
             "setup_draw_order": 1, "blend": "normal", "color_rgba": "ffffffff"}
        )
        rig["attachments"].append(
            {"id": "cover-region", "slot": "cover-slot", "type": "region",
             "image_path": second["raster"]["artifact_path"],
             "image_sha256": second["raster"]["sha256"],
             "source_layer_ids": [second["layer_id"]],
             "canvas_offset_xy": second["raster"]["canvas_offset_xy"],
             "pivot_xy": [20, 25], "size": [30, 40]}
        )
        rig["skins"]["default"]["cover-slot"] = ["cover-region"]
        probes = deepcopy(fixture.probes)
        probes["source"]["layer_manifest_sha256"] = layer_sha
        probes["source"]["rig_sha256"] = canonical_sha256(rig)
        return fixture.store.publish("sample-a", rig, run, probes, layer_bundle)


if __name__ == "__main__":
    unittest.main()
