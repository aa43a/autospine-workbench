from copy import deepcopy
import unittest

from test_pose_geometry_patch import fixture
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.view_pose_variant import build


class ViewPoseVariantTests(unittest.TestCase):
    def fixture(self):
        doc, _ = fixture()
        doc['slots'] = [dict(name='leg', bone='root', attachment='leg'),
                        dict(name='other', bone='root', attachment='other')]
        mesh = doc['skins'][0]['attachments']['leg']['leg']
        mapping = dict(mesh_sha256=canonical_sha256(mesh), source_uv=[[0, 0], [1, 0], [1, 1], [0, 1]],
                       target_uv=[[.1, .1], [.9, .1], [.9, .9], [.1, .9]],
                       target_xy=[[0, 0], [1.4, 0], [1.4, 2.4], [0, 2.4]], triangles=[[0, 1, 2], [0, 2, 3]])
        request = dict(document_sha256=canonical_sha256(doc), slot='leg', animation='move', interval=[.5, 1.5],
                       texture_sha256='a'*64, texture_size=[128, 256], poses=[dict(time=1, correspondence=mapping)])
        return doc, request

    def test_new_texture_and_geometry_use_separate_attachment(self):
        doc, request = self.fixture(); before = deepcopy(doc)
        changed, report = build(doc, request)
        self.assertEqual(doc, before)
        self.assertEqual(changed['bones'], doc['bones'])
        self.assertEqual(changed['slots'], doc['slots'])
        original = doc['skins'][0]['attachments']
        output = changed['skins'][0]['attachments']
        self.assertEqual(output['other'], original['other'])
        self.assertEqual(output['leg']['leg'], original['leg']['leg'])
        name = report['variant']['variant_attachment']
        self.assertEqual(output['leg'][name]['path'], 'view-'+'a'*64)
        self.assertEqual(output['leg'][name]['uvs'][:2], [.1, .1])
        self.assertLess(report['geometry']['authored_point_error_px'], 1e-6)
        track = changed['animations']['move']['slots']['leg']['attachment']
        self.assertEqual(track, [dict(time=0, name='leg'), dict(time=.5, name=name), dict(time=1.5, name='leg')])
        self.assertEqual(changed['animations']['move']['attachments']['default']['leg']['leg'],
                         doc['animations']['move']['attachments']['default']['leg']['leg'])

    def test_uv_changes_between_poses_require_another_attachment(self):
        doc, request = self.fixture()
        later = deepcopy(request['poses'][0]); later['time'] = 1.2
        later['correspondence']['target_uv'][0][0] += .05
        request['poses'].append(later)
        with self.assertRaisesRegex(ValueError, 'animated_uv'):
            build(doc, request)

    def test_invalid_texture_or_boundary_pose_rejected(self):
        for field, value in [('texture_sha256', '../bad'), ('texture_size', [0, 1])]:
            doc, request = self.fixture(); request[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build(doc, request)
        doc, request = self.fixture(); request['poses'][0]['time'] = .5
        with self.assertRaisesRegex(ValueError, 'pose_time'):
            build(doc, request)
