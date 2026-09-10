import unittest

from autospine_workbench.targets.spine43.sleeve_overlap import intersection_area, overlaps, analyze, peak_visibility


class SleeveOverlapTests(unittest.TestCase):
    def test_clipping_and_winding(self):
        a = [[0, 0], [2, 0], [0, 2]]
        b = [[1, 0], [3, 0], [1, 2]]
        self.assertAlmostEqual(intersection_area(a, b), .5)
        self.assertAlmostEqual(intersection_area(a[::-1], b[::-1]), .5)
        self.assertAlmostEqual(intersection_area(a, a), 2)

    def test_shared_diagonal_is_not_overlap(self):
        self.assertEqual(overlaps([[0, 1, 2], [1, 3, 2]], [[0, 0], [2, 0], [0, 2], [2, 2]]), {})

    def test_new_pair_not_hidden_by_other_setup_overlap(self):
        triangles = [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
        setup = [[0, 0], [2, 0], [0, 2]]*2 + [[4, 0], [6, 0], [4, 2]]
        moved = setup[:3]+setup[6:]+setup[:3]
        report = analyze(triangles, setup, {'test': [dict(time=1, points=moved)]})
        self.assertEqual(report['tracks'][0]['peak']['triangles'], [0, 2])
        self.assertEqual(report['tracks'][0]['peak']['excess_area_px2'], 2)
        self.assertEqual(report['framebuffer_status'], 'not_evaluated')

    def test_similarity_covariance(self):
        a = [[0, 0], [2, 0], [0, 2]]
        b = [[1, 0], [3, 0], [1, 2]]
        transform = lambda t: [[10000-3*y, 20000+3*x] for x, y in t]
        self.assertAlmostEqual(intersection_area(transform(a), transform(b)), 4.5)

    def test_nonfinite_rejected(self):
        with self.assertRaisesRegex(ValueError, 'geometry'):
            overlaps([[0, 1, 2]], [[0, 0], [1, 0], [0, float('nan')]])

    def test_peak_transparent_texture_is_not_visible_overlap(self):
        import numpy as np
        points = [[0, 0], [4, 0], [0, -4]]*2
        attachment = dict(triangles=[0, 1, 2, 3, 4, 5], uvs=[0, 0, .4, 0, 0, .4, .6, .6, 1, .6, .6, 1])
        alpha = np.full((10, 10), 255.)
        self.assertGreater(peak_visibility(attachment, points, alpha, [0, 1])['dual_alpha8_pixels'], 0)
        alpha[5:, 5:] = 0
        self.assertEqual(peak_visibility(attachment, points, alpha, [0, 1])['dual_alpha8_pixels'], 0)

    def test_smaller_visible_pair_not_hidden_by_larger_transparent_pair(self):
        import numpy as np
        triangles = [[i, i+1, i+2] for i in (0, 3, 6, 9)]
        tri = lambda x: [[x, 0], [x+4, 0], [x, -4]]
        setup = tri(0)+tri(10)+tri(100)+tri(110)
        moved = tri(0)+tri(0)+tri(100)+tri(102)
        attachment = dict(triangles=sum(triangles, []), uvs=[0, 0, .2, 0, 0, .2]*2+[.7, .7, .9, .7, .7, .9]*2)
        alpha = np.zeros((20, 20)); alpha[12:, 12:] = 255
        report = analyze(triangles, setup, {'test': [dict(time=1, points=moved)]}, attachment, alpha)
        track = report['tracks'][0]
        self.assertEqual(track['peak']['triangles'], [0, 1])
        self.assertEqual(track['visible_peak']['triangles'], [2, 3])
        self.assertGreater(track['visible_peak']['excess_pair_pixels'], 0)
