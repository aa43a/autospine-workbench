"""Synthetic PNG alpha evidence only; no real benchmark or holdout images."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from autospine_workbench.benchmark.input_quality import (
    InputQualityError, analyze_input_image, validate_input_quality,
)

try:
    from PIL import Image
except ImportError:
    Image = None


def png(image, **kwargs):
    output = BytesIO()
    image.save(output, format="PNG", **kwargs)
    return output.getvalue()


@unittest.skipUnless(Image, "Pillow optional analysis dependency is unavailable")
class InputQualityTests(unittest.TestCase):
    def healthy_image(self):
        image = Image.new("RGBA", (10, 12), (0, 0, 0, 0))
        image.paste((20, 40, 60, 255), (2, 2, 8, 10))
        return image

    def test_centered_alpha_geometry_is_ok_but_makes_no_human_quality_claim(self):
        raw = png(self.healthy_image())
        result = analyze_input_image(raw)
        self.assertEqual(result["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["canvas"], [10, 12])
        self.assertEqual(result["quality"], "ok")
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["authority"], "none")
        self.assertEqual(result["observability"], "limited_to_alpha_geometry")
        self.assertIn("human_body_cropping_not_assessed", result["limitations"])
        self.assertIn("character_count_not_assessed", result["limitations"])
        self.assertIn("perspective_not_assessed", result["limitations"])
        self.assertNotIn("reviewed_joints", result)
        self.assertEqual(analyze_input_image(raw), result)

    def test_thresholds_are_inclusive_and_low_residual_does_not_expand_bboxes(self):
        image = Image.new("RGBA", (10, 12), (0, 0, 0, 0))
        image.putpixel((0, 0), (1, 2, 3, 1))
        image.paste((1, 2, 3, 8), (1, 1, 9, 11))
        image.paste((1, 2, 3, 32), (3, 3, 7, 9))
        result = analyze_input_image(png(image))
        self.assertEqual(result["alpha"]["bbox_threshold_8"], [1, 1, 9, 11])
        self.assertEqual(result["alpha"]["bbox_threshold_32"], [3, 3, 7, 9])
        self.assertEqual(result["alpha"]["min"], 0)
        self.assertEqual(result["alpha"]["max"], 32)
        self.assertAlmostEqual(result["alpha"]["transparent_pixel_ratio"], 39 / 120)
        self.assertAlmostEqual(result["alpha"]["nonzero_pixel_ratio"], 81 / 120)
        self.assertAlmostEqual(result["bbox_area_ratio"]["threshold_8"], 80 / 120)
        self.assertAlmostEqual(result["bbox_area_ratio"]["threshold_32"], 24 / 120)
        self.assertEqual(result["edge_contacts"], {"threshold_8": [], "threshold_32": []})
        self.assertEqual(result["quality"], "ok")

    def test_only_confirmed_empty_alpha_image_blocks(self):
        for alpha, quality, reason in ((0, "blocked", "empty_alpha_image"),
                                       (1, "warning", "low_alpha_only"),
                                       (7, "warning", "low_alpha_only"),
                                       (8, "warning", "faint_alpha_content"),
                                       (31, "warning", "faint_alpha_content")):
            with self.subTest(alpha=alpha):
                result = analyze_input_image(png(Image.new("RGBA", (10, 12), (1, 2, 3, alpha))))
                self.assertEqual(result["quality"], quality)
                self.assertIn(reason, [row["reason_code"] for row in result["issues"]])

    def test_rgb_without_alpha_warns_without_fabricated_silhouette(self):
        result = analyze_input_image(png(Image.new("RGB", (10, 12), (0, 0, 0))))
        self.assertEqual(result["quality"], "warning")
        self.assertEqual(result["issues"], [{"reason_code": "alpha_channel_missing", "severity": "warning"}])
        self.assertFalse(result["alpha"]["present"])
        self.assertTrue(all(value is None for key, value in result["alpha"].items() if key != "present"))

    def test_png_palette_transparency_is_a_real_alpha_channel(self):
        image = Image.new("P", (10, 12), 0)
        image.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
        image.paste(1, (2, 2, 8, 10))
        result = analyze_input_image(png(image, transparency=0))
        self.assertTrue(result["alpha"]["present"])
        self.assertEqual(result["alpha"]["bbox_threshold_32"], [2, 2, 8, 10])
        self.assertEqual(result["quality"], "ok")

    def test_canvas_edges_landscape_and_occupancy_are_warnings_only(self):
        result = analyze_input_image(png(Image.new("RGBA", (20, 10), (1, 2, 3, 255))))
        self.assertEqual(result["quality"], "warning")
        self.assertEqual(result["edge_contacts"]["threshold_32"], ["left", "top", "right", "bottom"])
        self.assertEqual({row["reason_code"] for row in result["issues"]},
                         {"alpha_content_touches_canvas", "landscape_canvas", "large_alpha_bbox"})
        small = Image.new("RGBA", (10, 12), (0, 0, 0, 0))
        small.putpixel((5, 5), (1, 2, 3, 255))
        result = analyze_input_image(png(small))
        self.assertEqual(result["issues"], [{"reason_code": "small_alpha_bbox", "severity": "warning"}])

    def test_faint_edge_does_not_claim_strong_content_touches(self):
        image = self.healthy_image()
        image.putpixel((0, 3), (1, 2, 3, 8))
        result = analyze_input_image(png(image))
        self.assertEqual(result["edge_contacts"]["threshold_8"], ["left"])
        self.assertEqual(result["edge_contacts"]["threshold_32"], [])
        self.assertEqual(result["issues"], [{"reason_code": "low_alpha_content_touches_canvas", "severity": "warning"}])

    def test_bad_png_and_optional_missing_dependency_are_structured_errors(self):
        for raw in (b"", b"bad png", bytearray(b"png")):
            with self.subTest(raw=raw), self.assertRaises(InputQualityError):
                analyze_input_image(raw)
        import builtins
        real_import = builtins.__import__

        def without_pillow(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("optional dependency absent")
            return real_import(name, *args, **kwargs)

        raw = png(self.healthy_image())
        observed = analyze_input_image(raw)
        with patch("builtins.__import__", without_pillow):
            self.assertEqual(validate_input_quality(observed), observed)
            with self.assertRaises(InputQualityError) as caught:
                analyze_input_image(raw)
        self.assertEqual(caught.exception.reason_code, "input_quality_dependency_unavailable")

    def test_semantic_validator_rejects_nonfinite_boolean_and_inconsistent_geometry(self):
        valid = analyze_input_image(png(self.healthy_image()))
        bad = []
        for value in (True, "0.5", float("nan"), float("inf"), -0.1, 1.1):
            result = deepcopy(valid)
            result["alpha"]["transparent_pixel_ratio"] = value
            bad.append(result)
        for value in (True, float("nan"), 1):
            result = deepcopy(valid)
            result["canvas_aspect_ratio"] = value
            bad.append(result)
        result = deepcopy(valid)
        result["alpha"]["bbox_threshold_32"] = [0, 0, 10, 12]
        bad.append(result)
        result = deepcopy(valid)
        result["alpha"]["bbox_threshold_8"][0] = False
        bad.append(result)
        result = deepcopy(valid)
        result["alpha"]["min"] = 32
        bad.append(result)
        result = deepcopy(valid)
        result["quality"] = "blocked"
        bad.append(result)
        result = deepcopy(valid)
        result["edge_contacts"]["threshold_32"] = ["left"]
        bad.append(result)
        for result in bad:
            with self.assertRaises(InputQualityError):
                validate_input_quality(result)

    def test_schema_and_validator_reject_wrong_shapes_and_unsupported_claims(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema unavailable")
        schema = json.loads((ROOT / "schemas/benchmark-input-quality-v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        document = analyze_input_image(png(self.healthy_image()))
        validator.validate(document)
        for image in (Image.new("RGB", (10, 12)), Image.new("RGBA", (10, 12)),
                      Image.new("RGBA", (20, 10), (1, 2, 3, 255))):
            validator.validate(analyze_input_image(png(image)))
        for mutation in ({"authority": "approved"}, {"observability": "full_body_pose"},
                         {"limitations": []}, {"canvas": [True, 12]}, {"quality": "blocked"}):
            invalid = {**document, **mutation}
            self.assertTrue(list(validator.iter_errors(invalid)))
            with self.assertRaises(InputQualityError):
                validate_input_quality(invalid)


if __name__ == "__main__":
    unittest.main()
