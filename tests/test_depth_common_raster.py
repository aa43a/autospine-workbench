import unittest
import numpy as np
from autospine_workbench.targets.character43.depth_common_raster import raster
from autospine_workbench.targets.spine43.seam_raster import mask
from autospine_workbench.targets.character43.depth_group_raster import raster as cropped


class CommonRasterTests(unittest.TestCase):
    def test_random_transformed_alpha_and_overlapping_triangles_match_dense(self):
        rng=np.random.default_rng(31)
        for _ in range(40):
            vertices=rng.uniform(-15,15,(6,2)).tolist()
            attachment=dict(triangles=[0,1,2,3,4,5],uvs=rng.uniform(-.2,1.2,12).tolist())
            alpha=rng.integers(0,256,(11,9)).astype(float)
            common=rng.random((32,32))>.7;charges=[];rect=[-16,-16,32,32]
            actual=raster(attachment,vertices,alpha,rect,common,charges.append)
            expected=(mask(attachment,vertices,alpha,rect)>=8)&common
            np.testing.assert_array_equal(actual,expected)
            self.assertLessEqual(sum(charges),int(common.sum()))
            rectangle_charges=[]
            cropped(attachment,vertices,alpha,rect,common,rectangle_charges.append)
            self.assertLessEqual(sum(charges),sum(rectangle_charges))

    def test_group_outside_common_does_not_charge_unrelated_pixels(self):
        charges=[]
        result=raster(dict(triangles=[0,1,2],uvs=[0,0,1,0,1,1]),
            [(50,50),(52,50),(50,52)],np.ones((2,2))*255,[0,0,10,10],
            np.ones((10,10),bool),charges.append)
        self.assertFalse(result.any());self.assertEqual(charges,[])

    def test_degenerate_and_empty_common_do_not_invent_coverage(self):
        attachment=dict(triangles=[0,1,2],uvs=[0,0,1,0,1,1])
        for common in (np.zeros((2,2),bool),np.ones((2,2),bool)):
            self.assertFalse(raster(attachment,[(0,0)]*3,np.ones((2,2))*255,
                                    [0,0,2,2],common,lambda _:None).any())

    def test_budget_refusal_precedes_sampling(self):
        def fail(_):raise ValueError('budget')
        with self.assertRaisesRegex(ValueError,'budget'):
            raster(dict(triangles=[0,1,2],uvs=[0,0,1,0,1,1]),[(0,0),(2,0),(0,-2)],
                   np.ones((2,2))*255,[0,0,2,2],np.ones((2,2),bool),fail)
