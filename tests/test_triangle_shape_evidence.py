import unittest
import numpy as np
from autospine_workbench.targets.character43.triangle_shape_evidence import build,shape


class ShapeEvidenceTests(unittest.TestCase):
    rest=[[0,0],[1,0],[0,1]]

    def test_single_bone_shrink_is_distinct_from_extra_compression(self):
        setup={'bone':(1,0,0,1,0,0)};current={'bone':(.2,0,0,1,0,0)}
        raw=[[0,0],[.2,0],[0,1]]
        for height,expected in ((1,1),(.5,.5)):
            report=build(self.rest,[[0,0],[.2,0],[0,height]],raw,[[(0,1)]]*3,
                [{'name':'bone'}],setup,current)
            self.assertEqual(report['reference_kind'],'single_bone_affine')
            self.assertAlmostEqual(report['bone_compensated']['minimum_stretch'],expected)
            self.assertFalse(report['selected'])

    def test_rotation_and_translation_do_not_change_stretch(self):
        _,result=shape(self.rest,[[9,4],[9,5],[8,4]])
        self.assertAlmostEqual(result['minimum_stretch'],1)
        self.assertAlmostEqual(result['maximum_stretch'],1)

    def test_inversion_keeps_signed_area_even_when_stretch_is_one(self):
        _,result=shape(self.rest,[[0,0],[-1,0],[0,1]])
        self.assertEqual(result['signed_area_ratio'],-1)
        self.assertEqual(result['minimum_stretch'],1)

    def test_mixed_bone_reference_never_claims_exact_compensation(self):
        transforms={'a':(1,0,0,1,0,0),'b':(1,0,0,1,0,0)}
        report=build(self.rest,self.rest,self.rest,[[(0,.5),(1,.5)]]*3,
            [{'name':'a'},{'name':'b'}],transforms,transforms)
        self.assertEqual(report['reference_kind'],'mixed_bone_proxy_only')
        self.assertIsNone(report['bone_compensated'])

    def test_degenerate_and_nonfinite_points_rejected(self):
        for points in ([[0,0],[1,0],[2,0]],[[0,0],[1,0],[0,np.nan]]):
            with self.assertRaises(ValueError):shape(points,self.rest)
