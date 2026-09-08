import unittest
import numpy as np
from autospine_workbench.targets.spine43.seam_direct_alpha import sample,patch
from autospine_workbench.targets.spine43.seam_raster import mask


class DirectAlphaTests(unittest.TestCase):
    def fixture(self):
        return {'uvs':[0,0,1,0,1,1,0,1],'triangles':[0,1,2,0,2,3]},[[0,0],[4,0],[4,-4],[0,-4]],np.arange(16).reshape(4,4)*16.

    def test_native_lattice_agrees_with_raster(self):
        a,p,t=self.fixture();points=[[x+.5,-y-.5] for y in range(4) for x in range(4)]
        result,covered=sample(a,p,t,points)
        np.testing.assert_allclose(result.reshape(4,4),mask(a,p,t,[0,0,4,4]),atol=1e-10)
        self.assertTrue(covered.all())

    def test_subpixel_bilinear_and_outside(self):
        a,p,t=self.fixture();values,covered=sample(a,p,t,[[1,-1],[5,5]])
        self.assertAlmostEqual(values[0],40.)
        self.assertEqual(values[1],0);self.assertFalse(covered[1])

    def test_alpha_union_not_equivalent_to_per_attachment_threshold(self):
        a,p,_=self.fixture();t=np.full((4,4),5.)
        result,_=patch([2,-2],[a,a],[p,p],[t,t],8)
        self.assertEqual(result['both_below8'],64);self.assertEqual(result['union_below8'],0)

    def test_invalid_points_and_resolution(self):
        a,p,t=self.fixture()
        with self.assertRaises(ValueError): sample(a,p,t,[[float('nan'),0]])
        with self.assertRaises(ValueError): patch([2,-2],[a,a],[p,p],[t,t],4)
