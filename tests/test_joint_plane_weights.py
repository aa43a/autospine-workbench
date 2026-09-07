"""Joint-plane partitioning, rigid endpoints and geometric equivariance."""
from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.joint_plane_weights import weights_for_vertices
from autospine_workbench.asset.joints.mesh_weights import evaluate_mesh


def chain():
    return [{'id': name, 'parent_id': parent, 'head_xy': [x, 0.], 'tail_xy': [x+10., 0.],
             'world_rotation_degrees': 0.} for name, parent, x in
            (('upperarm', 'clavicle', 0.), ('forearm', 'upperarm', 10.), ('hand', 'forearm', 20.))]


def transform(point, angle, offset):
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return [point[0]*cosine-point[1]*sine+offset[0], point[0]*sine+point[1]*cosine+offset[1]]


class JointPlaneWeightsTests(unittest.TestCase):
    def setUp(self):
        self.bones = chain()
        self.vertices = [[0., 2.], [10., 2.], [15., 2.], [20., 2.], [30., 2.]]

    def test_rigid_ends_center_and_smooth_transition(self):
        rows = weights_for_vertices(self.vertices, self.bones)
        self.assertEqual([v['weight'] for v in rows[0]], [1., 0., 0.])
        self.assertEqual([v['weight'] for v in rows[1]], [.5, .5, 0.])
        self.assertEqual([v['weight'] for v in rows[2]], [0., 1., 0.])
        self.assertEqual([v['weight'] for v in rows[3]], [0., .5, .5])
        self.assertEqual([v['weight'] for v in rows[4]], [0., 0., 1.])

    def test_normalization_nonnegative_and_pure_deterministic(self):
        before = deepcopy((self.vertices, self.bones))
        result = weights_for_vertices(self.vertices, self.bones)
        self.assertEqual(result, weights_for_vertices(self.vertices, self.bones))
        self.assertEqual((self.vertices, self.bones), before)
        for row in result:
            self.assertEqual(len(row), 3)
            self.assertAlmostEqual(sum(v['weight'] for v in row), 1.)
            self.assertTrue(all(0 <= v['weight'] <= 1 for v in row))

    def test_setup_fk_lbs_reconstruction(self):
        vertices = [[1., 1.], [3., 1.], [1., 3.]]
        qa = evaluate_mesh(vertices, [[0, 1, 2]], weights_for_vertices(vertices, self.bones), self.bones)
        self.assertTrue(qa['passed'])
        self.assertLessEqual(qa['setup_max_error'], 1e-7)
        self.assertLessEqual(qa['weight_sum_max_error'], 1e-9)

    def test_rotation_translation_equivariance(self):
        original = weights_for_vertices(self.vertices, self.bones)
        angle, offset = 63.25, [131., 91.]
        moved_bones = deepcopy(self.bones)
        for bone in moved_bones:
            bone['head_xy'] = transform(bone['head_xy'], angle, offset)
            bone['tail_xy'] = transform(bone['tail_xy'], angle, offset)
            bone['world_rotation_degrees'] += angle
        moved = weights_for_vertices([transform(v, angle, offset) for v in self.vertices], moved_bones)
        for old, new in zip(original, moved):
            for a, b in zip(old, new):
                self.assertEqual(a['bone_id'], b['bone_id'])
                self.assertAlmostEqual(a['weight'], b['weight'], places=12)
                for x, y in zip(a['local_xy'], b['local_xy']):
                    self.assertAlmostEqual(x, y, places=12)

    def test_bent_chain_uses_bisector_normal(self):
        self.bones[1].update(tail_xy=[10., 10.], world_rotation_degrees=90.)
        self.bones[2].update(head_xy=[10., 10.], tail_xy=[10., 20.], world_rotation_degrees=90.)
        rows = weights_for_vertices([[10., 0.], [11., -1.], [9., 1.]], self.bones)
        for row in rows:
            self.assertAlmostEqual(row[0]['weight'], .5)
            self.assertAlmostEqual(sum(v['weight'] for v in row), 1.)

    def test_reversed_tiny_and_disconnected_fail(self):
        reverse = chain()
        reverse[1]['tail_xy'] = [0., 0.]
        reverse[2].update(head_xy=[0., 0.], tail_xy=[-10., 0.])
        with self.assertRaisesRegex(ValueError, 'joint_plane_degenerate'):
            weights_for_vertices(self.vertices, reverse)
        tiny = chain()
        tiny[0]['tail_xy'] = [5e-7, 0.]
        with self.assertRaisesRegex(ValueError, 'joint_plane_degenerate'):
            weights_for_vertices(self.vertices, tiny)
        disconnected = chain()
        disconnected[1]['head_xy'][1] = .01
        with self.assertRaisesRegex(ValueError, 'joint_plane_disconnected'):
            weights_for_vertices(self.vertices, disconnected)

    def test_shared_input_guards_nonfinite_and_wrong_chain(self):
        with self.assertRaises(ValueError):
            weights_for_vertices([[float('nan'), 0.], [1., 0.], [0., 1.]], self.bones)
        self.bones[2]['parent_id'] = 'unrelated'
        with self.assertRaises(ValueError):
            weights_for_vertices(self.vertices, self.bones)


if __name__ == '__main__':
    unittest.main()
