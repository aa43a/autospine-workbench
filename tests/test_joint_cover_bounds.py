import unittest
from autospine_workbench.targets.character43.joint_cover_bounds import cover


class JointCoverTests(unittest.TestCase):
    def test_minimum_uniform_growth_covers_both_boundaries(self):
        points=[[-1,-1],[1,-1],[1,1],[-1,1]]
        result,report=cover(points,[0,0],[[-1.5,.5],[1.2,-1.3]],2)
        self.assertAlmostEqual(report['required_scale'],1.5)
        self.assertEqual(report['status'],'bounded_geometric_cover')
        self.assertLess(report['maximum_boundary_deficit_px'],1e-8)
        self.assertAlmostEqual(result[0][0],-1.5)

    def test_over_budget_does_not_apply_partial_growth(self):
        p=[[-1,-1],[1,-1],[1,1],[-1,1]]
        result,r=cover(p,[0,0],[[3,0]],2)
        self.assertEqual(result,p);self.assertEqual(r['applied_scale'],1)
        self.assertEqual(r['status'],'coverage_exceeds_geometry_budget')
        self.assertEqual(r['maximum_boundary_deficit_px'],2)

    def test_rigid_world_transform_covariance(self):
        p=[[-1,-1],[1,-1],[1,1],[-1,1]];q=[[1.5,0]]
        f=lambda p:[-p[1]+5,p[0]-3]
        a,ra=cover(p,[0,0],q,2);b,rb=cover(list(map(f,p)),f([0,0]),list(map(f,q)),2)
        self.assertAlmostEqual(ra['required_scale'],rb['required_scale'])
        for x,y in zip(map(f,a),b):
            for u,v in zip(x,y):self.assertAlmostEqual(u,v)

    def test_outside_center_and_degenerate_input_rejected(self):
        with self.assertRaises(ValueError):cover([[0,0],[1,0],[0,1]],[2,2],[[0,0]],2)
        with self.assertRaises(ValueError):cover([[0,0],[1,0],[2,0]],[0,0],[[0,0]],2)
