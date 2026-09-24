import unittest
from m4_leg_shoe_material_probe import comparison_times


class MaterialProbeTimesTests(unittest.TestCase):
    def document(self, times):
        return {'animations': {'move': {'bones': {'foot': {'rotate': [
            {'time': t, 'value': 0} for t in times]}}}}}

    def test_uses_both_timelines_and_intermediate_samples(self):
        actual = comparison_times(self.document([0, 2]), self.document([0, .5, 2]), 'move')
        self.assertEqual(actual, [0, .25, .5, 1.25, 2])

    def test_changed_duration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duration_changed'):
            comparison_times(self.document([0, 2]), self.document([0, 3]), 'move')
