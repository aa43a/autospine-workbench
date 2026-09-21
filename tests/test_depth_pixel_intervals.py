import unittest
import numpy as np
from autospine_workbench.targets.spine43.seam_raster import mask
from autospine_workbench.targets.character43.depth_pixel_intervals import classify


class PixelDepthTests(unittest.TestCase):
    def setUp(self):
        self.mesh=dict(uvs=[.5,.5]*3,triangles=[0,1,2])
        self.points=[(0,0),(4,0),(0,-4)]
        self.alpha=np.full((2,2),255.)
        self.rect=[0,0,4,4]
        self.common=mask(self.mesh,self.points,self.alpha,self.rect)>=8

    def test_linear_gradient_resolves_only_pixels_clearing_margin(self):
        charges=[]
        counts=classify(self.mesh,self.points,self.alpha,self.rect,self.common,
                        [[0,0],[.4,.4],[0,0]],.1,charges.append)
        self.assertEqual(counts,dict(front=6,back=0,ambiguous=4,unknown=0))
        self.assertEqual(sum(charges),32)
        wide=classify(self.mesh,self.points,self.alpha,self.rect,self.common,
                     [[-.2,.2],[.2,.6],[-.2,.2]],.1,lambda n:None)
        self.assertGreater(wide['ambiguous'],counts['ambiguous'])

    def test_unknown_and_overlapping_opposite_triangles_are_not_adopted(self):
        unknown=classify(self.mesh,self.points,self.alpha,self.rect,self.common,
                        [None,[1,1],[1,1]],.1,lambda n:None)
        self.assertEqual(unknown['unknown'],int(self.common.sum()))
        mesh=dict(uvs=self.mesh['uvs']*2,triangles=[0,1,2,3,4,5])
        counts=classify(mesh,self.points*2,self.alpha,self.rect,self.common,
                        [[1,1]]*3+[[-1,-1]]*3,.1,lambda n:None)
        self.assertEqual(counts['ambiguous'],int(self.common.sum()))
        self.assertEqual(counts['front']+counts['back'],0)

    def test_budget_failure_is_propagated(self):
        def charge(n):raise ValueError('budget')
        with self.assertRaisesRegex(ValueError,'budget'):
            classify(self.mesh,self.points,self.alpha,self.rect,self.common,[[1,1]]*3,.1,charge)


if __name__=='__main__':unittest.main()
