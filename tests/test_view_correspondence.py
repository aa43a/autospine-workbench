from copy import deepcopy
import unittest

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.view_correspondence import compile_mapping


class ViewCorrespondenceTests(unittest.TestCase):
    def setUp(self):
        self.mesh = dict(uvs=[0, 0, 1, 0, 0, 1, .25, .25], triangles=[0, 1, 3, 1, 2, 3, 2, 0, 3])
        self.request = dict(mesh_sha256=canonical_sha256(self.mesh), source_uv=[[0, 0], [1, 0], [0, 1]],
                            target_uv=[[.1, .2], [.9, .2], [.1, .8]],
                            target_xy=[[10, 20], [110, 20], [10, -180]], triangles=[[0, 1, 2]])

    def test_affine_mapping_and_parent_immutable(self):
        before = deepcopy(self.mesh)
        result = compile_mapping(self.mesh, self.request)
        self.assertEqual(result['points'][3], [35, -30])
        self.assertAlmostEqual(result['uvs'][6], .3)
        self.assertAlmostEqual(result['uvs'][7], .35)
        self.assertEqual(self.mesh, before)
        self.assertFalse(result['selected'])

    def test_uncovered_fold_and_stale_identity_rejected(self):
        for key, value, reason in [('mesh_sha256', 'x', 'mesh_changed'),
                                  ('source_uv', [[0, 0], [.5, 0], [0, .5]], 'uncovered'),
                                  ('target_uv', [[0, 0], [0, 1], [1, 0]], 'uv_fold')]:
            request = dict(self.request, **{key: value})
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                compile_mapping(self.mesh, request)

    def test_cross_cell_triangle_requires_subdivision(self):
        mesh = dict(uvs=[0, 0, 1, 0, 0, 1, 1, 1], triangles=[0, 1, 2, 1, 3, 2])
        request = dict(mesh_sha256=canonical_sha256(mesh), source_uv=[[0, 0], [1, 0], [0, 1], [1, 1]],
                       target_uv=[[0, 0], [1, 0], [0, 1], [1, 1]],
                       target_xy=[[0, 0], [1, 0], [0, -1], [1, -1]], triangles=[[0, 1, 3], [0, 3, 2]])
        with self.assertRaisesRegex(ValueError, 'requires_subdivision'):
            compile_mapping(mesh, request)

    def test_shared_control_edges_agree(self):
        mesh = dict(uvs=[0, 0, 1, 0, 0, 1, 1, 1], triangles=[0, 1, 2, 1, 3, 2])
        request = dict(mesh_sha256=canonical_sha256(mesh), source_uv=[[0, 0], [1, 0], [0, 1], [1, 1]],
                       target_uv=[[0, 0], [1, 0], [0, 1], [.8, .9]],
                       target_xy=[[0, 0], [100, 0], [0, -100], [80, -90]], triangles=[[0, 1, 2], [1, 3, 2]])
        result = compile_mapping(mesh, request)
        self.assertEqual(result['points'][3], [80, -90])
        self.assertEqual(result['uvs'][-2:], [.8, .9])

    def test_conflicting_overlapping_controls_rejected(self):
        request = deepcopy(self.request)
        request['source_uv'] *= 2
        request['target_uv'] *= 2
        request['target_xy'] += [[20, 20], [120, 20], [20, -180]]
        request['triangles'].append([3, 4, 5])
        with self.assertRaisesRegex(ValueError, 'ambiguous_overlap'):
            compile_mapping(self.mesh, request)


if __name__ == '__main__':
    unittest.main()
