import unittest
import numpy as np
from m4_alpha_contour_clip import clip


class ContourClipTests(unittest.TestCase):
    def test_hole_and_affine_interpolation_preserved(self):
        uv=np.array([[0.,0],[1,0],[1,1],[0,1]])
        points=np.column_stack((uv*10,uv[:,0]*2+uv[:,1]))
        alpha=np.full((10,10),255);alpha[4:6,4:6]=0
        r=clip(points,uv,[[0,1,2],[0,2,3]],alpha)
        self.assertEqual(r['contour_rings'],2)
        self.assertLess(r['clipped_area'],100)
        co=np.asarray(r['coefficients']);np.testing.assert_allclose(co.sum(axis=1),1)
        self.assertGreaterEqual(co.min(),0)
        np.testing.assert_allclose(co@uv,r['uvs'],atol=1e-9)
        np.testing.assert_allclose(co@points,r['vertices'])
        # No triangle can fill the center of the transparent hole.
        from shapely import Polygon,Point,union_all
        union=union_all([Polygon(np.asarray(r['uvs'])[f]) for f in r['triangles']])
        self.assertFalse(union.contains(Point(.5,.5)))

    def test_reports_material_outside_source(self):
        r=clip([[0,0,0],[5,0,0],[0,5,0]],[[0,0],[.5,0],[0,.5]],[[0,1,2]],np.full((10,10),255))
        self.assertGreater(r['outside_source_area'],70)
