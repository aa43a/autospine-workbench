"""Synthetic choices remain explicit and source-bound across draft round trips."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.region_binding import build_region_bindings
from autospine_workbench.benchmark.region_binding_draft import build_binding_draft, validate_binding_draft
from tests.test_region_binding import fixture


class RegionBindingDraftTests(unittest.TestCase):
    def source(self):
        return build_region_bindings(*fixture())

    def test_initial_all_pending_not_suggested_adoption_and_pure(self):
        bindings = self.source()
        before = deepcopy(bindings)
        draft = build_binding_draft(bindings)
        self.assertEqual(bindings, before)
        self.assertTrue(all(r == {'layer_id': s['layer_id'], 'action': 'pending', 'bone_id': None, 'notes': ''}
                            for r, s in zip(draft['records'], bindings['bindings'])))
        validated = validate_binding_draft(bindings, draft)
        validated['records'][0]['notes'] = 'changed copy'
        self.assertEqual(draft['records'][0]['notes'], '')

    def test_explicit_allowed_bone_and_reasoned_actions(self):
        bindings = self.source()
        draft = build_binding_draft(bindings)
        draft['records'][0].update(action='bind', bone_id='head')
        draft['records'][1].update(action='bind', bone_id='upperarm_r')
        for action in ('requires_split', 'exclude', 'semantic_review'):
            draft['records'][2].update(action=action, notes='Synthetic explanation')
            self.assertEqual(validate_binding_draft(bindings, draft), draft)

    def test_blocked_unknown_bone_and_non_bind_bone_rejected(self):
        for index, action, bone in ((0, 'bind', 'pelvis'), (2, 'bind', 'head'),
                                   (0, 'pending', 'head'), (0, 'exclude', 'head'), (0, 'bind', True)):
            bindings = self.source()
            draft = build_binding_draft(bindings)
            draft['records'][index].update(action=action, bone_id=bone, notes='test')
            with self.assertRaises(ValueError):
                validate_binding_draft(bindings, draft)

    def test_notes_requirements_and_types(self):
        for action, notes in (('exclude', ''), ('requires_split', '  '), ('semantic_review', ''),
                              ('pending', True), ('pending', 'x'*2001), ('pending', 'x\x00y')):
            bindings = self.source()
            draft = build_binding_draft(bindings)
            draft['records'][0].update(action=action, notes=notes)
            with self.assertRaises(ValueError):
                validate_binding_draft(bindings, draft)

    def test_missing_duplicate_order_extra_authority_and_sha_rejected(self):
        for mutate in (lambda d: d['records'].pop(), lambda d: d['records'].reverse(),
                       lambda d: d['records'][1].update(layer_id=d['records'][0]['layer_id']),
                       lambda d: d['records'][0].update(extra=1), lambda d: d.update(extra=1),
                       lambda d: d.update(source_bindings_sha256='0'*64),
                       lambda d: d.update(production_authorized=0), lambda d: d.update(authority='human'),
                       lambda d: d['records'][0].update(action=True)):
            bindings = self.source()
            draft = build_binding_draft(bindings)
            mutate(draft)
            with self.assertRaises(ValueError):
                validate_binding_draft(bindings, draft)

    def test_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/region-binding-draft-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(build_binding_draft(self.source()))


if __name__ == '__main__':
    unittest.main()
