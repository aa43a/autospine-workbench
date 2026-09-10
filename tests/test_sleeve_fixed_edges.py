import unittest
from autospine_workbench.asset.planning.sleeve_fixed_edges import inspect,inspect_areas


class FixedEdgeTests(unittest.TestCase):
    def test_area_collapse_can_pass_every_edge_limit(self):
        points=[[0,0],[2,0],[0,2]];tri=[[0,1,2]]
        tracks=[dict(bone_id='fold',samples=[dict(points=[[0,0],[2,0],[0,.2]])])]
        self.assertEqual(inspect(points,tri,[0,1,2],tracks)['status'],'no_fixed_edge_counterexample')
        result=inspect_areas(points,tri,[0,1,2],tracks)
        self.assertEqual(result['status'],'infeasible_with_fixed_vertices')
        self.assertAlmostEqual(result['witnesses'][0]['ratio'],.1)
        self.assertEqual(inspect_areas(points,tri,[0,1],tracks)['witnesses'],[])

    def test_fixed_area_rigid_transform_passes_and_degenerate_fails(self):
        points=[[0,0],[2,0],[0,2]];tri=[[0,1,2]]
        tracks=[dict(bone_id='turn',samples=[dict(points=[[3,4],[3,6],[1,4]])])]
        self.assertEqual(inspect_areas(points,tri,[0,1,2],tracks)['witnesses'],[])
        with self.assertRaisesRegex(ValueError,'degenerate'):
            inspect_areas([[0,0],[1,0],[2,0]],tri,[0,1,2],[])

    def test_protected_edge_cannot_be_repaired_by_free_third_vertex(self):
        points=[[0,0],[1,0],[0,1]]
        tracks=[dict(bone_id='motion',samples=[dict(points=[[0,0],[3,0],[0,99]])])]
        result=inspect(points,[[0,1,2]],[0,1],tracks)
        self.assertEqual(result['status'],'infeasible_with_fixed_endpoints')
        self.assertEqual(result['witnesses'][0]['ratio'],3)
        self.assertEqual(inspect(points,[[0,1,2]],[0],tracks)['status'],'no_fixed_edge_counterexample')

    def test_rigid_transform_and_scale_do_not_change_verdict(self):
        for scale in (1,100):
            points=[[0,0],[scale,0],[0,scale]]
            tracks=[dict(bone_id='motion',samples=[dict(points=[[5,8],[5,8+scale],[5-scale,8]])])]
            self.assertEqual(inspect(points,[[0,1,2]],[0,1,2],tracks)['peak_ratio'],1)

    def test_invalid_sample_fails(self):
        with self.assertRaisesRegex(ValueError,'sample'):
            inspect([[0,0],[1,0],[0,1]],[[0,1,2]],[0,1],
                    [dict(bone_id='x',samples=[dict(points=[[0,0]])])])
