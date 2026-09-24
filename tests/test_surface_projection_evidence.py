import math
import unittest
import numpy as np
from autospine_workbench.targets.character43.surface_projection_evidence import inspect


class SurfaceProjectionTests(unittest.TestCase):
    def setUp(self):
        self.points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float)

    def row(self, target):
        return inspect(self.points, target, [[0, 1, 2]], np.eye(3))['triangles'][0]

    def test_rigid_turn_compresses_projection_without_material_strain(self):
        angle = math.radians(80)
        rotation = np.array([[1, 0, 0], [0, math.cos(angle), -math.sin(angle)], [0, math.sin(angle), math.cos(angle)]])
        row = self.row(self.points@rotation.T)
        self.assertAlmostEqual(row['intrinsic_area_ratio'], 1)
        self.assertAlmostEqual(row['maximum_intrinsic_edge_stretch'], 1)
        self.assertAlmostEqual(row['projected_signed_area_ratio'], math.cos(angle))
        self.assertTrue(row['projected_area_failure_with_intrinsic_pass'])
        self.assertFalse(row['accepted'])

    def test_real_compression_is_not_reclassified(self):
        row = self.row(self.points*[1, .2, 1])
        self.assertFalse(row['intrinsic_gate_passed'])
        self.assertFalse(row['projected_area_failure_with_intrinsic_pass'])

    def test_back_face_and_edge_on_stay_unaccepted(self):
        row = self.row(self.points*[1, -1, -1])
        self.assertTrue(row['intrinsic_gate_passed'])
        self.assertEqual(row['surface_orientation'], 'back')
        self.assertTrue(row['projected_winding_changed'])
        self.assertFalse(row['accepted'])
        target = self.points[:, [0, 2, 1]]
        self.assertEqual(self.row(target)['surface_orientation'], 'edge_on')

    def test_rejects_camera_scale_and_degenerate_surface(self):
        with self.assertRaises(ValueError):
            inspect(self.points, self.points, [[0, 1, 2]], np.eye(3)*2)
        self.assertEqual(self.row(np.zeros((3, 3)))['status'], 'degenerate_surface')
