import unittest
from autospine_workbench.targets.character43.material_anchor_constraints import inspect_paths


class MaterialAnchorConstraintTests(unittest.TestCase):
    def test_indirect_path_proves_infeasible_even_with_free_middle(self):
        rest=[[0,0],[1,0],[2,0],[1,1]]
        result=inspect_paths(rest,rest,[[0,1,3],[1,2,3]],{0:[-3,0]},[0,1,3])
        self.assertEqual(result['status'],'infeasible_fixed_anchors')
        witness=result['witnesses'][0]
        self.assertEqual(witness['path'],[0,1,2])
        self.assertEqual(witness['minimum_required_edge_stretch'],2.5)

    def test_exact_bound_is_not_a_feasibility_claim(self):
        rest=[[0,0],[1,0],[0,1]]
        result=inspect_paths(rest,rest,[[0,1,2]],{0:[-1,0]},[0,2])
        self.assertEqual(result['status'],'no_path_counterexample')
        self.assertFalse(result['sufficiency'])
        self.assertFalse(result['selected'])

    def test_disconnected_fixed_point_does_not_create_constraint(self):
        rest=[[0,0],[1,0],[0,1],[100,100]]
        result=inspect_paths(rest,rest,[[0,1,2]],{0:[0,0]},[0,1,2])
        self.assertEqual(result['checked_pairs'],0)
