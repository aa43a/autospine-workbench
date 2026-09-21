import math
import unittest
from autospine_workbench.targets.character43.local_area_constraints import refine


class LocalAreaTests(unittest.TestCase):
    def test_repairs_small_fold_without_moving_fixed_edge(self):
        base=[[0,0],[2,0],[1,1]];initial=[[0,0],[2,0],[1,-.1]]
        context=dict(row={'triangles':[[0,1,2]]},areas=[1],edges=[(0,1),(1,2),(0,2)],
                     lengths=[2,math.sqrt(2),math.sqrt(2)],free=[False,False,True],budget=1.2)
        result,report=refine(context,base,initial)
        self.assertEqual(report['status'],'candidate')
        self.assertEqual(result[:2],base[:2]);self.assertGreaterEqual(result[2][1],.5)
        self.assertLessEqual(math.dist(result[2],base[2]),1.2+1e-7)

    def test_impossible_patch_keeps_input_unchanged(self):
        base=[[0,0],[2,0],[1,-1]]
        context=dict(row={'triangles':[[0,1,2]]},areas=[1],edges=[(0,1),(1,2),(0,2)],
                     lengths=[2,math.sqrt(2),math.sqrt(2)],free=[False,False,True],budget=.1)
        result,report=refine(context,base,base)
        self.assertEqual(result,base);self.assertNotEqual(report['status'],'candidate')
