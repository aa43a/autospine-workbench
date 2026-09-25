import unittest
import numpy as np
from autospine_workbench.targets.character43.occlusion_scope_alpha import inspect


class OcclusionAlphaTests(unittest.TestCase):
    def check(self,alpha,reference=None,other=None):
        p=[[0,0],[3,0],[0,3]];uv=[[0,0],[1,0],[0,1]]
        return inspect(p,uv,[0,1,2],[0],reference or p,uv,other or [0,1,2],
                       np.full((3,3),255),alpha)

    def test_opaque_hole_partial_and_outside_are_distinct(self):
        for value,label in [(255,'opaque_reference'),(128,'partial_reference'),(0,'exposed')]:
            alpha=np.full((3,3),255);alpha[1,1]=value
            r=self.check(alpha)
            self.assertEqual(r['records'][0]['classification'],label)
            self.assertTrue(r['records'][0]['reference_mesh_covered'])
            self.assertEqual(r['visual_status'],'not_checked')
        r=self.check(np.full((3,3),255),[[10,10],[13,10],[10,13]])
        self.assertEqual(r['records'][0]['classification'],'exposed')
        self.assertFalse(r['records'][0]['reference_mesh_covered'])

    def test_overlapping_reference_uv_not_arbitrarily_chosen(self):
        p=[[0,0],[3,0],[0,3]];uv=[[0,0],[1,0],[0,1]]
        r=inspect(p,uv,[0,1,2],[0],p+p,uv+[[1,1],[0,1],[1,0]],
                  [0,1,2,3,4,5],np.full((3,3),255),np.full((3,3),255))
        self.assertEqual(r['records'][0]['classification'],'reference_mapping_ambiguous')
        self.assertIsNone(r['records'][0]['reference_alpha'])

    def test_degenerate_source_not_claimed_visible(self):
        r=inspect([[0,0],[1,0],[2,0]],[[0,0],[1,0],[0,1]],[0,1,2],[0],
                  [[0,0],[3,0],[0,3]],[[0,0],[1,0],[0,1]],[0,1,2],
                  np.full((3,3),255),np.full((3,3),255))
        self.assertEqual(r['records'][0]['classification'],'degenerate_source')
