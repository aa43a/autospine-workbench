"""Opt-in real ONNX evidence; no stub or downloadable dependency in default tests."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.png_rgba import decode_rgba_png
from autospine_workbench.runners.pose.base import PoseRunnerRequest
from autospine_workbench.runners.pose.dwpose import DWPoseOnnxRunner
from autospine_workbench.runners.pose.dwpose_reader import read_dwpose_raw


@unittest.skipUnless(os.environ.get('AUTOSPINE_DWPOSE_MODEL') and os.environ.get('AUTOSPINE_DWPOSE_IMAGE'),
                     'Real ONNX model and image are opt-in external inputs')
class ActualDwposeTests(unittest.TestCase):
    def test_real_inference_repeatability_raw_replay_and_unknown_visibility(self):
        image_path = Path(os.environ['AUTOSPINE_DWPOSE_IMAGE'])
        raw = image_path.read_bytes(); image = decode_rgba_png(raw)
        request = PoseRunnerRequest('real-dwpose-test', hashlib.sha256(raw).hexdigest(),
                                   (image.width, image.height), image_path)
        with tempfile.TemporaryDirectory() as tmp:
            runner = DWPoseOnnxRunner(Path(os.environ['AUTOSPINE_DWPOSE_MODEL']), Path(tmp))
            first = runner.produce(request)
            second = runner.produce(request)
            self.assertEqual(first, second)
            pose = json.loads(first.read_text())
            self.assertEqual(len(pose['joints']), 12)
            self.assertTrue(all(row['visibility'] == 'unknown' for row in pose['joints'].values()))
            raws = list((Path(tmp)/'analysis'/'real-dwpose-test'/'dwpose-raw').glob('*.json'))
            self.assertEqual(len(raws), 1)
            observation = read_dwpose_raw(raws[0], request)
            self.assertEqual(len(observation['decoded']['keypoints133']), 133)
            self.assertEqual(image_path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
