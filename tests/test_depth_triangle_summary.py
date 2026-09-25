import unittest
from autospine_workbench.targets.character43.depth_triangle_summary import summarize


def row(time,counts,complete=True):
    return dict(pair=['arm','body'],check=dict(time=time),trace_complete=complete,
                triangle_observations=[dict(triangle=3,counts=counts)])


class TriangleSummaryTests(unittest.TestCase):
    def status(self,records):return summarize(records)['pairs'][0]['triangles'][0]['status']

    def test_temporal_change_is_not_spatial_mixing(self):
        self.assertEqual(self.status([row(0,{'front':4}),row(1,{'back':3})]),'temporal_side_change')
        self.assertEqual(self.status([row(0,{'front':4,'back':3})]),'within_frame_mixed')

    def test_uncertainty_and_incomplete_samples_cannot_confirm_side(self):
        self.assertEqual(self.status([row(0,{'front':4,'ambiguous':1})]),'uncertain_depth')
        result=summarize([row(0,{'front':4}),row(1,{'back':3},False)])
        pair=result['pairs'][0]
        self.assertEqual(pair['triangles'][0]['status'],'observed_front_only')
        self.assertEqual(pair['incomplete_times'],[1])
        self.assertFalse(result['selected'])

    def test_invalid_inventory_rejected(self):
        for counts in ({'front':-1},{'front':True},{'bogus':1}):
            with self.assertRaisesRegex(ValueError,'observation_invalid'):summarize([row(0,counts)])
