import unittest
from autospine_workbench.targets.character43.material_anchor_field import solve


class MaterialAnchorFieldTests(unittest.TestCase):
    def test_fixed_border_and_exact_anchor_with_smooth_interior(self):
        points=[[0,0],[2,0],[2,2],[0,2],[1,1]]
        triangles=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        result,report=solve(points,points,triangles,{0:[0,1]},[0,4])
        self.assertEqual(result[:4],[[0,1],[2,0],[2,2],[0,2]])
        self.assertAlmostEqual(result[4][1],1.25)
        self.assertEqual(report['maximum_anchor_error_px'],0)

    def test_unconstrained_component_rejected(self):
        points=[[0,0],[1,0],[0,1],[3,0],[4,0],[3,1]]
        with self.assertRaisesRegex(ValueError,'unconstrained'):
            solve(points,points,[[0,1,2],[3,4,5]],{0:[0,0]},list(range(6)))

    def test_no_displacement_preserves_pose(self):
        points=[[0,0],[1,0],[0,1]]
        result,_=solve(points,points,[[0,1,2]],{0:[0,0]},[0,1,2])
        self.assertEqual(result,points)
