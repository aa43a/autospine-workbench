import unittest
import numpy as np
from autospine_workbench.targets.character43.limb_surface_proxy import point,rotation


class SurfaceProxyTests(unittest.TestCase):
    def test_setup_reconstructs_with_shear_and_offset(self):
        m=(2.,.3,0.,1.2,7.,9.)
        for sign in (-1,1):
            for u,v in ((0.,0.),(5.,2.),(-3.,-8.)):
                np.testing.assert_allclose(point(u,v,m,m,[1.,0.,0.],10.,sign),[7+2*u+.3*v,9+1.2*v])

    def test_depth_surface_changes_when_axis_enters_screen(self):
        p=point(2.,0.,(1,0,0,1,0,0),(.6,0,0,1,0,0),[.6,0,.8],1,1)
        np.testing.assert_allclose(p,[.4,0],atol=1e-12)

    def test_rotation_is_proper_and_antipodal_is_rejected(self):
        R=rotation([0,1,0],[.3,.4,.5]);np.testing.assert_allclose(R.T@R,np.eye(3),atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(R),1.)
        with self.assertRaises(ValueError):rotation([1,0,0],[-1,0,0])

    def test_invalid_or_unobservable_source_rejected(self):
        for s in ([0,0,1],[float('nan'),0,1]):
            with self.assertRaises(ValueError):point(0,0,(1,0,0,1,0,0),(1,0,0,1,0,0),s,1,1)
