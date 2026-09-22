import unittest
from m4_reach_continuity_audit import inspect


def document(values):
    return dict(bones=[dict(name='upperarm_r', x=0, y=0, rotation=0)],
                animations={'test': {'bones': {'upperarm_r': {'rotate': values}}}})


class ContinuityAuditTests(unittest.TestCase):
    def test_continuous_crossing_is_label_wrap_only(self):
        row = inspect(document([dict(time=0, value=179), dict(time=1, value=181)]), 'test')['rows'][0]
        self.assertEqual(row['local_half_turn_intervals'], [])
        self.assertEqual(len(row['world_label_wraps']), 1)
        self.assertLess(row['maximum_world_sample_step']['degrees'], .01)

    def test_raw_branch_and_whole_turn_are_not_hidden(self):
        for end in (-179, 539):
            row = inspect(document([dict(time=0, value=179), dict(time=1, value=end)]), 'test')['rows'][0]
            self.assertEqual(len(row['local_half_turn_intervals']), 1)

    def test_duplicate_times_and_curves_rejected(self):
        for keys in ([dict(time=0, value=0), dict(time=0, value=1)],
                     [dict(time=0, value=0, curve=[.1,.2,.3,.4])]):
            with self.assertRaises(ValueError):
                inspect(document(keys), 'test')

    def test_stepped_jump_remains_visible_in_world_samples(self):
        row = inspect(document([dict(time=0, value=0, curve='stepped'),
                                dict(time=1, value=180)]), 'test')['rows'][0]
        self.assertEqual(row['maximum_world_sample_step']['degrees'], 180)
