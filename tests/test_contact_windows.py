import unittest
from autospine_workbench.targets.character43.contact_windows import for_motion


class ContactWindowTests(unittest.TestCase):
    def test_nonzero_original_interval_maps_into_clip(self):
        motion = dict(markers=[], ticks_per_second=100, duration_ticks=100)
        h = dict(ticks_per_second=100, markers=[dict(kind='contact', limb='leg.left',
                     start_tick=220, end_tick=280)])
        result = for_motion(motion, h, (2000000, 3000000))
        self.assertEqual((result[0]['start_tick'], result[0]['end_tick']), (20, 80))
        self.assertEqual(h['markers'][0]['start_tick'], 220)

    def test_wrong_clip_duration_rejected(self):
        motion = dict(markers=[], ticks_per_second=100, duration_ticks=100)
        h = dict(ticks_per_second=100, markers=[])
        for bounds in ((0, 2000000), (-1, 999999), (0, 0)):
            with self.assertRaisesRegex(ValueError, 'clip_bounds_invalid'):
                for_motion(motion, h, bounds)

    def test_existing_labels_cannot_be_replaced(self):
        with self.assertRaisesRegex(ValueError, 'take_precedence'):
            for_motion(dict(markers=[dict(kind='contact')]), {})
