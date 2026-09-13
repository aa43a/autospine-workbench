import json
import unittest
from hashlib import sha256
from pathlib import Path

import jsonschema

from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.targets.character43.order_candidate import generate, stable_order
from test_character_motion_composition import package


def fixture():
    files = package('idle')
    doc = json.loads(files['skeleton.json'])
    doc['skeleton'] = {'spine': '4.3.26'}
    doc['slots'] = [{'name': n} for n in ['wing', 'skirt', 'leg', 'face']]
    files['skeleton.json'] = files['editor/skeleton.json'] = raw(doc)
    reference = json.loads(files['numeric-reference.json'])
    reference['skeleton_sha256'] = sha256(files['skeleton.json']).hexdigest()
    files['numeric-reference.json'] = raw(reference)
    return files


class OrderCandidateTests(unittest.TestCase):
    def test_order_deterministic_and_unrelated_slots_stable(self):
        names = ['wing', 'skirt', 'leg', 'face']
        self.assertEqual(stable_order(names, [('leg', 'skirt')])[0], ['wing', 'leg', 'skirt', 'face'])
        self.assertEqual(stable_order(names, [('leg', 'skirt'), ('wing', 'leg')]),
                         stable_order(names, [('wing', 'leg'), ('leg', 'skirt'), ('leg', 'skirt')]))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            stable_order(names, [('leg', 'skirt'), ('skirt', 'leg')])
        with self.assertRaisesRegex(ValueError, 'missing'):
            stable_order(names, [('missing', 'skirt')])

    def test_only_order_and_identity_change_not_geometry_or_approval(self):
        files = fixture(); before = dict(files)
        result, report = generate(files, [('leg', 'skirt')])
        self.assertEqual(files, before)
        a, b = (json.loads(x['skeleton.json']) for x in (files, result))
        for key in ('bones', 'skins', 'animations'):
            self.assertEqual(a[key], b[key])
        self.assertEqual(result['images/leg.png'], files['images/leg.png'])
        ref = json.loads(result['numeric-reference.json'])
        self.assertEqual(ref['skeleton_sha256'], sha256(result['skeleton.json']).hexdigest())
        self.assertEqual(ref['animations'], json.loads(files['numeric-reference.json'])['animations'])
        self.assertEqual(json.loads(result['editor/skeleton.json'])['slots'], b['slots'])
        self.assertFalse(report['selected'])
        self.assertEqual(json.loads(result['character-manifest.json'])['qa']['runtime_status'], 'not_run')
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/character-order-candidate-v1.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(report, schema)

    def test_animated_order_clipping_and_stale_reference_fail_closed(self):
        for kind in ('drawOrder', 'clipping', 'reference'):
            files = fixture(); doc = json.loads(files['skeleton.json'])
            if kind == 'drawOrder': doc['animations']['idle']['drawOrder'] = []
            if kind == 'clipping': doc['skins'][0]['attachments']['leg']['leg']['type'] = 'clipping'
            if kind == 'reference': doc['bones'][0]['x'] = 3
            files['skeleton.json'] = raw(doc)
            with self.assertRaisesRegex(ValueError, 'dependency|identity'):
                generate(files, [('leg', 'skirt')])
