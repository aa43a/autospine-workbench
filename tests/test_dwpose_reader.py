"""Replay recorded numeric tensors; these fixtures do not simulate model inference."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.runners.pose.base import PoseRunnerRequest
from autospine_workbench.runners.pose.dwpose_profile import PROFILE
from autospine_workbench.runners.pose.dwpose_reader import read_dwpose_raw


@unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("cv2"),
                     "Codec numeric dependencies unavailable")
class DwposeReaderTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from autospine_workbench.runners.pose.dwpose_codec import preprocess_rgba, decode_simcc

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        image = encode_rgba_png(RgbaImage(40, 80, bytes((20, 80, 200, 255)) * 40 * 80))
        self.image_path = self.root / "source.png"
        self.image_path.write_bytes(image)
        self.request = PoseRunnerRequest("test-only", hashlib.sha256(image).hexdigest(), (40, 80), self.image_path)
        _, transform = preprocess_rgba(image)
        x, y = np.zeros((1, 133, 576), dtype=np.float32), np.zeros((1, 133, 768), dtype=np.float32)
        x[:, :, 288] = .75
        y[:, :, 384] = .5
        self.document = {
            "schema": "autospine.dwpose-raw/v1", "authority": "none", "project_id": "test-only",
            "source": {"image_kind": "composite", "image_sha256": self.request.image_sha256,
                       "canvas_size": [40, 80]}, "profile": deepcopy(PROFILE), "transform": transform,
            "decoded": decode_simcc(x, y, transform), "simcc": [x.tolist(), y.tolist()],
            "tensor_sha256": [hashlib.sha256(t.tobytes()).hexdigest() for t in (x, y)],
            "environment": {key: "synthetic-test-only" for key in ("python", "numpy", "opencv", "onnxruntime")},
            "implementation_sha256": {key: "a" * 64 for key in
                                      ("dwpose.py", "dwpose_codec.py", "dwpose_adapter.py", "dwpose_profile.py")},
        }

    def publish(self, document=None):
        document = self.document if document is None else document
        path = self.root / (canonical_sha256(document) + ".json")
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_exact_replay_with_historical_implementation_hashes(self):
        before = deepcopy(self.document)
        result = read_dwpose_raw(self.publish(), self.request)
        self.assertEqual(result, before)
        self.assertEqual(result["decoded"]["keypoints133"][0], [20.0, 40.0])
        self.assertEqual(result["decoded"]["scores133"][0], .5)
        self.assertEqual(result["implementation_sha256"]["dwpose.py"], "a" * 64)

    def test_wrong_canonical_address_rejected(self):
        path = self.root / ("0" * 64 + ".json")
        path.write_text(json.dumps(self.document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "address_mismatch"):
            read_dwpose_raw(path, self.request)

    def test_readdressed_decoded_and_transform_tamper_rejected(self):
        for change, reason in ((lambda d: d["decoded"]["keypoints133"][0].__setitem__(0, 21), "decoded_mismatch"),
                               (lambda d: d["transform"]["center"].__setitem__(0, 21), "transform_mismatch"),
                               (lambda d: d["transform"]["warp_border_rgb"].__setitem__(0, False), "transform_mismatch")):
            document = deepcopy(self.document)
            change(document)
            with self.assertRaisesRegex(ValueError, reason):
                read_dwpose_raw(self.publish(document), self.request)

    def test_readdressed_tensor_tamper_rejected(self):
        self.document["simcc"][0][0][0][288] = .8
        with self.assertRaisesRegex(ValueError, "tensor_hash_mismatch"):
            read_dwpose_raw(self.publish(), self.request)

    def test_shape_and_value_rejected_before_numpy_allocation(self):
        for change in (lambda d: d["simcc"][0][0][0].pop(),
                       lambda d: d["simcc"][0][0][0].__setitem__(0, True),
                       lambda d: d["simcc"][0][0][0].__setitem__(0, 10**1000)):
            document = deepcopy(self.document)
            change(document)
            path = self.publish(document)
            with patch("numpy.array", side_effect=AssertionError("unexpected tensor allocation")):
                with self.assertRaisesRegex(ValueError, "tensor_(shape|value)_invalid"):
                    read_dwpose_raw(path, self.request)

    def test_source_profile_and_authority_mismatch(self):
        for change, reason in ((lambda d: d["source"].update(image_sha256="0" * 64), "source_mismatch"),
                               (lambda d: d["profile"].update(threads=True), "profile_mismatch"),
                               (lambda d: d.update(authority="human"), "document_invalid")):
            document = deepcopy(self.document)
            change(document)
            with self.assertRaisesRegex(ValueError, reason):
                read_dwpose_raw(self.publish(document), self.request)

    def test_changed_real_source_image_rejected(self):
        path = self.publish()
        self.image_path.write_bytes(encode_rgba_png(RgbaImage(40, 80, bytes((0, 0, 0, 255)) * 40 * 80)))
        with self.assertRaises(ValueError):
            read_dwpose_raw(path, self.request)

    def test_invalid_metadata_and_budget_rejected(self):
        self.document["implementation_sha256"]["dwpose.py"] = "unknown"
        with self.assertRaisesRegex(ValueError, "implementation_invalid"):
            read_dwpose_raw(self.publish(), self.request)
        self.document["implementation_sha256"]["dwpose.py"] = "a" * 64
        path = self.publish()
        with patch("autospine_workbench.runners.pose.dwpose_reader.MAX_RAW_BYTES", 10):
            with self.assertRaises(ValueError):
                read_dwpose_raw(path, self.request)


if __name__ == "__main__":
    unittest.main()
