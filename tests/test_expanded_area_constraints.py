import math
import unittest
from autospine_workbench.targets.character43.local_area_constraints import refine


class ExpandedAreaTests(unittest.TestCase):
    def fixture(self,count):
        base=[];initial=[];tri=[];edges=[];free=[]
        for n in range(count):
            i=len(base);x=4*n
            base.extend([[x,0],[x+2,0],[x+1,1]])
            initial.extend([[x,0],[x+2,0],[x+1,.6]])
            tri.append([i,i+1,i+2]);edges.extend([(i,i+1),(i+1,i+2),(i,i+2)])
            free.extend([False,False,True])
        return base,initial,dict(row={'triangles':tri},areas=[1]*count,edges=edges,
            lengths=[2,math.sqrt(2),math.sqrt(2)]*count,free=free,budget=1,minimum_ratios=[.9]*count)

    def test_opt_in_solves_beyond_old_limit_without_changing_default(self):
        base,initial,context=self.fixture(33)
        unchanged,report=refine(context,base,initial,analytic=True)
        self.assertEqual(report['status'],'local_patch_unavailable');self.assertEqual(unchanged,initial)
        points,report=refine(context,base,initial,analytic=True,expanded=True)
        self.assertEqual(report['status'],'candidate')
        for i,(a,b) in enumerate(zip(base,points)):
            if i%3!=2:self.assertEqual(a,b)
            else:self.assertGreaterEqual(b[1],.9-1e-7);self.assertLessEqual(math.dist(a,b),1+1e-7)

    def test_expanded_still_has_resource_bound_and_requires_derivatives(self):
        base,initial,context=self.fixture(129)
        points,report=refine(context,base,initial,analytic=True,expanded=True)
        self.assertEqual(report['status'],'local_patch_unavailable');self.assertEqual(points,initial)
        with self.assertRaisesRegex(ValueError,'requires_analytic'):
            refine(context,base,initial,expanded=True)
