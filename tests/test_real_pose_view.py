"""Synthetic view fixtures test rendering and identity, not model accuracy."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.optimizer import optimize_joints
from autospine_workbench.benchmark.real_pose_view import render_real_pose
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_joint_optimizer import fixture


def inputs():
    candidate, pose, match = fixture()
    raw = encode_rgba_png(RgbaImage(100, 100, bytes([0, 0, 0, 0])*10000))
    digest = hashlib.sha256(raw).hexdigest()
    candidate['composite_sha256'] = digest
    pose = replace(pose, image_sha256=digest)
    match['candidate_sha256'] = canonical_sha256(candidate)
    return candidate, pose, optimize_joints(candidate, pose, match), raw


class RealPoseViewTests(unittest.TestCase):
    def test_two_panels_scores_readonly_and_pure(self):
        args = inputs()
        before = deepcopy(args)
        page = render_real_pose(*args)
        self.assertEqual(args, before)
        self.assertEqual(page.count('<svg '), 2)
        self.assertEqual(page.count('<circle '), 24)
        self.assertIn('0.9000', page)
        self.assertIn('尚无人工标注，不能计算关节误差', page)
        self.assertIn("script-src 'none'", page)
        for forbidden in ('<script', '<button', 'download=', 'fetch('):
            self.assertNotIn(forbidden, page)

    def test_blocked_has_no_fake_optimized_points(self):
        candidate, pose, doc, raw = inputs()
        doc.update(status='blocked', joints=[], reason_codes=['complete_limb_pose_required'])
        page = render_real_pose(candidate, pose, doc, raw)
        self.assertEqual(page.count('<circle '), 12)
        self.assertIn('优化被阻塞', page)

    def test_xss_escaped(self):
        candidate, pose, doc, raw = inputs()
        payload = '</p><script>alert(1)</script>'
        pose = replace(pose, detector_id=payload)
        doc['reason_codes'] = [payload]
        page = render_real_pose(candidate, pose, doc, raw)
        self.assertNotIn(payload, page)
        self.assertIn('&lt;script&gt;', page)

    def test_source_binding_image_tamper_and_out_of_bounds(self):
        candidate, pose, doc, raw = inputs()
        with self.assertRaises(ValueError):
            render_real_pose(candidate, pose, doc, raw+b'changed')
        bad = deepcopy(doc)
        bad['pose_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            render_real_pose(candidate, pose, bad, raw)
        bad = deepcopy(doc)
        bad['joints'][0]['position'] = [10**1000, 0]
        with self.assertRaisesRegex(ValueError, 'input_invalid'):
            render_real_pose(candidate, pose, bad, raw)
        with self.assertRaises(ValueError):
            render_real_pose(candidate, replace(pose, project_id='wrong'), doc, raw)


if __name__ == '__main__':
    unittest.main()
