"""Model-independent numeric tests for the fixed whole-canvas DWPose codec."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.runners.pose.dwpose_codec import MEAN, STD, preprocess_rgba, decode_simcc


def png(width=80, height=160, pixel=(10, 40, 200, 255)):
    return encode_rgba_png(RgbaImage(width, height, bytes(pixel) * width * height))


@unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("cv2"), "Codec numeric dependencies unavailable")
class DwposeCodecTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def outputs(self):
        x = self.np.zeros((1, 133, 576), dtype=self.np.float32)
        y = self.np.zeros((1, 133, 768), dtype=self.np.float32)
        x[:, :, 288] = .8; y[:, :, 384] = .6
        return x, y

    def test_preprocessing_shape_bgr_white_alpha_and_black_padding(self):
        np = self.np
        tensor, transform = preprocess_rgba(png())
        self.assertEqual(tensor.shape, (1, 3, 384, 288))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertTrue(tensor.flags.c_contiguous)
        self.assertEqual(transform["color_order"], "BGR")
        np.testing.assert_allclose(tensor[0, :, 192, 144], (np.array([200, 40, 10])-MEAN)/STD, atol=1e-6)
        transparent, _ = preprocess_rgba(png(pixel=(10, 40, 200, 0)))
        np.testing.assert_allclose(transparent[0, :, 192, 144], (np.array([255]*3)-MEAN)/STD, atol=1e-6)
        np.testing.assert_allclose(transparent[0, :, 0, 0], -np.array(MEAN)/STD, atol=1e-6)

    def test_non_square_canvas_inverse_matches_simcc_postprocessing(self):
        np = self.np
        for width, height in ((80, 160), (200, 80)):
            _, transform = preprocess_rgba(png(width, height))
            x, y = self.outputs(); result = decode_simcc(x, y, transform)
            np.testing.assert_allclose(result["keypoints133"][0], [width/2, height/2], atol=1e-6)
            matrix = np.vstack((transform["affine"], [0, 0, 1]))
            inverse = np.vstack((transform["inverse_affine"], [0, 0, 1]))
            np.testing.assert_allclose(matrix @ inverse, np.eye(3), atol=1e-10)
            x[0, 0] = 0; y[0, 0] = 0; x[0, 0, 70] = 1; y[0, 0, 200] = .9
            result = decode_simcc(x, y, transform)
            np.testing.assert_allclose(result["keypoints133"][0], (inverse @ [35, 100, 1])[:2], atol=1e-6)

    def test_raw_score_minimum_invalid_sentinel_and_out_of_canvas_are_preserved(self):
        _, transform = preprocess_rgba(png()); x, y = self.outputs()
        x[0, 0] = -2; y[0, 0] = -3
        x[0, 1, 0] = 2.4; y[0, 1, 0] = 1.9
        result = decode_simcc(x, y, transform)
        self.assertEqual(result["scores133"][0], -3)
        self.assertFalse(result["valid133"][0])
        self.assertLess(result["keypoints133"][0][0], 0)
        self.assertAlmostEqual(result["scores133"][1], 1.9, places=6)
        self.assertLess(result["keypoints133"][1][1], 0)
        self.assertAlmostEqual(result["scores133"][2], .6, places=6)

    def test_wrong_shapes_nonfinite_dtypes_and_changed_transform_fail(self):
        _, transform = preprocess_rgba(png()); x, y = self.outputs()
        for bad in (x[:, :132], x.astype(bool), x.tolist(), x.astype(self.np.int32)):
            with self.assertRaisesRegex(ValueError, "simcc_invalid"): decode_simcc(bad, y, transform)
        for number in (float("nan"), float("inf")):
            bad = x.copy(); bad[0, 0, 0] = number
            with self.assertRaisesRegex(ValueError, "simcc_invalid"): decode_simcc(bad, y, transform)
        changed = deepcopy(transform); changed["center"][0] += 1
        with self.assertRaisesRegex(ValueError, "transform_invalid"): decode_simcc(x, y, changed)

    def test_malformed_image_rejected(self):
        with self.assertRaisesRegex(ValueError, "png_invalid"): preprocess_rgba(b"not PNG")


if __name__ == "__main__": unittest.main()
