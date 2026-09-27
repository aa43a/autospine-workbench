from copy import deepcopy
import unittest
from unittest.mock import patch
import test_motion_related_pose as fixtures
from autospine_workbench.targets.character43 import source_view_tradeoffs as views
from autospine_workbench.targets.character43.oblique_target import prepare
from autospine_workbench.targets.character43.motion_clip import clip_motion
from autospine_workbench.automation.storage_io import canonical_bytes


class SourceViewTradeoffsTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RelatedPoseTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def build(self):
        return views.build(self.f.files, 'candidate', self.f.bundle, self.f.request)

    def test_exact_clip_keeps_times_and_identity_without_selecting_camera(self):
        before = deepcopy(self.f.files); report = self.build()
        self.assertEqual(report['times'], [0, .5])
        self.assertEqual(report['source_times'], [.5, 1])
        self.assertEqual(report['motion_identity'], self.f.request['motion_identity'])
        self.assertEqual(report['current_yaw'], 30)
        self.assertEqual(len(report['candidates']), 13)
        self.assertFalse(report['selected']); self.assertFalse(report['production_authorized'])
        self.assertEqual(self.f.files, before)
        for row in report['candidates']:
            self.assertEqual(row['knees']['sample_count'], 4)
            worst = row['knees']['worst']
            if worst:
                self.assertEqual(worst['source_time'], worst['time'] + .5)

    def test_changed_source_or_motion_cannot_be_compared(self):
        self.f.request['character_sha256'] = 'different'
        with self.assertRaisesRegex(ValueError, 'source_identity_mismatch'): self.build()

    def test_torso_missing_evidence_is_not_passing_view(self):
        with patch.object(views, 'reference_shapes', side_effect=ValueError('torso_initial_view_degenerate')):
            report = self.build()
        self.assertTrue(all(row['torso']['status'] == 'unmeasured' and row['torso']['source_supported'] is None
                            for row in report['candidates']))

    def test_nonmatching_source_time_rejected(self):
        actual = views.anchors(self.f.bundle, 0)
        with patch.object(views, 'anchors', return_value=(actual[0], [t+1 for t in actual[1]])):
            with self.assertRaisesRegex(ValueError, 'source_times_mismatch'): self.build()

    def test_current_non_grid_view_is_retained_in_addition_to_thirteen_views(self):
        self.f.request['projection']['yaw_degrees'] = 55
        motion, _ = prepare(self.f.bundle, self.f.request['projection'])
        self.f.files['motion-ir.json'] = canonical_bytes(clip_motion(motion, (500000, 1000000)))
        report = self.build()
        self.assertEqual(len(report['candidates']), 14)
        self.assertEqual([r['yaw_degrees'] for r in report['candidates'] if r['current']], [55])
