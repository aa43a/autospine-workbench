from copy import deepcopy
from hashlib import sha256
import json
import unittest
from test_character_affine_repair import fixture
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.runtime_storage_reference import build, stored_document, f32


class RuntimeStorageTests(unittest.TestCase):
    def test_shear_arrays_match_float32_storage(self):
        doc=self.document()
        doc['animations']['walk']['bones']['a']['shear']=[dict(time=.123456789,x=0,y=12.3456789)]
        stored=stored_document(doc)
        key=stored['animations']['walk']['bones']['a']['shear'][0]
        self.assertEqual(key['time'],f32(.123456789))
        self.assertEqual(key['y'],f32(12.3456789))
        self.assertEqual(doc['animations']['walk']['bones']['a']['shear'][0]['y'],12.3456789)

    def document(self):
        doc = fixture()
        doc['skins'][0]['attachments']['mesh']['mesh'].update(type='mesh', uvs=[0, 0, 1, 0, 0, 1])
        doc['bones'][0]['x'] = 1000.123456789
        return doc

    def test_quantizes_runtime_arrays_but_preserves_source_and_setup_fields(self):
        doc = self.document(); original = deepcopy(doc)
        doc['animations']['walk']['bones']['a']['scale'][1]['time'] = .123456789
        before = deepcopy(doc)
        stored = stored_document(doc)
        self.assertEqual(doc, before)
        self.assertEqual(stored['bones'], original['bones'])
        self.assertEqual(stored['animations']['walk']['bones']['a']['scale'][1]['time'], f32(.123456789))
        self.assertNotEqual(stored['animations']['walk']['bones']['a']['scale'][1]['time'], .123456789)

    def test_reference_preserves_exact_times_and_reports_displacement(self):
        doc = self.document(); raw = json.dumps(doc).encode(); digest = sha256(raw).hexdigest()
        ideal = dict(skeleton_sha256=digest, animations={'walk': [
            dict(time=t, vertices=sample(doc, 'walk', t)[0]) for t in (0, .33333333, 1)]})
        files = {'skeleton.json': raw, 'numeric-reference.json': json.dumps(ideal).encode()}
        before = deepcopy(files)
        result = build(files)
        self.assertEqual(files, before)
        self.assertEqual([r['time'] for r in result['animations']['walk']], [0, .33333333, 1])
        self.assertEqual(result['skeleton_sha256'], digest)
        self.assertGreater(result['max_storage_displacement_px'], 0)

    def test_unsupported_curves_are_not_silently_linearized(self):
        doc = self.document()
        doc['animations']['walk']['bones']['a']['scale'][0]['curve'] = [0, 1, 0, 1]
        with self.assertRaisesRegex(ValueError, 'curve_unsupported'):
            stored_document(doc)

    def test_reference_must_match_exact_skeleton(self):
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            build({'skeleton.json': b'{}', 'numeric-reference.json': b'{"skeleton_sha256":"wrong"}'})

    def test_key_times_that_collapse_in_float32_are_rejected(self):
        doc = self.document()
        keys = doc['animations']['walk']['bones']['a']['scale']
        keys[0]['time'] = 1
        keys[1]['time'] = 1+1e-10
        with self.assertRaisesRegex(ValueError, 'key_times_collapsed'):
            stored_document(doc)

    def test_draw_order_times_match_runtime_storage_without_changing_offsets(self):
        doc = self.document()
        keys = [dict(time=.1, offsets=[dict(slot='mesh', offset=0)]), dict(time=.2)]
        doc['animations']['walk']['drawOrder'] = keys
        stored = stored_document(doc)['animations']['walk']['drawOrder']
        self.assertEqual(stored[0]['time'], f32(.1))
        self.assertEqual(stored[0]['offsets'], keys[0]['offsets'])
        self.assertEqual(keys[0]['time'], .1)


if __name__ == '__main__':
    unittest.main()
