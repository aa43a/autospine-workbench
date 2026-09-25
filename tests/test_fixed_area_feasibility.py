import unittest
from autospine_workbench.targets.character43.fixed_area_feasibility import inspect


class FixedAreaTests(unittest.TestCase):
    def test_fixed_compression_is_proof_but_free_vertex_is_not(self):
        args=('leg',[[0,1,2]],[.5],[False]*3,[0],[[[0,0],[1,0],[0,.3]]],[[.15]])
        report=inspect(*args)
        self.assertEqual(report['status'],'infeasible_fixed_vertices')
        self.assertAlmostEqual(report['failures'][0]['setup_ratio'],.3)
        mutable=list(args);mutable[3]=[False,True,False]
        self.assertEqual(inspect(*mutable)['status'],'no_fixed_triangle_counterexample')

    def test_orientation_and_projected_failure(self):
        r=inspect('leg',[[0,2,1]],[-.5],[False]*3,[0],[[[0,0],[1,0],[0,1]]],[[-.1]])
        self.assertEqual(r['failures'][0]['setup_ratio'],1)
        self.assertEqual(r['failures'][0]['projected_ratio'],5)


if __name__=='__main__':unittest.main()
