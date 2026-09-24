from copy import deepcopy
import unittest

from test_pose_geometry_patch import fixture
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.pose_mesh_refinement import refine
from autospine_workbench.targets.character43.pose_attachment_variant import compile_variant


class PoseAttachmentVariantTests(unittest.TestCase):
    def fixtures(self):
        doc, _ = fixture()
        doc['slots'] = [dict(name='leg', bone='root', attachment='leg')]
        variant, _ = refine(doc, 'leg', [0], canonical_sha256(doc))
        return doc, variant

    def compile(self, doc, variant, interval=None):
        return compile_variant(doc, variant, slot='leg', animation='move',
            interval=[.5, 1.5] if interval is None else interval, source_sha256=canonical_sha256(doc))

    def test_replaces_in_same_slot_with_separate_deform(self):
        doc, variant = self.fixtures(); before = deepcopy(doc)
        result, report = self.compile(doc, variant)
        self.assertEqual(doc, before)
        self.assertEqual(result['slots'], doc['slots'])
        self.assertEqual(result['skins'][0]['attachments']['leg']['leg'], doc['skins'][0]['attachments']['leg']['leg'])
        name = report['variant_attachment']
        self.assertEqual(result['skins'][0]['attachments']['leg'][name]['path'], 'leg')
        motion = result['animations']['move']
        self.assertEqual(motion['slots']['leg']['attachment'], [dict(time=0, name='leg'), dict(time=.5, name=name), dict(time=1.5, name='leg')])
        self.assertEqual(motion['attachments']['default']['leg'][name]['deform'], variant['animations']['move']['attachments']['default']['leg']['leg']['deform'])

    def test_out_of_scope_changes_and_existing_selection_rejected(self):
        doc, variant = self.fixtures()
        variant['bones'][0]['x'] += 1
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.compile(doc, variant)
        doc, variant = self.fixtures()
        doc['animations']['move']['slots'] = {'leg': {'attachment': [dict(time=0, name='leg')]}}
        with self.assertRaisesRegex(ValueError, 'existing_attachment'):
            self.compile(doc, variant)

    def test_collapsed_float32_interval_rejected(self):
        doc, variant = self.fixtures()
        with self.assertRaisesRegex(ValueError, 'collapsed'):
            self.compile(doc, variant, [.5, .500000001])
