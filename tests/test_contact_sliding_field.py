import unittest
import numpy as np
from autospine_workbench.targets.character43.contact_sliding_field import solve


class ContactSlidingFieldTests(unittest.TestCase):
    def setUp(self):
        self.points=[[0,0],[2,0],[2,2],[0,2]]
        self.tris=[[0,1,2],[0,2,3]]

    def guide(self,origin,limits=(-4,4),tangent=(1,0)):
        return dict(origin=list(origin),limits=list(limits),tangent=list(tangent))

    def test_tangential_reference_motion_does_not_drag_material(self):
        actual,report=solve(self.points,self.points,self.tris,{}, {2:self.guide((5,2))})
        np.testing.assert_allclose(actual,self.points,atol=1e-10)
        self.assertEqual(report['status'],'single_pose_requires_validation')
        self.assertFalse(report['selected'])
        self.assertEqual(self.points,[[0,0],[2,0],[2,2],[0,2]])

    def test_normal_constraint_preserves_unspecified_vertices(self):
        actual,report=solve(self.points,self.points,self.tris,{}, {2:self.guide((2,2.2))})
        np.testing.assert_allclose(actual[2],[2,2.2],atol=1e-10)
        for v in (0,1,3):self.assertEqual(actual[v],self.points[v])
        self.assertEqual(report['after']['inversions'],0)

    def test_limits_not_extended_to_improve_geometry(self):
        actual,report=solve(self.points,self.points,self.tris,{}, {2:self.guide((20,2),(-.5,.5))})
        np.testing.assert_allclose(actual[2],[19.5,2],atol=1e-8)
        self.assertEqual(report['status'],'rejected_geometry')

    def test_preserved_or_fixed_conflicts_fail_instead_of_overriding(self):
        with self.assertRaisesRegex(ValueError,'preserved_conflict'):
            solve(self.points,self.points,self.tris,{2:[3,2]}, {},preserved=[2])
        with self.assertRaisesRegex(ValueError,'shared_guide_conflict'):
            solve(self.points,self.points,self.tris,{2:[2,3]}, {2:self.guide((2,2))})
        actual,_=solve(self.points,self.points,self.tris,{2:[2,2]}, {2:self.guide((3,2))},preserved=[2])
        self.assertEqual(actual,self.points)

    def test_missing_support_and_invalid_direction_rejected(self):
        with self.assertRaisesRegex(ValueError,'underdetermined'):
            solve(self.points,self.points,self.tris,{}, {i:self.guide(p) for i,p in enumerate(self.points)})
        with self.assertRaisesRegex(ValueError,'guide_invalid'):
            solve(self.points,self.points,self.tris,{}, {2:self.guide((2,2),tangent=(0,0))})
