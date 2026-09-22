import unittest
import numpy as np
from m4_halfplane_clips import rectangles, contains


class HalfplaneTests(unittest.TestCase):
    def test_linear_classification_and_complement(self):
        random = np.random.default_rng(52)
        for points in ([[0, 0], [30, 0], [0, 20]], [[0, 0], [0, 20], [30, 0]]):
            for values in ([1, 2, -3], [-1, -2, 3], [2, 2, 2], [-2, -2, -2], [0, 0, 0]):
                clips = rectangles(points, values)
                barycentric = random.dirichlet([1, 1, 1], 300)
                probes = barycentric @ np.asarray(points)
                field = barycentric @ np.asarray(values)
                front = contains(clips['front'], probes)
                back = contains(clips['back'], probes)
                self.assertTrue(np.all(front | back))
                np.testing.assert_array_equal(front, field >= -1e-8)
                if np.any(field):
                    np.testing.assert_array_equal(back, field <= 1e-8)
                for quad in clips.values():
                    self.assertGreater(abs(np.linalg.det(np.asarray(quad)[[1, 3]] - quad[0])), 0)

    def test_invalid_geometry(self):
        for points, values in [([[0, 0]] * 3, [1, 2, 3]),
                               ([[0, 0], [1, 0], [0, 1]], [1, float('nan'), 3])]:
            with self.assertRaises(ValueError):
                rectangles(points, values)

    def test_guard_is_bounded_and_only_expands_shared_boundary(self):
        points = [[0, 0], [10, 0], [0, 10]]
        q = rectangles(points, [-5, 5, -5], boundary_guard=.001)
        probes = [[4.9995, 2], [5.0005, 2]]
        self.assertTrue(contains(q['front'], probes).all())
        self.assertTrue(contains(q['back'], probes).all())
        for guard in (-1, .002, float('nan')):
            with self.assertRaises(ValueError): rectangles(points, [-5, 5, -5], boundary_guard=guard)


if __name__ == '__main__':
    unittest.main()
