import unittest
from autospine_workbench.targets.character43.boundary_shape_feasible import refine


class FeasibilityTests(unittest.TestCase):
    def test_fixed_boundary_preserved_and_compressed_triangle_recovered(self):
        rest=[[0.,0.],[2.,0.],[0.,2.]];seed=[[0.,0.],[2.,0.],[0.,.2]]
        points,report=refine(rest,[[0,1,2]],seed,[2],seed,seed,2)
        self.assertEqual(report['status'],'feasible_candidate')
        self.assertEqual(points[:2],seed[:2])
        self.assertGreaterEqual(report['geometry']['min_area_ratio'],.5)
        self.assertLessEqual(report['maximum_displacement_px'],2)

    def test_fixed_edge_conflict_does_not_return_optimizer_shape(self):
        rest=[[0.,0.],[2.,0.],[0.,2.]];seed=[[0.,0.],[6.,0.],[0.,2.]]
        points,report=refine(rest,[[0,1,2]],seed,[2],seed,seed,10)
        self.assertEqual(report['status'],'fixed_constraint_conflict')
        self.assertEqual(points,seed)

    def test_unreachable_area_keeps_original(self):
        rest=[[0.,0.],[2.,0.],[0.,2.]];seed=[[0.,0.],[2.,0.],[0.,.2]]
        points,report=refine(rest,[[0,1,2]],seed,[2],seed,seed,.01)
        self.assertEqual(report['status'],'no_feasible_candidate_found')
        self.assertEqual(points,seed)
