from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = REPOSITORY_ROOT / "tmp" / "psd_audit" / "results"
WORKBENCH_SRC = Path(__file__).resolve().parents[1] / "src"
if str(WORKBENCH_SRC) not in sys.path:
    sys.path.insert(0, str(WORKBENCH_SRC))

from autospine_workbench.composite_quality import compare_composite_pngs  # noqa: E402
from autospine_workbench.project_store import ProjectStore  # noqa: E402


def load_audit(relative_path: str) -> dict:
    path = AUDIT_ROOT / relative_path / "audit.json"
    if not path.is_file():
        raise unittest.SkipTest(f"actual audit is not present: {path}")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


class ActualSeeThroughAuditRegressionTests(unittest.TestCase):
    def test_1024_sample_distinguishes_rgba_representation_from_visual_error(self) -> None:
        audit = load_audit("seethrough_output")
        self.assertEqual(
            audit["sha256"],
            "4427ec70014a81c3ca398697dcd9d289cb8dba16a789afe9ceefbd34ede924bf",
        )
        self.assertEqual(audit["canvas"], [1024, 1024])
        self.assertEqual(audit["pixel_layers"], 23)
        self.assertEqual(audit["empty_pixel_layers"], 0)
        self.assertGreater(audit["composite_vs_embedded_mae_rgba"], 100)
        self.assertEqual(audit["composite_vs_embedded_max_abs"], 255)
        audit_dir = AUDIT_ROOT / "seethrough_output"
        metrics = compare_composite_pngs(
            audit_dir / "composite.png", audit_dir / "embedded_composite.png"
        )
        self.assertEqual("flattened_reference", metrics.alpha_representation)
        self.assertLess(metrics.background_matched_rgb_mae, 5)
        self.assertEqual("passed", metrics.status)
        with tempfile.TemporaryDirectory() as state_root:
            store = ProjectStore(REPOSITORY_ROOT, state_root=Path(state_root))
            project = store.get_project("seethrough_output")
            audit_warnings = project["workflow"]["audit_warnings"]
            self.assertTrue(audit_warnings["raw_composite_difference"])
            self.assertFalse(audit_warnings["high_composite_error"])
            warning_codes = {
                warning["code"]
                for warning in store.validate_project("seethrough_output")["warnings"]
            }
            self.assertNotIn("composite_mismatch", warning_codes)

        names = [layer["name"] for layer in audit["layers"]]
        self.assertIn("handwear-l", names)
        self.assertIn("handwear-r", names)
        self.assertEqual(names.count("legwear"), 1)
        self.assertEqual(names.count("footwear"), 1)

    def test_1200x1800_sample_keeps_manual_mapping_findings_visible(self) -> None:
        audit = load_audit("seethrough_output_5")
        self.assertEqual(
            audit["sha256"],
            "26a67ea971bf27473285e8bb5fce22ca4f26bce658aac99eeead43a782760803",
        )
        self.assertEqual(audit["canvas"], [1200, 1800])
        self.assertEqual(audit["channels"], 5)
        self.assertEqual(audit["pixel_layers"], 20)
        self.assertEqual(audit["visible_pixel_layers"], 19)
        self.assertEqual(audit["empty_pixel_layers"], 1)
        self.assertLess(audit["composite_vs_embedded_mae_rgba"], 1)

        layers = {layer["name"]: layer for layer in audit["layers"]}
        self.assertTrue(layers["handwear"]["empty"])
        self.assertFalse(layers["handwear"]["visible"])
        self.assertIn("hand-r", layers)
        self.assertIn("hand-l", layers)
        self.assertIn("head-obj", layers)
        self.assertNotIn("legwear", layers)
        for bilateral_name in ("eyebrow", "ears", "eyelash", "eyewhite", "irides"):
            with self.subTest(layer=bilateral_name):
                self.assertGreaterEqual(layers[bilateral_name]["component_count"], 2)


if __name__ == "__main__":
    unittest.main()
