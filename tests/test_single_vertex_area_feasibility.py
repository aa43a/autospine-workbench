import unittest
from autospine_workbench.targets.character43.single_vertex_area_feasibility import inspect


class SharedVertexAreaTests(unittest.TestCase):
    def fixture(self):
        return dict(row={'triangles':[[0,1,2],[3,4,2]]},areas=[1.,1.],
                    free=[False,False,True,False,False],budget=.2),[[0,0],[2,0],[1,1],[2,2],[0,2]]

    def test_opposed_requirements_conflict_even_when_individual_disks_allow_them(self):
        context,points=self.fixture();result=inspect(context,points,[1.1,1.1])
        self.assertEqual(len(result['failures']),1)
        row=result['failures'][0];self.assertEqual(row['vertex'],2)
        self.assertAlmostEqual(row['maximum_normal_displacement_sum'],0)
        self.assertAlmostEqual(row['required_normal_displacement_sum'],.2-2e-7)

    def test_valid_parent_and_reversed_winding_are_handled(self):
        context,points=self.fixture()
        self.assertEqual(inspect(context,points,[1.,1.])['failures'],[])
        context['row']['triangles']=[list(reversed(t)) for t in context['row']['triangles']];context['areas']=[-1.,-1.]
        self.assertEqual(len(inspect(context,points,[1.1,1.1])['failures']),1)

    def test_does_not_infer_linear_constraint_when_second_vertex_can_move(self):
        context,points=self.fixture();context['free'][0]=True
        self.assertEqual(inspect(context,points,[1.1,1.1])['failures'],[])
