import unittest
from autospine_workbench.targets.spine43.seam_shape_solver import solve,admissible


class ShapeSolverTests(unittest.TestCase):
    def fixture(self):
        vertices=[[0.,0.],[1.,0.],[0.,1.],[200.,200.]]
        anchors=[{'triangle':[0,1,2],'barycentric':[float(i==j) for i in range(3)]} for j in range(3)]
        return vertices,anchors,[[0,1,2]]

    def test_zero_and_outside_support(self):
        v,a,t=self.fixture();moves,qa=solve(v,a,[[0,0]]*3,t,[[0,1,2]])
        self.assertEqual(moves,[[0.,0.]]*4);self.assertEqual(qa['tangent_constraints'],2)
        moves,_=solve(v,a,[[2,1]]*3,t,[[0,1,2]])
        self.assertEqual(moves[-1],[0.,0.]);self.assertTrue(admissible(v,moves,t))

    def test_inversion_rejected_and_large_move_capped(self):
        v,a,t=self.fixture();self.assertFalse(admissible(v,[[0,0],[-2,0],[0,0],[0,0]],t))
        moves,qa=solve(v,a,[[100,0],[-100,0],[0,100]],t,[[0,1,2]])
        self.assertTrue(admissible(v,moves,t))
        self.assertTrue(all((x*x+y*y)**.5<=12+1e-8 for x,y in moves))
        self.assertGreater(qa['backtracks'],0)

    def test_invalid_targets_and_chain_fail(self):
        v,a,t=self.fixture()
        with self.assertRaisesRegex(ValueError,'shape_target_nonfinite'):solve(v,a,[[float('nan'),0]]*3,t,[])
        with self.assertRaisesRegex(ValueError,'shape_chain_reference'):solve(v,a,[[0,0]]*3,t,[[0,9]])

    def test_repeat_is_exact(self):
        v,a,t=self.fixture();args=(v,a,[[1,0],[2,1],[1,-1]],t,[[0,1,2]])
        self.assertEqual(solve(*args),solve(*args))
