import unittest
from autospine_workbench.targets.character43.fixed_boundary_area import inspect


class FixedBoundaryAreaTests(unittest.TestCase):
    def context(self):
        return dict(row={'triangles':[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]},
                    areas=[1.]*4,free=[False]*4+[True])

    def test_detects_joint_conflict_even_when_each_triangle_can_grow(self):
        points=[[0,0],[2,0],[2,2],[0,2],[1,1]]
        report=inspect(self.context(),points,[1.1]*4)
        self.assertEqual(report['infeasible_patches'],1)
        self.assertAlmostEqual(report['patches'][0]['fixed_area'],4)
        self.assertAlmostEqual(report['patches'][0]['deficit'],.4)

    def test_area_sum_invariant_under_interior_motion_and_winding(self):
        for center in ([1,1],[.2,1.5],[3,4]):
            ctx=self.context();ctx['row']['triangles']=[list(reversed(t)) for t in ctx['row']['triangles']];ctx['areas']=[-1.]*4
            report=inspect(ctx,[[0,0],[2,0],[2,2],[0,2],center],[1.]*4)
            self.assertEqual(report['infeasible_patches'],0)
            self.assertAlmostEqual(report['patches'][0]['fixed_area'],4)

    def test_open_movable_boundary_or_invalid_topology_does_not_claim_proof(self):
        points=[[0,0],[2,0],[2,2],[0,2],[1,1]]
        ctx=self.context();ctx['free'][0]=True
        self.assertEqual(inspect(ctx,points,[2]*4)['patches'],[])
        ctx=self.context();ctx['row']['triangles'][0]=[0,4,1]
        self.assertEqual(inspect(ctx,points,[2]*4)['patches'],[])
