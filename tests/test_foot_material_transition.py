import unittest
from autospine_workbench.targets.character43.foot_material_transition import solve


class FootMaterialTransitionTests(unittest.TestCase):
    def fixture(self):
        setup=[[0,0],[1,0],[0,1],[1,1],[0,2],[1,2]]
        vertices=[]
        for i in range(6):
            influences=[(0,1)] if i<2 else ([(0,.5),(1,.5)] if i<4 else [(1,1)])
            vertices.append(len(influences))
            for bone,weight in influences:vertices.extend([bone,*setup[i],weight])
        return setup,dict(vertices=vertices,triangles=[0,1,2,1,3,2,2,3,4,3,5,4])

    def test_fixed_calf_and_exact_foot_targets(self):
        setup,mesh=self.fixture();adjusted=[p[:] for p in setup]
        for i in (4,5):adjusted[i][0]+=.2
        result,report=solve(mesh,setup,setup,adjusted,1,0)
        self.assertEqual(result[:2],setup[:2])
        self.assertEqual(result[4:],adjusted[4:])
        self.assertTrue(0<result[2][0]<.2)
        self.assertTrue(report['transition_passed'])
        self.assertFalse(report['selected'])

    def test_impossible_anchors_are_not_reported_as_pass(self):
        setup,mesh=self.fixture();adjusted=[p[:] for p in setup]
        for i in (4,5):adjusted[i][0]+=20
        _,report=solve(mesh,setup,setup,adjusted,1,0)
        self.assertEqual(report['constraints']['status'],'infeasible_fixed_anchors')
        self.assertFalse(report['transition_passed'])

    def test_hard_refinement_does_not_move_fixed_ends_to_claim_success(self):
        setup,mesh=self.fixture();adjusted=[p[:] for p in setup]
        for i in (4,5):adjusted[i][0]+=20
        result,report=solve(mesh,setup,setup,adjusted,1,0,refine_transition=True)
        self.assertEqual(result[:2],setup[:2])
        self.assertEqual(result[4:],adjusted[4:])
        self.assertFalse(report['transition_passed'])
        self.assertNotEqual(report['hard_refinement']['status'],'feasible_candidate')
