import unittest
from autospine_workbench.targets.character43.contact_region_path_bounds import inspect


class RegionPathTests(unittest.TestCase):
    def test_far_contact_cannot_reach_fixed_endpoint_with_bounded_edges(self):
        points=[[0,0],[1,1],[2,0]]
        region=dict(vertex=0,center=[10,0],inverse=[[1,0],[0,1]],radius=.5)
        report=inspect(points,[[0,1,2]],points,[0,1],[region])
        self.assertEqual(report['status'],'contact_region_path_conflict')
        self.assertAlmostEqual(report['witnesses'][0]['minimum_possible_distance_px'],7.5)
        region.update(inverse=[[.1,0],[0,1]],radius=1)
        self.assertEqual(inspect(points,[[0,1,2]],points,[0,1],[region])['status'],'no_region_path_counterexample')


if __name__=='__main__':unittest.main()
