"""Setup identity, inherited chain transforms and conservative deformation QA."""
from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.mesh_weights import weights_for_vertices, evaluate_mesh


def chain():
    return [{'id': name, 'parent_id': parent, 'head_xy': [x, 0], 'tail_xy': [x+10, 0],
             'world_rotation_degrees': 0} for name, parent, x in
            (('upperarm', 'clavicle', 0), ('forearm', 'upperarm', 10), ('hand', 'forearm', 20))]


class MeshWeightsTests(unittest.TestCase):
    def setUp(self):
        self.bones = chain()
        self.vertices = [[1, 1], [9, 1], [9, 3], [1, 3]]
        self.triangles = [[0, 1, 2], [0, 2, 3]]

    def test_smooth_three_bone_weights_normalize_and_setup_is_exact(self):
        weights = weights_for_vertices(self.vertices, self.bones)
        for row in weights:
            self.assertEqual(len(row), 3)
            self.assertAlmostEqual(sum(v['weight'] for v in row), 1)
            self.assertTrue(all(v['weight'] > 0 for v in row))
        result = evaluate_mesh(self.vertices, self.triangles, weights, self.bones)
        self.assertLess(result['setup_max_error'], 1e-12)
        self.assertLess(result['weight_sum_max_error'], 1e-12)
        self.assertEqual(len(result['probes']), 7)

    def test_vertex_on_bone_has_finite_epsilon_regularized_weights(self):
        vertices = [[0, 0], [10, 0], [20, 0]]
        weights = weights_for_vertices(vertices, self.bones)
        self.assertTrue(all(math.isfinite(v['weight']) for row in weights for v in row))
        self.assertAlmostEqual(weights[1][0]['weight'], weights[1][1]['weight'])

    def test_third_bone_head_inherits_second_bone_rotation(self):
        vertices = [[19, 0], [21, 0], [20, 2]]
        weights = [[{'bone_id': 'forearm', 'weight': 1., 'local_xy': [9., 0.]}],
                   [{'bone_id': 'hand', 'weight': 1., 'local_xy': [1., 0.]}],
                   [{'bone_id': 'hand', 'weight': 1., 'local_xy': [0., 2.]}]]
        result = evaluate_mesh(vertices, [[0, 1, 2]], weights, self.bones)
        self.assertTrue(result['passed'])
        for probe in result['probes']:
            self.assertAlmostEqual(probe['max_edge_stretch'], 1.)
            self.assertEqual(probe['inverted_triangle_count'], 0)

    def test_arbitrary_world_rotations_round_trip(self):
        for bone in self.bones:
            bone['world_rotation_degrees'] = 73.25
        weights = weights_for_vertices(self.vertices, self.bones)
        result = evaluate_mesh(self.vertices, self.triangles, weights, self.bones)
        self.assertLess(result['setup_max_error'], 1e-12)

    def test_bad_sums_and_local_positions_fail_setup_qa(self):
        weights = weights_for_vertices(self.vertices, self.bones)
        weights[0][0]['weight'] *= .5
        result = evaluate_mesh(self.vertices, self.triangles, weights, self.bones)
        self.assertFalse(result['passed'])
        self.assertGreater(result['weight_sum_max_error'], 1e-9)
        weights = weights_for_vertices(self.vertices, self.bones)
        weights[0][0]['local_xy'][0] += 1
        self.assertFalse(evaluate_mesh(self.vertices, self.triangles, weights, self.bones)['passed'])

    def test_inversions_are_detected_relative_to_either_setup_winding(self):
        vertices = [[9, 0], [11, 0], [10, 1]]
        weights = [[{'bone_id': 'upperarm', 'weight': 1., 'local_xy': [9., 0.]}],
                   [{'bone_id': 'forearm', 'weight': 1., 'local_xy': [1., 0.]}],
                   [{'bone_id': 'upperarm', 'weight': 1., 'local_xy': [10., 1.]}]]
        for triangles in ([[0, 1, 2]], [[2, 1, 0]]):
            result = evaluate_mesh(vertices, triangles, weights, self.bones)
            self.assertFalse(result['passed'])
            self.assertTrue(any(p['inverted_triangle_count'] for p in result['probes']))

    def test_inputs_immutable_and_output_deterministic(self):
        before = deepcopy((self.vertices, self.triangles, self.bones))
        weights = weights_for_vertices(self.vertices, self.bones)
        copied = deepcopy(weights)
        report = evaluate_mesh(self.vertices, self.triangles, weights, self.bones)
        self.assertEqual(report, evaluate_mesh(self.vertices, self.triangles, weights, self.bones))
        self.assertEqual(weights, copied)
        self.assertEqual((self.vertices, self.triangles, self.bones), before)

    def test_nonfinite_unknown_bones_bad_topology_and_limits_fail(self):
        for point in ([True, 0], [math.nan, 0], [10**1000, 0]):
            with self.assertRaises(ValueError):
                weights_for_vertices([point, [1, 0], [0, 1]], self.bones)
        with self.assertRaises(ValueError):
            weights_for_vertices([[0, 0]] * 4097, self.bones)
        bad = deepcopy(self.bones)
        bad[2]['parent_id'] = 'other'
        with self.assertRaises(ValueError):
            weights_for_vertices(self.vertices, bad)
        weights = weights_for_vertices(self.vertices, self.bones)
        for triangles in ([[0, 0, 1]], [[0, 1, 99]], [[True, 1, 2]]):
            with self.assertRaises(ValueError):
                evaluate_mesh(self.vertices, triangles, weights, self.bones)
        weights[0][0]['bone_id'] = 'other'
        with self.assertRaises(ValueError):
            evaluate_mesh(self.vertices, self.triangles, weights, self.bones)


if __name__ == '__main__':
    unittest.main()
