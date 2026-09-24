import unittest
import numpy as np
from autospine_workbench.targets.character43.closed_surface_shell import build


class ShellTests(unittest.TestCase):
    def test_closed_orientation_and_unchanged_front(self):
        points=[[0,0,0],[2,0,0],[2,3,0],[0,3,0]]
        for triangles in ([[0,1,2],[0,2,3]],[[2,1,0],[3,2,0]]):
            r=build(points,triangles,4)
            np.testing.assert_array_equal(r['vertices'][:4],points)
            p=np.array(r['vertices']);t=np.array(r['triangles'])
            volume=np.einsum('ij,ij->i',p[t[:,0]],np.cross(p[t[:,1]],p[t[:,2]])).sum()/6
            self.assertAlmostEqual(volume,24)
            self.assertEqual(r['material_roles'].count('original_front'),2)
            self.assertEqual(r['material_roles'].count('missing_side_material'),8)
            self.assertTrue(r['closed_oriented_edges']);self.assertFalse(r['accepted'])

    def test_inconsistent_or_degenerate_front_rejected(self):
        p=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]]
        for t in ([[0,1,2],[0,3,2]],[[0,1,1]]):
            with self.assertRaises(ValueError):build(p,t,1)
