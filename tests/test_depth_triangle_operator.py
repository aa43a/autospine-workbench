import unittest
from autospine_workbench.targets.character43.depth_triangle_summary import operator_summary


class TriangleOperatorTests(unittest.TestCase):
    def row(self, time, counts, complete=True):
        return dict(pair=['arm','body'],check=dict(time=time),trace_complete=complete,
            triangle_observations=[dict(triangle=i,counts=c) for i,c in enumerate(counts)])

    def test_limits_prioritize_mixed_and_keep_full_counts(self):
        r=operator_summary([self.row(0,[dict(ambiguous=1)]*25+[dict(front=1,back=1)]),
                            self.row(1,[],False)])['pairs'][0]
        self.assertEqual(r['counts'],dict(uncertain_depth=25,within_frame_mixed=1))
        self.assertEqual(r['locations'][0]['triangle'],25)
        self.assertEqual(len(r['locations']),20)
        self.assertTrue(r['locations_truncated'])
        self.assertEqual(r['incomplete_samples'],1)

    def test_temporal_change_and_missing_trace_remain_distinct(self):
        r=operator_summary([self.row(0,[dict(front=1)]),self.row(1,[dict(back=1)])])
        self.assertEqual(r['pairs'][0]['locations'][0]['status'],'temporal_side_change')
        self.assertIsNone(operator_summary([]))
        self.assertIsNone(operator_summary([dict(check={})]))
        with self.assertRaisesRegex(ValueError,'trace_required'):
            operator_summary([self.row(0,[]),dict(check={})])


if __name__=='__main__':unittest.main()
