"""Raw-score encoding and fail-closed adapter behavior, without model inference."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.runners.pose.dwpose_adapter import to_coco17
from autospine_workbench.runners.pose.dwpose_profile import PROFILE
from autospine_workbench.coco17_adapter import adapt_coco17_detections
from autospine_workbench.coco17_detections import load_coco17_detections


def raw_fixture():
    return {'schema': 'autospine.dwpose-raw/v1', 'authority': 'none', 'profile': deepcopy(PROFILE),
            'project_id': 'test', 'source': {'image_kind': 'composite', 'image_sha256': 'a'*64, 'canvas_size': [100, 200]},
            'environment': {'onnxruntime': 'test-only'},
            'decoded': {'keypoints133': [[10., 20.] for _ in range(133)], 'scores133': [1.02843]*133}}


class DwposeAdapterTests(unittest.TestCase):
    def test_unbounded_native_score_is_preserved_and_explicitly_encoded(self):
        raw = raw_fixture(); before = deepcopy(raw)
        coco = to_coco17(raw)
        self.assertEqual(raw, before)
        self.assertAlmostEqual(coco['detections'][0]['keypoint_scores'][0], 1.02843 / 2.02843)
        self.assertEqual(coco['detections'][0]['visibility'], ['unknown']*17)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'coco.json'; path.write_text(json.dumps(coco), encoding='utf-8')
            detections = load_coco17_detections(path, expected_project_id='test',
                                              expected_image_sha256='a'*64, expected_canvas_size=(100, 200))
            pose = adapt_coco17_detections(detections, selected_index=0, selection_method='single',
                                          side_mapping='as_reported', view_orientation='unknown', mirror_state='unknown')
            self.assertEqual(len(pose['joints']), 12)
            self.assertEqual(pose['joints']['knee.left']['visibility'], 'unknown')

    def test_invalid_body_point_fails_without_clipping(self):
        for value in (-.1, 100):
            raw = raw_fixture(); raw['decoded']['keypoints133'][5][0] = value
            with self.assertRaisesRegex(ValueError, 'unrepresentable'):
                to_coco17(raw)
        raw = raw_fixture(); raw['decoded']['scores133'][5] = 0
        with self.assertRaisesRegex(ValueError, 'unrepresentable'):
            to_coco17(raw)

    def test_non_body_outside_canvas_is_retained_but_not_promoted(self):
        raw = raw_fixture(); raw['decoded']['keypoints133'][100] = [-20, 300]
        self.assertEqual(len(to_coco17(raw)['detections'][0]['keypoints']), 17)
        self.assertEqual(raw['decoded']['keypoints133'][100], [-20, 300])

    def test_source_or_raw_change_changes_adapter_identity(self):
        raw = raw_fixture(); first = to_coco17(raw)['detector']['config_sha256']
        raw['decoded']['scores133'][100] = .9
        self.assertNotEqual(first, to_coco17(raw)['detector']['config_sha256'])
        raw['decoded']['scores133'][0] = float('nan')
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            to_coco17(raw)


if __name__ == '__main__':
    unittest.main()
