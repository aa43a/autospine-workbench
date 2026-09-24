from copy import deepcopy
from hashlib import sha256
import json
import unittest

import test_view_pose_variant as fixtures
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.view_pose_variant import build as variant
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.runtime_storage_reference import build, stored_document


class RuntimeStorageVariantTests(unittest.TestCase):
    def fixture(self):
        doc, request = fixtures.ViewPoseVariantTests().fixture()
        document, report = variant(doc, request)
        raw = canonical_bytes(document)
        frames = []
        for time in (0, .4999, .5, .5001, 1, 1.4999, 1.5, 1.5001, 2):
            active = sample_active(document, 'move', time)
            frames.append(dict(time=time, attachments=active['attachments'], vertices=active['vertices']))
        reference = dict(skeleton_sha256=sha256(raw).hexdigest(), animations={'move': frames})
        return document, report, {
            'skeleton.json': raw, 'numeric-reference.json': canonical_bytes(reference)}

    def test_matching_deform_and_identity_at_boundaries(self):
        document, report, files = self.fixture(); before = deepcopy(files)
        result = build(files)
        self.assertEqual(files, before)
        frames = result['animations']['move']
        self.assertEqual(frames[1]['attachments']['leg'], 'leg')
        self.assertEqual(frames[2]['attachments']['leg'], report['variant']['variant_attachment'])
        self.assertEqual(frames[6]['attachments']['leg'], 'leg')
        self.assertLess(result['max_storage_displacement_px'], 1e-5)

    def test_wrong_reference_attachment_is_rejected(self):
        _, _, files = self.fixture()
        reference = json.loads(files['numeric-reference.json'])
        reference['animations']['move'][4]['attachments']['leg'] = 'leg'
        files['numeric-reference.json'] = canonical_bytes(reference)
        with self.assertRaisesRegex(ValueError, 'attachment_identity'):
            build(files)

    def test_float32_collision_and_invalid_names_rejected(self):
        document, _, _ = self.fixture()
        keys = document['animations']['move']['slots']['leg']['attachment']
        keys[2]['time'] = .500000001
        with self.assertRaisesRegex(ValueError, 'times_collapsed'):
            stored_document(document)
        keys[2]['time'] = 1.5; keys[1]['name'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'switch_invalid'):
            stored_document(document)
