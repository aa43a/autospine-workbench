import unittest
import numpy as np
from autospine_workbench.targets.character43.material_reachability import inspect


class MaterialReachabilityTests(unittest.TestCase):
    def setUp(self):
        self.mesh=dict(uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3])
        self.points=[[0,0],[10,0],[10,10],[0,10]]
        self.alpha=np.full((10,10),255.)

    def test_exact_solid_support_bound_and_witness(self):
        r=inspect(self.mesh,self.points,self.alpha,[15,5],budget=3)
        self.assertEqual(r['status'],'outside_vertex_budget')
        self.assertAlmostEqual(r['conservative_distance_lower_bound_px'],5)
        r=inspect(self.mesh,self.points,self.alpha,[12,5],budget=3)
        self.assertEqual(r['status'],'material_witness_within_budget')
        self.assertAlmostEqual(r['witness']['distance_px'],2)

    def test_transparent_texture_has_no_support(self):
        r=inspect(self.mesh,self.points,np.zeros((10,10)),[5,5],budget=3)
        self.assertEqual(r['status'],'outside_vertex_budget')
        self.assertIsNone(r['witness'])

    def test_bilinear_transition_not_nearest_texel(self):
        alpha=np.zeros((10,10));alpha[:,5:]=255
        r=inspect(self.mesh,self.points,alpha,[4,5],budget=1,threshold=128)
        self.assertEqual(r['status'],'not_ruled_out')
        self.assertGreater(r['witness']['distance_px'],1)
        self.assertLess(r['conservative_distance_lower_bound_px'],1)
        r=inspect(self.mesh,self.points,alpha,[4,5],budget=1,threshold=8)
        self.assertEqual(r['status'],'material_witness_within_budget')

    def test_degenerate_and_invalid_are_not_certified(self):
        r=inspect(self.mesh,[[0,0]]*4,self.alpha,[0,0])
        self.assertEqual(r['status'],'unmeasured_degenerate_triangles')
        self.assertIsNone(r['conservative_distance_lower_bound_px'])
        with self.assertRaises(ValueError):inspect(self.mesh,self.points,self.alpha,[0,0],threshold=0)
