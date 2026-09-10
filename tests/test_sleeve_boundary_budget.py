import unittest
from autospine_workbench.asset.planning.sleeve_boundary_budget import estimate


class BoundaryBudgetTests(unittest.TestCase):
    def test_exact_displacement_bound_and_cap(self):
        setup=[[0.,0.],[2.,0.],[0.,2.]];points=[[0.,0.],[2.,0.],[0.,-1.]]
        budget,e=estimate(setup,[[0,1,2]],points,[2],1.)
        self.assertAlmostEqual(e['required_lower_bound_px'],2.1)
        self.assertAlmostEqual(budget,2.31)
        budget,e=estimate(setup,[[0,1,2]],points,[2],.1)
        self.assertTrue(e['cap_exceeded']);self.assertAlmostEqual(budget,1/3)

    def test_fixed_failure_and_similarity(self):
        p=[[0.,0.],[2.,0.],[0.,2.]];q=[[0.,0.],[2.,0.],[0.,-1.]]
        _,e=estimate(p,[[0,1,2]],q,[],1.);self.assertEqual(e['fixed_triangle_failures'],[0])
        transform=lambda rows:[[30-3*x,20+3*y] for x,y in rows]
        b,_=estimate(p,[[0,1,2]],q,[2],1.)
        c,_=estimate(transform(p),[[0,1,2]],transform(q),[2],3.)
        self.assertAlmostEqual(c,3*b)
        self.assertEqual(estimate(p,[[0,1,2]],p,[2],1.)[0],1.)

    def test_edge_displacement_lower_bound_and_fixed_edge_failure(self):
        p=[[0.,0.],[1.,0.],[0.,1.]];q=[[0.,0.],[4.,0.],[0.,1.]]
        budget,e=estimate(p,[[0,1,2]],q,[1],1.,include_edges=True)
        edge=next(r for r in e['edge_requirements'] if r['edge']==[0,1])
        self.assertAlmostEqual(edge['required_px'],2.1)
        self.assertGreaterEqual(budget,2.31)
        _,e=estimate(p,[[0,1,2]],q,[0,1],1.,include_edges=True)
        self.assertAlmostEqual(next(r for r in e['edge_requirements'] if r['edge']==[0,1])['required_px'],1.05)
        _,e=estimate(p,[[0,1,2]],q,[],1.,include_edges=True)
        self.assertIn([0,1],e['fixed_edge_failures'])

    def test_edge_policy_remains_capped_and_similarity_invariant(self):
        p=[[0.,0.],[1.,0.],[0.,1.]];q=[[0.,0.],[4.,0.],[0.,1.]]
        budget,e=estimate(p,[[0,1,2]],q,[1],.1,include_edges=True)
        self.assertAlmostEqual(budget,1/3);self.assertTrue(e['cap_exceeded'])
        transform=lambda rows:[[18+v[1]*5,22-v[0]*5] for v in rows]
        b,_=estimate(p,[[0,1,2]],q,[1],1.,include_edges=True)
        c,_=estimate(transform(p),[[0,1,2]],transform(q),[1],5.,include_edges=True)
        self.assertAlmostEqual(c,5*b)

    def test_area_preserving_shear_needs_edge_budget_to_be_repairable(self):
        from autospine_workbench.asset.planning.cloth_anchor_solver import solve
        from autospine_workbench.asset.planning.component_temporal_qa import passed
        setup=[[0.,0.],[1.,0.],[0.,1.]];points=[[0.,0.],[1.,0.],[4.,1.]];tri=[[0,1,2]]
        old,e=estimate(setup,tri,points,[2],1.)
        self.assertEqual(e['required_lower_bound_px'],0.)
        _,before=solve(setup,tri,points,[2],[0,1],old)
        self.assertFalse(passed(before['qa']))
        new,e=estimate(setup,tri,points,[2],1.,include_edges=True)
        self.assertGreater(e['required_lower_bound_px'],0.)
        moved,after=solve(setup,tri,points,[2],[0,1],new)
        self.assertTrue(passed(after['qa']));self.assertEqual(moved[:2],points[:2])
