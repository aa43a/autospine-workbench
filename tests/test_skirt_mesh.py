import copy
import math
import unittest

from autospine_workbench.asset.planning.skirt_mesh import build_skirt_mesh, SkirtMeshError


def contains(point, triangle):
    x, y = point
    signs = [(b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
             for a, b in zip(triangle, triangle[1:] + triangle[:1])]
    return min(signs) >= -1e-12


class SkirtMeshTests(unittest.TestCase):
    def assert_coverage(self, alpha, result):
        triangles = [[result['vertices'][i] for i in t] for t in result['triangles']]
        for y, row in enumerate(alpha):
            for x, value in enumerate(row):
                if value:
                    for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1), (.5, .5)]:
                        self.assertTrue(any(contains((x + dx, y + dy), t) for t in triangles), (x, y, dx, dy))
        self.assertEqual(result['coverage']['covered_alpha_pixels'], sum(v > 0 for row in alpha for v in row))

    def test_all_corners_partial_edges_and_fractional_waist(self):
        alpha = [[255] * 7 for _ in range(11)]
        result = build_skirt_mesh(alpha, 2.75, 4)
        self.assert_coverage(alpha, result)
        self.assertIn([7., 11.], result['vertices'])
        for (x, y), uv, weights in zip(result['vertices'], result['uvs'], result['influences']):
            self.assertEqual(uv, [x / 7, y / 11])
            self.assertEqual(sum(e['weight'] for e in weights), 1.)
            self.assertLessEqual(len(weights), 4)
            self.assertTrue(all(math.isfinite(e['weight']) and e['weight'] >= 0 for e in weights))
            self.assertTrue(all(e['bone'] == 'pelvis' or e['bone'].startswith('skirt_') for e in weights))
            if y <= 2.75:
                self.assertEqual(weights, [{'bone': 'pelvis', 'weight': 1.}])
            if y == 11:
                self.assertTrue(all(e['bone'].endswith('_lower') for e in weights))
        self.assertEqual([c['id'] for c in result['helper_chains']], ['skirt_0', 'skirt_1', 'skirt_2'])
        self.assertTrue(result['review_required'])

    def test_holes_and_disconnected_source_preserved(self):
        alpha = [[255] * 9 for _ in range(10)]
        for y in range(3, 7):
            for x in range(3, 6):
                alpha[y][x] = 0
        result = build_skirt_mesh(alpha, 1, 1)
        self.assert_coverage(alpha, result)
        area = sum(abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) / 2
                   for a, b, c in [[result['vertices'][i] for i in t] for t in result['triangles']])
        self.assertEqual(area, 78)
        self.assertFalse(any(contains((4.5, 4.5), [result['vertices'][i] for i in t]) for t in result['triangles']))
        alpha[8] = [0] * 9
        result = build_skirt_mesh(alpha, 1, 3)
        self.assert_coverage(alpha, result)
        self.assertEqual(result['coverage']['alpha_components'], 2)
        self.assertIn('disconnected_alpha', result['review_reasons'])

    def test_translation_determinism_and_no_mutation(self):
        alpha = [[255] * 8 for _ in range(10)]
        original = copy.deepcopy(alpha)
        a = build_skirt_mesh(alpha, 2.5, 3)
        self.assertEqual(a, build_skirt_mesh(tuple(tuple(r) for r in alpha), 2.5, 3))
        self.assertEqual(alpha, original)
        padded = [[0] * 12 for _ in range(14)]
        for y, row in enumerate(alpha):
            padded[y + 3][2:10] = row
        b = build_skirt_mesh(padded, 5.5, 3)
        self.assertEqual(b['vertices'], [[x + 2, y + 3] for x, y in a['vertices']])
        self.assertEqual(a['triangles'], b['triangles'])
        self.assertEqual(a['influences'], b['influences'])

    def test_smooth_transition_and_horizontal_neighbor_limit(self):
        result = build_skirt_mesh([[255] * 25 for _ in range(24)], 0, 1)
        for (x, y), weights in zip(result['vertices'], result['influences']):
            ids = {int(w['bone'].split('_')[1]) for w in weights if w['bone'] != 'pelvis'}
            self.assertLessEqual(len(ids), 2)
            if len(ids) == 2:
                self.assertEqual(max(ids) - min(ids), 1)
            if y == 6:
                self.assertEqual(next(w['weight'] for w in weights if w['bone'] == 'pelvis'), .5)
            if y == 12:
                self.assertTrue(all(w['bone'].endswith('_upper') for w in weights))

    def test_near_pixel_boundary_and_missing_root_support(self):
        alpha = [[255] * 5 for _ in range(7)]
        result = build_skirt_mesh(alpha, 1 - 1e-12, 3)
        self.assert_coverage(alpha, result)
        self.assertTrue(all(result['vertices'][t[2]][1] > result['vertices'][t[0]][1]
                            for t in result['triangles'][::2]))
        alpha = [[255, 255, 0, 0, 0, 255, 255] for _ in range(7)]
        result = build_skirt_mesh(alpha, 1, 3)
        self.assertIn('helper_root_over_alpha_gap', result['review_reasons'])
        self.assert_coverage(alpha, result)

    def test_rejections_are_structured(self):
        valid = [[255] * 5 for _ in range(6)]
        cases = [([], 0, 1, 'skirt_alpha_dimensions'),
                 ([[255], []], 0, 1, 'skirt_alpha_dimensions'),
                 ([[0] * 3], 0, 1, 'skirt_alpha_empty'),
                 ([[True] * 3], 0, 1, 'skirt_alpha_value'),
                 ([[256] * 3], 0, 1, 'skirt_alpha_value'),
                 ([[float('nan')] * 3], 0, 1, 'skirt_alpha_value'),
                 (valid, float('inf'), 1, 'skirt_waist_nonfinite'),
                 (valid, float('nan'), 1, 'skirt_waist_nonfinite'),
                 (valid, -1, 1, 'skirt_waist_outside_alpha'),
                 (valid, 6, 1, 'skirt_waist_outside_alpha'),
                 (valid, math.nextafter(6., 0.), 1, 'skirt_height_degenerate'),
                 (valid, 1, True, 'skirt_step_invalid'),
                 (valid, 1, 0, 'skirt_step_invalid'),
                 ([[255, 255]] * 6, 1, 1, 'skirt_waist_support_insufficient'),
                 ([[255] * 17000], 0, 1, 'skirt_resource_limit'),
                 ([[255] * 320] * 320, 1, 1, 'skirt_resource_limit')]
        for alpha, waist, step, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(SkirtMeshError) as caught:
                    build_skirt_mesh(alpha, waist, step)
                self.assertEqual(caught.exception.code, code)


if __name__ == '__main__':
    unittest.main()
