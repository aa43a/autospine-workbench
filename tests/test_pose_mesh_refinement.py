from copy import deepcopy
import unittest

from test_pose_geometry_patch import fixture
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.pose_mesh_refinement import refine
from autospine_workbench.targets.character43.pose_geometry_patch import compile_patch


class PoseMeshRefinementTests(unittest.TestCase):
    def test_surface_and_uv_preserved_through_weighted_deform(self):
        doc, _ = fixture()
        # Different moving bone transforms make naive averaging of local
        # coordinates or weights observably wrong.
        doc['animations']['move']['bones']['child'] = dict(rotate=[
            dict(time=0, value=0), dict(time=1, value=75), dict(time=2, value=-20)])
        original = deepcopy(doc)
        changed, report = refine(doc, 'leg', [1, 0], canonical_sha256(doc))
        self.assertEqual(doc, original)
        mesh = changed['skins'][0]['attachments']['leg']['leg']
        self.assertEqual(mesh['uvs'][8:], [2/3, 1/3, 1/3, 2/3])
        self.assertEqual(report['triangle_sources'], [0, 0, 0, 1, 1, 1])
        for time in (0, .13, .51, 1, 1.37, 2):
            before = sample(doc, 'move', time)[0]
            after = sample(changed, 'move', time)[0]
            self.assertEqual(before['other'], after['other'])
            self.assertEqual(before['leg'], after['leg'][:4])
            for i, source in enumerate(report['added_vertex_sources']):
                for axis in (0, 1):
                    self.assertAlmostEqual(after['leg'][4+i][axis],
                        sum(before['leg'][v][axis] for v in source)/3, places=10)
        self.assertFalse(report['repair_claim'])

    def test_sparse_and_empty_deform_expansion(self):
        doc, _ = fixture()
        keys = doc['animations']['move']['attachments']['default']['leg']['leg']['deform']
        keys[0] = dict(time=0)
        keys[1] = dict(time=1, offset=9, vertices=[-4, 0, -4])
        changed, _ = refine(doc, 'leg', [0], canonical_sha256(doc))
        keys = changed['animations']['move']['attachments']['default']['leg']['leg']['deform']
        self.assertEqual(len(keys[0]['vertices']), 28)
        self.assertEqual(keys[1]['vertices'][16:], [0, 0, 0, 0, 0, 0, 0, 0, 0, -4, 0, -4])

    def test_new_control_can_be_authored_without_moving_boundary(self):
        doc, _ = fixture()
        doc['animations']['move'].pop('attachments')
        refined, _ = refine(doc, 'leg', [0], canonical_sha256(doc))
        point = sample(refined, 'move', 1)[0]['leg'][4]
        desired = [point[0], point[1]+.1]
        request = dict(document_sha256=canonical_sha256(refined),
            mesh_sha256=canonical_sha256(refined['skins'][0]['attachments']['leg']['leg']),
            animation='move', slot='leg', vertices=[4], interval=[0, 2],
            poses=[dict(time=1, points=[desired])])
        patched, report = compile_patch(refined, request)
        self.assertLess(report['authored_point_error_px'], 1e-10)
        for t in (0, .37, 1, 1.71, 2):
            self.assertEqual(sample(doc, 'move', t)[0]['leg'],
                             sample(patched, 'move', t)[0]['leg'][:4])

    def test_rejects_stale_unsupported_and_bad_selection(self):
        doc, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'document_changed'):
            refine(doc, 'leg', [0], 'old')
        for selection in ([], [0, 0], [-1], [True], [2]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                refine(doc, 'leg', selection, canonical_sha256(doc))
        doc['animations']['move']['attachments']['default']['leg']['leg']['deform'][0]['curve'] = 'stepped'
        with self.assertRaisesRegex(ValueError, 'linear_deform'):
            refine(doc, 'leg', [0], canonical_sha256(doc))
