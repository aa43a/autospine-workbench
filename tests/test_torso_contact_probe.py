import unittest
import numpy as np
from m4_torso_contact_probe import subdivide
from m4_pose_material_review import transfer


class TorsoSubdivisionTests(unittest.TestCase):
    def test_shared_edges_use_one_midpoint_and_preserve_area(self):
        points = [[0, 0], [2, 0], [2, 3], [0, 3]]
        tris = [[0, 1, 2], [0, 2, 3]]
        refined, faces = subdivide(points, tris)
        self.assertEqual(len(refined), 9)
        self.assertEqual(len(faces), 8)
        self.assertEqual(refined.count([1., 1.5]), 1)
        areas = []
        for a, b, c in faces:
            u, v = np.asarray(refined[b])-refined[a], np.asarray(refined[c])-refined[a]
            areas.append(float(u[0]*v[1]-u[1]*v[0])/2)
        self.assertTrue(all(a>0 for a in areas))
        self.assertAlmostEqual(sum(areas), 6)
        self.assertEqual(points, [[0, 0], [2, 0], [2, 3], [0, 3]])

    def test_subdivision_retains_original_piecewise_affine_mapping(self):
        source = [[0, 0], [2, 0], [2, 3], [0, 3]]
        deformed = [[1, 0], [3, 1], [4, 4], [-1, 3]]
        triangles = [[0, 1, 2], [0, 2, 3]]
        points, faces = subdivide(source, triangles)
        flat = [v for t in triangles for v in t]
        mapped, ok = transfer(source, deformed, flat, points)
        queries = np.asarray([[.2, .2], [.8, 1.2], [1.8, 2.9], [.1, 2.8]])
        expected, support = transfer(source, deformed, flat, queries)
        actual, refined_support = transfer(points, mapped, [v for t in faces for v in t], queries)
        self.assertTrue(ok.all() and support.all() and refined_support.all())
        np.testing.assert_allclose(expected, actual, atol=1e-12)
