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
