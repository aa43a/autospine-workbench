import unittest
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.spine43.continuous_pose import area


class LocalAreaActiveDomainTests(unittest.TestCase):
    def test_optimizer_success_does_not_accept_inconsistent_area_requirements(self):
        points=[[0,0],[2,0],[1,1],[2,2],[0,2]]
        ctx=dict(row={'triangles':[[0,1,2],[3,4,2]]},areas=[1.,1.],
            edges=[(0,1),(1,2),(0,2),(3,4),(4,2),(3,2)],lengths=[2]*6,
            free=[False,False,True,False,False],budget=.4,minimum_ratios=[1.1,1.1],
            area_floor_contract='raw-compression-preservation-v1-experiment')
        result,report=refine(ctx,points,points,analytic=True,active_tolerance=1e-7,feasibility_first=True)
        self.assertEqual(result,points);self.assertEqual(report['status'],'no_feasible_patch_found')
        self.assertTrue(report['optimizer_success'])
        self.assertGreater(report['residuals']['floor_deficit'],.09)

    def context(self):
        return dict(row={'triangles':[[0,1,2],[3,4,5]]},areas=[1.,1.],
            edges=[(0,1),(1,2),(0,2),(3,4),(4,5),(3,5)],lengths=[2]*6,
            free=[False,False,True,False,False,False],budget=.4,minimum_ratios=[.8,.8])

    def test_valid_frozen_roundoff_does_not_make_optimizer_infeasible(self):
        base=[[0,0],[2,0],[1,.6],[10,0],[12,0],[11,.8-1e-12]]
        points,report=refine(self.context(),base,base,analytic=True,active_tolerance=1e-7)
        self.assertEqual(report['status'],'candidate')
        self.assertGreaterEqual(area(points,[0,1,2]),.8-1e-7)
        self.assertEqual(points[3:],base[3:]);self.assertGreater(report['validated_constant_constraints'],0)

    def test_real_frozen_failure_is_retained(self):
        base=[[0,0],[2,0],[1,.6],[10,0],[12,0],[11,.7]]
        points,report=refine(self.context(),base,base,analytic=True,active_tolerance=1e-7)
        self.assertEqual(points,base);self.assertEqual(report['status'],'frozen_local_context_failed')
        self.assertEqual(report['frozen_triangles'],[1])

    def test_rejects_selection_tolerance_larger_than_existing_final_check(self):
        with self.assertRaisesRegex(ValueError,'active_tolerance_invalid'):
            refine({},[],[],active_tolerance=1e-3)
