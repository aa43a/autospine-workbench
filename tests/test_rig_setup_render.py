"""Pixel-exact setup reconstruction for region-only RigIR."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.rig_setup_render import (  # noqa: E402
    RigSetupRenderError,
    compare_region_setup,
)
from tests.png_helpers import write_rgba  # noqa: E402


def layer(layer_id: str, path: str, order: int, offset: list[int], opacity: float) -> dict:
    return {
        "layer_id": layer_id,
        "source": {"visible": True, "opacity": opacity, "blend_mode": "normal"},
        "raster": {"artifact_path": path, "canvas_offset_xy": offset},
        "rig_hint": {"attachment_kind": "region", "setup_draw_order": order},
    }


def attachment(layer_id: str, path: str, offset: list[int], size: list[int]) -> dict:
    return {
        "id": f"attachment.{layer_id}",
        "slot": f"slot.{layer_id}",
        "type": "region",
        "image_path": path,
        "canvas_offset_xy": offset,
        "size": size,
    }


class RegionSetupRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "layers").mkdir()
        write_rgba(
            self.root / "layers" / "bottom.png",
            [[(255, 0, 0, 255), (255, 0, 0, 255)]],
        )
        write_rgba(self.root / "layers" / "top.png", [[(0, 0, 255, 128)]])
        self.manifest = {
            "source": {"canvas": [3, 2]},
            "layers": [
                layer("top", "layers/top.png", 8, [1, 0], 0.5),
                layer("bottom", "layers/bottom.png", 2, [0, 0], 1.0),
            ],
        }
        self.rig = {
            "canvas": {"width": 3, "height": 2},
            "slots": [
                {
                    "id": "slot.top",
                    "setup_attachment": "attachment.top",
                    "setup_draw_order": 8,
                    "blend": "normal",
                    "color_rgba": "ffffff80",
                },
                {
                    "id": "slot.bottom",
                    "setup_attachment": "attachment.bottom",
                    "setup_draw_order": 2,
                    "blend": "normal",
                    "color_rgba": "ffffffff",
                },
            ],
            "attachments": [
                attachment("top", "layers/top.png", [1, 0], [1, 1]),
                attachment("bottom", "layers/bottom.png", [0, 0], [2, 1]),
            ],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_manifest_and_region_rig_reconstruct_pixel_exact_setup(self) -> None:
        result = compare_region_setup(self.manifest, self.rig, self.root)
        self.assertTrue(result.exact)
        self.assertEqual(0, result.differing_pixels)
        self.assertEqual(result.manifest_rgba_sha256, result.rig_rgba_sha256)

    def test_offset_or_draw_order_regression_changes_pixels(self) -> None:
        changed = deepcopy(self.rig)
        changed["attachments"][0]["canvas_offset_xy"] = [2, 0]
        self.assertFalse(compare_region_setup(self.manifest, changed, self.root).exact)
        changed = deepcopy(self.rig)
        changed["slots"][0]["setup_draw_order"] = 1
        self.assertFalse(compare_region_setup(self.manifest, changed, self.root).exact)

    def test_unsupported_blend_and_size_mismatch_fail_loudly(self) -> None:
        changed = deepcopy(self.rig)
        changed["slots"][0]["blend"] = "multiply"
        with self.assertRaisesRegex(RigSetupRenderError, "normal blend"):
            compare_region_setup(self.manifest, changed, self.root)
        changed = deepcopy(self.rig)
        changed["attachments"][0]["size"] = [2, 1]
        with self.assertRaisesRegex(RigSetupRenderError, "size"):
            compare_region_setup(self.manifest, changed, self.root)


if __name__ == "__main__":
    unittest.main()
