import unittest
import numpy as np
from autospine_workbench.targets.character43.surface_chain_skin import deform


class SurfaceChainTests(unittest.TestCase):
    def test_identity_and_common_rigid_rotation(self):
        p=np.array([[1.,0,2],[0,3,1]]); h=np.array([[0.,0,0],[0,2,0]])
        w=[[(0,.3),(1,.7)],[(1,1.)]]
        for r in (np.eye(3),np.array([[1.,0,0],[0,0,-1],[0,1,0]])):
            result,heads=deform(p,w,h,[r,r],[4,5,6])
            np.testing.assert_allclose(result,p@r.T+[4,5,6])
            np.testing.assert_allclose(heads,h@r.T+[4,5,6])

    def test_child_origin_follows_parent(self):
        r=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
        p,h=deform([[0,2,0]],[[(1,1.)]],[[0,0,0],[0,2,0]],[r,np.eye(3)],[0,0,0])
        np.testing.assert_allclose(p,[[-2,0,0]])

    def test_bad_weights_or_nonrigid_frames_rejected(self):
        for w,r in (([[(0,.8)]],np.eye(3)),([[(0,1.)]],np.eye(3)*2)):
            with self.assertRaises(ValueError):deform([[0,0,0]],w,[[0,0,0]],[r],[0,0,0])
