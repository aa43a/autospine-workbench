import unittest
import numpy as np
from m4_overlap_material_trace import coverage


class OverlapTraceTests(unittest.TestCase):
    def test_material_can_leave_cover_without_leaving_reference_mesh(self):
        mesh=dict(uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3])
        vertices=[[0,0],[4,0],[4,4],[0,4]]
        alpha=np.tile([255,255,0,0],(4,1))
        points=np.array([[.5,.5],[1.5,.5],[2.5,.5],[3.5,.5],[5,.5]])
        values,hits=coverage(vertices,mesh,alpha,points)
        self.assertEqual(values.tolist(),[255,255,0,0,0])
        self.assertEqual(hits.tolist(),[True,True,True,True,False])
        moved=np.asarray(vertices)+[2,0]
        shifted,covered=coverage(moved,mesh,alpha,points)
        self.assertEqual(shifted.tolist(),[0,0,255,255,0])
        self.assertEqual(covered.tolist(),[False,False,True,True,True])

    def test_transparent_hole_and_partial_alpha_are_not_fixed_connection_errors(self):
        mesh=dict(uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3])
        vertices=[[0,0],[3,0],[3,3],[0,3]]
        alpha=np.array([[255,255,255],[255,0,128],[255,255,255]])
        values,hits=coverage(vertices,mesh,alpha,[[1.5,1.5],[2.5,1.5]])
        self.assertTrue(hits.all())
        self.assertEqual(values.tolist(),[0,128])
        self.assertEqual(alpha[1].tolist(),[255,0,128])
