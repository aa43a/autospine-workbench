import copy
import unittest
from autospine_workbench.targets.character43.runtime_visibility_depth import build


class VisibilityDepthTests(unittest.TestCase):
    def inputs(self):
        rows = [dict(time=.5, region='hand', restored=True, prior_frame_max_channel_delta=0,
                     points=[dict(x=1, y=2, kind='ambiguous', hide_deltas={'hand': 0}, support=[
                         dict(slot='hand', rgba=[255,0,0,255]), dict(slot='leg', rgba=[0,255,0,255]),
                         dict(slot='skirt', rgba=[0,0,127,127])])])]
        checks = [dict(arm='hand', body='leg', time=.5, status='uniform_front_proxy')]
        return rows, checks

    def test_opaque_leg_under_transparent_skirt_is_retained(self):
        rows, checks = self.inputs(); out = build(rows, checks)
        point = out['rows'][0]['points'][0]
        self.assertEqual(point['status'], 'opaque_blocker_proxy_conflict')
        self.assertEqual(point['contrary_opaque_slots'], ['leg'])
        self.assertEqual(point['blockers'][-1]['depth_status'], 'missing_evidence')
        self.assertFalse(out['selected'])

    def test_partial_alpha_or_missing_depth_is_not_proven_conflict(self):
        rows, checks = self.inputs(); rows[0]['points'][0]['support'][1]['rgba'][3] = 254
        self.assertEqual(build(rows, checks)['rows'][0]['points'][0]['status'], 'hidden_depth_unresolved')
        rows, _ = self.inputs()
        self.assertEqual(build(rows, [])['rows'][0]['points'][0]['status'], 'hidden_depth_unresolved')

    def test_leg_conflict_buried_under_opaque_skirt_is_not_visible(self):
        rows, checks = self.inputs(); rows[0]['points'][0]['support'][-1]['rgba'][3] = 255
        point = build(rows, checks)['rows'][0]['points'][0]
        self.assertEqual(point['status'], 'hidden_depth_unresolved')
        self.assertEqual(point['contrary_opaque_slots'], ['leg'])
        self.assertEqual(point['nearest_opaque_blocker']['slot'], 'skirt')

    def test_raster_support_disagreement_not_silently_no_overlap(self):
        rows, checks = self.inputs(); checks[0]['status'] = 'no_overlap'
        point = build(rows, checks)['rows'][0]['points'][0]
        self.assertEqual(point['blockers'][0]['depth_status'], 'cpu_gpu_support_disagreement')
        self.assertEqual(point['status'], 'hidden_depth_unresolved')

    def test_visible_target_and_absent_target_distinguished(self):
        rows, checks = self.inputs(); rows[0]['points'][0]['hide_deltas']['hand'] = 2
        self.assertEqual(build(rows, checks)['rows'][0]['points'][0]['status'], 'target_has_visible_contribution')
        rows[0]['points'][0]['support'].pop(0)
        self.assertEqual(build(rows, checks)['rows'][0]['points'][0]['status'], 'target_not_rasterized')

    def test_wrong_frame_and_duplicate_source_fail_closed(self):
        rows, checks = self.inputs()
        with self.assertRaisesRegex(ValueError, 'duplicate'): build(rows, checks+copy.deepcopy(checks))
        rows[0]['restored'] = False
        with self.assertRaisesRegex(ValueError, 'unverified'): build(rows, checks)
