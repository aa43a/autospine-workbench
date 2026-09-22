import unittest
import numpy as np
from m4_pose_material_review import transfer,alpha_at


class PoseMaterialReviewTests(unittest.TestCase):
    def test_shared_edge_and_mirrored_triangle(self):
        vertices=[[0,0],[1,0],[1,1],[0,1]];values=np.asarray(vertices)*2+3
        out,valid=transfer(vertices,values,[2,1,0,3,2,0],[[.5,.5],[.25,.75],[2,2]])
        np.testing.assert_allclose(out[:2],[[4,4],[3.5,4.5]])
        self.assertEqual(valid.tolist(),[True,True,False])

    def test_inconsistent_overlapping_uv_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            transfer([[0,0],[1,0],[0,1],[0,0],[1,0],[0,1]],[[0,0]]*3+[[1,1]]*3,[0,1,2,3,4,5],[[.1,.1]])

    def test_outside_and_nan_sample_transparent(self):
        np.testing.assert_equal(alpha_at(np.array([[255]]),np.array([[.5,.5],[1,.5],[float('nan'),0]])),[255,0,0])
