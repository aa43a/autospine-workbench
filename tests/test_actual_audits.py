from __future__ import annotations

import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = REPOSITORY_ROOT / "tmp" / "psd_audit" / "results"


def load_audit(relative_path: str) -> dict:
    path = AUDIT_ROOT / relative_path / "audit.json"
    if not path.is_file():
        raise unittest.SkipTest(f"actual audit is not present: {path}")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


class ActualSeeThroughAuditRegressionTests(unittest.TestCase):
    def test_1024_sample_keeps_the_composite_blocker_visible(self) -> None:
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
