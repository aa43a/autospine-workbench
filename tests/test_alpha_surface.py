import unittest
import numpy as np
from autospine_workbench.targets.character43.alpha_surface import build


class AlphaSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.uv = np.array([[.15,.15],[.85,.15],[.85,.85],[.15,.85],[.55,.55]])
        self.points = self.uv*20+[30,-40]
        self.tri = [[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        self.alpha = np.full((10,10),255)

    def test_setup_and_uv_preserved_with_calibrated_scale(self):
        result = build(self.points,self.uv,self.tri,self.alpha)
        np.testing.assert_array_equal(np.array(result['vertices'])[:,:2],self.points)
        np.testing.assert_array_equal(result['uvs'],self.uv)
        self.assertAlmostEqual(result['pixel_to_world'],2)
        self.assertGreater(result['vertices'][4][2],result['vertices'][0][2])
        self.assertFalse(result['accepted'])

    def test_hole_has_no_invented_depth(self):
        self.alpha[5,5] = 0
        self.assertEqual(build(self.points,self.uv,self.tri,self.alpha)['vertices'][4][2],0)

    def test_rejects_deformed_or_anisotropic_mapping(self):
        changed = self.points.copy(); changed[4,0] += 1
        for points in (changed,self.points*[2,1]):
            with self.assertRaises(ValueError): build(points,self.uv,self.tri,self.alpha)

    def test_invalid_geometry_rejected(self):
        with self.assertRaises(ValueError): build(self.points,self.uv,[[0,1,99]],self.alpha)
        with self.assertRaises(ValueError): build(self.points,self.uv,self.tri,self.alpha,float('nan'))
