import unittest
import numpy as np
from m4_clip_groups import group
from m4_halfplane_clips import rectangles, contains


class ClipGroupsTests(unittest.TestCase):
    def test_adjacent_same_plane_and_full_support(self):
        points = np.array([[[0, 0], [10, 0], [0, 10], [10, 10]]]*2)
        values = points[:, :, 0]-5
        triangles = [[0, 1, 2], [1, 3, 2]]
        self.assertEqual(group(points, values, triangles, [0, 1]), [[0, 1]])
        q = rectangles(points[0, :3], values[0, :3], support=points[0])
        np.testing.assert_array_equal(contains(q['front'], points[0]), [False, True, False, True])

    def test_spatial_error_budget_and_low_gradient(self):
        p = np.array([[[0, 0], [10, 0], [0, 10], [10, 10]]]*2)
        v = p[:, :, 0].astype(float)-5;v[:, 3] += .001
        t = [[0, 1, 2], [1, 3, 2]]
        self.assertEqual(group(p, v, t, [0, 1], pixel_tolerance=.01), [[0, 1]])
        v[:, 3] += 10
        self.assertEqual(group(p, v, t, [0, 1], pixel_tolerance=.01), [[0], [1]])
        # Scaling depth units must not change a screen-space error decision.
        self.assertEqual(group(p, v*1e-5, t, [0, 1], pixel_tolerance=.01), [[0], [1]])

    def test_disconnected_triangles_are_not_merged(self):
        p = np.array([[[0, 0], [1, 0], [0, 1], [2, 0], [3, 0], [2, 1]]])
        self.assertEqual(group(p, p[:, :, 0]-.5, [[0, 1, 2], [3, 4, 5]], [0, 1]), [[0], [1]])
