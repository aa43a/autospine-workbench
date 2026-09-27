import unittest
import numpy as np
from autospine_workbench.targets.character43.regional_patch_geometry import constraints
from autospine_workbench.targets.character43.regional_material_support import solve


class RegionalGeometryTests(unittest.TestCase):
    def test_constraint_gradient_matches_independent_finite_difference(self):
        points=[[0,0],[10,0],[10,10],[0,10]]
        c=constraints(points,points,[[0,1,2],[0,3,2]],[1,2],8)
        x=np.array([.1,.2,-.1,.15]);expected=c['jac'](x);eps=1e-6
        numerical=np.column_stack([(c['fun'](x+np.eye(4)[i]*eps)-c['fun'](x-np.eye(4)[i]*eps))/(2*eps) for i in range(4)])
        self.assertTrue(np.allclose(expected,numerical,atol=1e-8))

    def test_area_limit_prevents_collapsing_material_target(self):
        points=[[0,0],[10,0],[10,10],[0,10]]
        result,report=solve(points,points,[[0,1,2],[0,2,3]],
            [dict(vertices=[0,1,2],weights=[0,0,1])],[[10,2]],[0,1,3],geometry=True)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result[2][1]/10,.5)
        self.assertGreater(report['maximum_target_error_px'],2.9)
        self.assertEqual([result[i] for i in (0,1,3)],[points[i] for i in (0,1,3)])
