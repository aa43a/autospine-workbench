from copy import deepcopy
import unittest
from unittest.mock import patch

from autospine_workbench.motion2d.contact_candidate import infer
from autospine_workbench.motion2d.stationary_support import inspect
from autospine_workbench.targets.character43.stationary_contact_policy import select
from test_motion_contact_candidate import fixture
from test_motion_contacts import fixture as target


class SourceStationarityTests(unittest.TestCase):
    def test_slow_gliding_is_not_stationary_despite_low_speed_contact(self):
        for speed, eligible in [(0, True), (.002, False)]:
            bvh, mapping = fixture(speed)
            hypothesis = infer(bvh, mapping)
            self.assertEqual(len(hypothesis['markers']), 2)
            self.assertEqual(inspect(bvh, mapping, hypothesis)['eligible'], eligible)

    def test_identity_and_partial_windows_fail_closed(self):
        bvh, mapping = fixture()
        hypothesis = infer(bvh, mapping)
        bad = deepcopy(hypothesis); bad['source_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            inspect(bvh, mapping, bad)
        hypothesis['markers'][0]['start_tick'] = 1
        self.assertFalse(inspect(bvh, mapping, hypothesis)['eligible'])


class SelectionTests(unittest.TestCase):
    def test_disabled_or_clipped_does_not_attempt_correction(self):
        doc, motion = target()
        report = dict(status='inferred_proxy_drift', selected=False)
        with patch('autospine_workbench.targets.character43.stationary_contact_policy.build') as build:
            for options in ({'enabled': False}, {'clip_bounds': (0, 1)}):
                result, _ = select(doc, 'walk', motion, [0, 1], 100, report, None, None, **options)
                self.assertIs(result, doc)
            build.assert_not_called()

    def test_legacy_profile_identity_is_preserved(self):
        from autospine_workbench.targets.character43.stationary_contact_policy import LEGACY_PROFILE
        doc, motion = target()
        _, report = select(doc, 'walk', motion, [0, 1], 100,
                           dict(status='inferred_proxy_drift'), None, None, enabled=False, profile=LEGACY_PROFILE)
        self.assertEqual(report['policy_id'], LEGACY_PROFILE)

    def test_geometry_failure_reverts_to_original_and_retains_attempt(self):
        doc, motion = target()
        report = dict(status='inferred_proxy_drift', selected=False,
                      hypothesis=dict(markers=motion['markers'], ticks_per_second=1000000))
        candidate = deepcopy(doc)
        candidate['animations']['walk']['bones']['root']['translate'][-1]['x'] = 0
        attempt = dict(after=dict(intervals=[dict(samples=[dict(time=0), dict(time=1)])]))
        module = 'autospine_workbench.targets.character43.stationary_contact_policy.'
        with patch(module+'inspect_source', return_value={'eligible': True}), \
             patch(module+'build', return_value=(candidate, attempt)), \
             patch(module+'inspect', return_value={'passed': False}):
            kept, result = select(doc, 'walk', motion, [0, 1], 100, report, None, None)
        self.assertIs(kept, doc)
        self.assertFalse(result['selected'])
        self.assertEqual(result['reason_codes'], ['stationary_target_geometry_failed'])
        self.assertIn('stationary_attempt', result)

    def test_passing_candidate_is_selected_without_mutating_report_or_motion(self):
        doc, motion = target()
        report = dict(status='inferred_proxy_drift', selected=False,
                      hypothesis=dict(markers=motion['markers'], ticks_per_second=1000000))
        before = deepcopy((doc, motion, report))
        candidate = deepcopy(doc)
        candidate['animations']['walk']['bones']['root']['translate'][-1]['x'] = 0
        attempt = dict(after=dict(intervals=[dict(samples=[dict(time=0), dict(time=1)])]))
        module = 'autospine_workbench.targets.character43.stationary_contact_policy.'
        with patch(module+'inspect_source', return_value={'eligible': True}), \
             patch(module+'build', return_value=(candidate, attempt)), \
             patch(module+'inspect', return_value={'passed': True}):
            selected, result = select(doc, 'walk', motion, [0, 1], 100, report, None, None)
        self.assertEqual((doc, motion, report), before)
        self.assertIs(selected, candidate)
        self.assertTrue(result['selected'])
        self.assertEqual(result['status'], 'inferred_proxy_corrected')
        self.assertEqual(result['reason_codes'], [])


if __name__ == '__main__':
    unittest.main()
