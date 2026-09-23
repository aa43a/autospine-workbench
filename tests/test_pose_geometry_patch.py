from copy import deepcopy
import math
import unittest

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.pose_geometry_patch import compile_patch


def fixture():
    points = [[0, 0], [2, 0], [2, 2], [0, 2]]
    mesh = dict(type='mesh', uvs=[0, 0, 1, 0, 1, 1, 0, 1], triangles=[0, 1, 2, 0, 2, 3],
                vertices=[v for x, y in points for v in (2, 0, x, y, .4, 1, x, y, .6)])
    zero = [0.]*16
    folded = zero[:]
    folded[9] = folded[11] = -4
    doc = dict(bones=[dict(name='root', x=0, y=0, rotation=0),
                      dict(name='child', parent='root', x=0, y=0, rotation=0)],
               skins=[dict(attachments={'leg': {'leg': mesh}, 'other': {'other': deepcopy(mesh)}})],
               animations={'move': dict(bones={'root': dict(scale=[dict(time=0, x=1, y=1),
                    dict(time=1, x=.7, y=1.2), dict(time=2, x=1, y=1)])}, attachments={'default': {
                    'leg': {'leg': dict(deform=[dict(time=0, vertices=zero), dict(time=1, vertices=folded),
                                               dict(time=2, vertices=zero)])}}})})
    clean = deepcopy(doc)
    clean['animations']['move'].pop('attachments')
    desired = sample(clean, 'move', 1)[0]['leg'][2]
    request = dict(document_sha256=canonical_sha256(doc), mesh_sha256=canonical_sha256(mesh),
                   animation='move', slot='leg', vertices=[2], interval=[0, 2],
                   poses=[dict(time=1, points=[desired])])
    return doc, request


class PoseGeometryPatchTests(unittest.TestCase):
    def test_repairs_explicit_pose_with_weighted_scaled_parent(self):
        doc, request = fixture()
        original = deepcopy(doc)
        changed, report = compile_patch(doc, request)
        self.assertEqual(doc, original)
        self.assertEqual(changed['bones'], original['bones'])
        self.assertEqual(changed['skins'], original['skins'])
        self.assertEqual(changed['animations']['move']['bones'], original['animations']['move']['bones'])
        self.assertTrue(report['sampled_geometry_passed'])
        self.assertGreater(next(r for r in report['records'] if r['time'] == 1)['before']['inversions'], 0)
        self.assertLess(report['authored_point_error_px'], 1e-10)
        for time in (0, .37, 1, 1.43, 2):
            before = sample(doc, 'move', time)[0]
            after = sample(changed, 'move', time)[0]
            self.assertEqual(before['other'], after['other'])
            for i in (0, 1, 3): self.assertEqual(before['leg'][i], after['leg'][i])
        self.assertFalse(report['selected'])

    def test_interval_edges_do_not_leak_and_outside_failures_remain(self):
        doc, request = fixture()
        request['interval'] = [.5, 1.5]
        changed, report = compile_patch(doc, request)
        for time in (0, .2, .5, 1.5, 1.8, 2):
            self.assertEqual(sample(doc, 'move', time)[0], sample(changed, 'move', time)[0])
        self.assertFalse(report['sampled_geometry_passed'])

    def test_bad_authored_geometry_stays_blocked(self):
        doc, request = fixture()
        request['poses'][0]['points'][0] = [0, -5]
        _, report = compile_patch(doc, request)
        self.assertFalse(report['sampled_geometry_passed'])

    def test_stale_and_invalid_requests_rejected(self):
        doc, request = fixture()
        for update in ({'document_sha256': '0'*64}, {'mesh_sha256': '0'*64}, {'vertices': [2, 2]},
                       {'interval': [0, 3]}, {'poses': [dict(time=0, points=[[1, 1]])]},
                       {'poses': [dict(time=1, points=[[math.nan, 1]])]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                compile_patch(doc, {**request, **update})

    def test_sparse_or_curved_source_not_silently_reinterpreted(self):
        doc, request = fixture()
        doc['animations']['move']['attachments']['default']['leg']['leg']['deform'][1]['curve'] = 'stepped'
        request['document_sha256'] = canonical_sha256(doc)
        with self.assertRaisesRegex(ValueError, 'dense_linear'):
            compile_patch(doc, request)

    def test_bezier_bone_curve_not_evaluated_as_linear(self):
        doc, request = fixture()
        doc['animations']['move']['bones']['root']['scale'][0]['curve'] = [.25, 0, .75, 1]
        request['document_sha256'] = canonical_sha256(doc)
        with self.assertRaisesRegex(ValueError, 'bezier'):
            compile_patch(doc, request)
