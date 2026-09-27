import unittest
from autospine_workbench.targets.character43.lower_limb_projection import view_summary


class KneeViewSummaryTests(unittest.TestCase):
    def test_depth_bend_readable_in_side_view(self):
        vectors={f'humanoid.leg.{part}.{side}':[v] for side in ('left','right')
                 for part,v in [('upper',[0,1,1]),('lower',[0,1,-1])]}
        front=view_summary(vectors,0);side=view_summary(vectors,90)
        self.assertAlmostEqual(front['maximum_hidden_bend_deg'],90)
        self.assertAlmostEqual(side['maximum_hidden_bend_deg'],0)
        self.assertEqual(front['samples_losing_30_degrees'],2)

    def test_mismatched_samples_rejected(self):
        vectors={f'humanoid.leg.{part}.{side}':[[0,1,0]] for side in ('left','right') for part in ('upper','lower')}
        vectors['humanoid.leg.lower.right']=[]
        with self.assertRaises(ValueError):view_summary(vectors,0)
