from copy import deepcopy
import unittest

from autospine_workbench.motion2d.contact_candidate import infer
from autospine_workbench.motion2d.phase_support import inspect
from test_motion_contact_candidate import fixture


class PhaseSupportTests(unittest.TestCase):
    def test_slow_glide_is_not_stationary_and_input_preserved(self):
        bvh, mapping = fixture(speed=.002)
        hypothesis = infer(bvh, mapping, source_up='+Y')
        original = deepcopy(hypothesis)
        self.assertEqual(len(hypothesis['markers']), 2)
        result = inspect(bvh, mapping, hypothesis)
        self.assertEqual(result['eligible_intervals'], 0)
        self.assertTrue(all(r['maximum_drift_ratio'] > .01 for r in result['records']))
        self.assertEqual(hypothesis, original)
        self.assertFalse(result['selected'])

    def test_stationary_and_half_open_local_anchor(self):
        bvh, mapping = fixture(speed=.002)
        hypothesis = infer(bvh, mapping, source_up='+Y')
        for row in hypothesis['markers']:
            row.update(start_tick=300000, end_tick=400000)
        result = inspect(bvh, mapping, hypothesis)
        self.assertEqual(result['eligible_intervals'], 2)
        self.assertTrue(all(r['worst_tick'] < 400000 for r in result['records']))
        bvh, mapping = fixture()
        self.assertEqual(inspect(bvh, mapping, infer(bvh, mapping))['eligible_intervals'], 2)

    def test_missing_samples_and_stale_identity(self):
        bvh, mapping = fixture()
        hypothesis = infer(bvh, mapping)
        for row in hypothesis['markers']:
            row.update(start_tick=1, end_tick=2)
        self.assertEqual(inspect(bvh, mapping, hypothesis)['eligible_intervals'], 0)
        hypothesis['source_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            inspect(bvh, mapping, hypothesis)


if __name__ == '__main__':
    unittest.main()
